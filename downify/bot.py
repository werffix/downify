from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from downify.config import Settings
from downify.media import convert_to_wav
from downify.models import SpotifyRelease, SpotifyTrack
from downify.providers import DownloadProvider, JamendoProvider
from downify.spotify import SpotifyClient

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Пришлите Spotify-ссылку на трек или альбом. "
        "Я возьму только метаданные релиза и попробую найти легальную загрузку "
        "на подключенной платформе."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    text = message.text or ""
    settings: Settings = context.application.bot_data["settings"]
    spotify: SpotifyClient = context.application.bot_data["spotify"]
    provider: DownloadProvider = context.application.bot_data["provider"]

    if "open.spotify.com" not in text and "spotify.link" not in text:
        await message.reply_text("Пришлите ссылку Spotify на трек или альбом.")
        return

    try:
        await message.chat.send_action(ChatAction.TYPING)
        release = await spotify.resolve(text)
    except Exception as exc:
        logger.exception("Failed to resolve Spotify link")
        await message.reply_text(f"Не смог прочитать Spotify-ссылку: {exc}")
        return

    await _send_cover(update, release, settings.download_dir)

    tracks = release.tracks[: settings.max_album_tracks]
    if release.kind == "album" and len(release.tracks) > len(tracks):
        await message.reply_text(
            f"В альбоме {len(release.tracks)} треков, обработаю первые {len(tracks)}. "
            "Лимит меняется через MAX_ALBUM_TRACKS."
        )

    if release.kind == "album" and len(tracks) <= 1 and tracks[0].title == release.title:
        await message.reply_text(
            "Это ссылка на альбом, но публичная страница Spotify не отдала треклист. "
            "Без Spotify API я не могу надежно узнать все треки альбома."
        )
        return

    await message.reply_text(_release_summary(release, len(tracks)))

    if release.kind == "album":
        await _process_album(update, provider, release, tracks, settings.download_dir)
        return

    for track in tracks:
        await _process_track(update, provider, track, settings.download_dir)


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram update error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(f"Ошибка обработки: {context.error}")


async def _send_cover(update: Update, release: SpotifyRelease, download_dir: Path) -> None:
    if not release.cover_url:
        return

    cover_dir = download_dir / "covers"
    cover_dir.mkdir(parents=True, exist_ok=True)
    cover_path = cover_dir / f"{_safe_filename(release.title)}.jpg"

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(release.cover_url)
        response.raise_for_status()
        cover_path.write_bytes(response.content)

    with cover_path.open("rb") as cover_file:
        await update.effective_message.reply_document(
            document=cover_file,
            filename=cover_path.name,
            caption=f"Обложка: {release.title}",
        )


async def _process_track(
    update: Update,
    provider: DownloadProvider,
    track: SpotifyTrack,
    download_dir: Path,
) -> None:
    message = update.effective_message
    await message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)

    found = await provider.search(track)
    if found is None:
        await message.reply_text(f"Не нашел легальную загрузку: {track.caption}")
        return

    downloaded = await provider.download(found, download_dir / "source")
    wav_path = await convert_to_wav(
        downloaded.file_path,
        download_dir / "wav" / f"{_track_filename(track)}.wav",
    )
    license_suffix = f"\nЛицензия: {found.license_name}" if found.license_name else ""
    caption = f"{track.caption}\nИсточник: {found.source_name}{license_suffix}"

    with wav_path.open("rb") as audio_file:
        await message.reply_document(
            document=audio_file,
            filename=wav_path.name,
            caption=caption[:1024],
        )


async def _process_album(
    update: Update,
    provider: DownloadProvider,
    release: SpotifyRelease,
    tracks: tuple[SpotifyTrack, ...],
    download_dir: Path,
) -> None:
    message = update.effective_message
    album_dir = download_dir / "albums" / _safe_filename(release.title)
    wav_dir = album_dir / "wav"
    wav_dir.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    wav_files: list[Path] = []

    for track in tracks:
        await message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
        wav_path = await _download_track_wav(provider, track, album_dir)
        if wav_path is None:
            missing.append(track.title)
        else:
            wav_files.append(wav_path)

    if not wav_files:
        await message.reply_text("Не нашел легальные загрузки для треков альбома.")
        return

    zip_path = album_dir / f"{_safe_filename(release.title)}.zip"
    await asyncio.to_thread(_write_zip, zip_path, wav_files)

    caption = f"{release.title}: {len(wav_files)} WAV-файлов"
    if missing:
        caption += f"\nНе найдено: {len(missing)}"

    with zip_path.open("rb") as zip_file:
        await message.reply_document(
            document=zip_file,
            filename=zip_path.name,
            caption=caption[:1024],
        )


async def _download_track_wav(
    provider: DownloadProvider,
    track: SpotifyTrack,
    album_dir: Path,
) -> Path | None:
    found = await provider.search(track)
    if found is None:
        return None

    downloaded = await provider.download(found, album_dir / "source")
    prefix = f"{track.track_number:02d} " if track.track_number else ""
    return await convert_to_wav(
        downloaded.file_path,
        album_dir / "wav" / f"{prefix}{_track_filename(track)}.wav",
    )


def _write_zip(zip_path: Path, files: list[Path]) -> None:
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for file_path in files:
            archive.write(file_path, arcname=file_path.name)


def _release_summary(release: SpotifyRelease, track_count: int) -> str:
    artists = ", ".join(release.artists)
    heading = f"{artists} - {release.title}" if artists else release.title
    return (
        f"Spotify metadata:\n"
        f"{heading}\n"
        f"Дата релиза: {release.release_date}\n"
        f"Треков к обработке: {track_count}"
    )


def _safe_filename(value: str) -> str:
    keep = []
    for char in value:
        keep.append(char if char.isalnum() or char in " ._-" else "_")
    return "".join(keep).strip()[:120] or "cover"


def _track_filename(track: SpotifyTrack) -> str:
    artist = " - ".join(track.artists)
    name = f"{artist} - {track.title}" if artist else track.title
    return _safe_filename(name)


def build_provider(settings: Settings) -> DownloadProvider:
    if settings.search_provider == "jamendo":
        if not settings.jamendo_client_id:
            raise RuntimeError("SEARCH_PROVIDER=jamendo requires JAMENDO_CLIENT_ID")
        return JamendoProvider(settings.jamendo_client_id)

    raise RuntimeError(f"Unknown SEARCH_PROVIDER: {settings.search_provider}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    settings.download_dir.mkdir(parents=True, exist_ok=True)

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["settings"] = settings
    app.bot_data["spotify"] = SpotifyClient()
    app.bot_data["provider"] = build_provider(settings)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(handle_error)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
