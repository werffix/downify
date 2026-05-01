from __future__ import annotations

import logging
from pathlib import Path

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from downify.config import Settings
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

    await message.reply_text(_release_summary(release, len(tracks)))

    for track in tracks:
        await _process_track(update, provider, track, settings.download_dir)


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
    await message.chat.send_action(ChatAction.UPLOAD_AUDIO)

    found = await provider.search(track)
    if found is None:
        await message.reply_text(f"Не нашел легальную загрузку: {track.caption}")
        return

    downloaded = await provider.download(found, download_dir / "audio")
    license_suffix = f"\nЛицензия: {found.license_name}" if found.license_name else ""
    caption = f"{track.caption}\nИсточник: {found.source_name}{license_suffix}"

    with downloaded.file_path.open("rb") as audio_file:
        await message.reply_audio(
            audio=audio_file,
            filename=downloaded.file_path.name,
            caption=caption[:1024],
            title=track.title,
            performer=", ".join(track.artists),
        )


def _release_summary(release: SpotifyRelease, track_count: int) -> str:
    artists = ", ".join(release.artists)
    return (
        f"Spotify metadata:\n"
        f"{artists} - {release.title}\n"
        f"Дата релиза: {release.release_date}\n"
        f"Треков к обработке: {track_count}"
    )


def _safe_filename(value: str) -> str:
    keep = []
    for char in value:
        keep.append(char if char.isalnum() or char in " ._-" else "_")
    return "".join(keep).strip()[:120] or "cover"


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
    app.bot_data["spotify"] = SpotifyClient(settings.spotify_client_id, settings.spotify_client_secret)
    app.bot_data["provider"] = build_provider(settings)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

