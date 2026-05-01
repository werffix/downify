from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from downify.config import Settings
from downify.media import convert_to_wav
from downify.models import SpotifyRelease, SpotifyTrack
from downify.providers import DownloadProvider, JamendoProvider
from downify.spotify import SpotifyClient

logger = logging.getLogger(__name__)

settings = Settings.from_env()
settings.download_dir.mkdir(parents=True, exist_ok=True)
spotify = SpotifyClient()
provider = None
app = FastAPI(title="Downify")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class PrepareRequest(BaseModel):
    url: str


@dataclass
class TrackResult:
    title: str
    artists: list[str]
    filename: str | None = None
    path: str | None = None
    error: str | None = None


@dataclass
class JobResult:
    id: str
    status: str
    message: str
    kind: str | None = None
    title: str | None = None
    artists: list[str] | None = None
    cover_path: str | None = None
    zip_path: str | None = None
    tracks: list[TrackResult] | None = None
    error: str | None = None


jobs: dict[str, JobResult] = {}


@app.on_event("startup")
async def startup() -> None:
    global provider
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    provider = build_provider(settings)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.post("/api/prepare")
async def prepare(payload: PrepareRequest) -> dict[str, str]:
    job_id = uuid.uuid4().hex
    jobs[job_id] = JobResult(
        id=job_id,
        status="queued",
        message="Задача поставлена в очередь",
        tracks=[],
    )
    asyncio.create_task(process_job(job_id, payload.url))
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str) -> dict:
    job = get_job(job_id)
    return serialize_job(job)


@app.get("/release/{job_id}")
async def release_page(job_id: str) -> FileResponse:
    get_job(job_id)
    return FileResponse(static_dir / "release.html")


@app.get("/download/{job_id}/cover")
async def download_cover(job_id: str) -> FileResponse:
    job = get_done_job(job_id)
    if not job.cover_path:
        raise HTTPException(status_code=404, detail="Cover not found")
    return FileResponse(job.cover_path, filename=Path(job.cover_path).name)


@app.get("/download/{job_id}/zip")
async def download_zip(job_id: str) -> FileResponse:
    job = get_done_job(job_id)
    if not job.zip_path:
        raise HTTPException(status_code=404, detail="ZIP is not available for this release")
    return FileResponse(job.zip_path, filename=Path(job.zip_path).name)


@app.get("/download/{job_id}/tracks/{track_index}")
async def download_track(job_id: str, track_index: int) -> FileResponse:
    job = get_done_job(job_id)
    if not job.tracks or track_index < 0 or track_index >= len(job.tracks):
        raise HTTPException(status_code=404, detail="Track not found")

    track = job.tracks[track_index]
    if not track.path:
        raise HTTPException(status_code=404, detail=track.error or "Track file not found")
    return FileResponse(track.path, filename=track.filename or Path(track.path).name)


async def process_job(job_id: str, url: str) -> None:
    job = jobs[job_id]
    job.status = "working"
    job.message = "Парсим Spotify-ссылку"

    try:
        release = await spotify.resolve(url)
        job.kind = release.kind
        job.title = release.title
        job.artists = list(release.artists)

        job.message = "Скачиваем обложку релиза"
        job.cover_path = await download_cover_file(release, job_dir(job_id))

        tracks = release.tracks[: settings.max_album_tracks]
        if release.kind == "album" and len(tracks) <= 1 and tracks[0].title == release.title:
            raise RuntimeError(
                "Публичная страница Spotify не отдала треклист альбома. "
                "Попробуйте другой альбом или ссылку на отдельный трек."
            )

        job.message = "Ищем треки на подключенной платформе"
        job.tracks = await download_tracks(job_id, tracks)

        downloaded = [track for track in job.tracks if track.path]
        if not downloaded:
            raise RuntimeError("Не нашлось ни одного легально доступного трека.")

        if release.kind == "album":
            job.message = "Собираем ZIP-архив"
            zip_path = job_dir(job_id) / f"{safe_filename(release.title)}.zip"
            await asyncio.to_thread(write_release_zip, zip_path, job.cover_path, downloaded)
            job.zip_path = str(zip_path)

        job.status = "done"
        job.message = "Готово"
        save_job(job)
    except Exception as exc:
        logger.exception("Job failed")
        job.status = "error"
        job.error = str(exc)
        job.message = "Ошибка"
        save_job(job)


async def download_cover_file(release: SpotifyRelease, directory: Path) -> str | None:
    if not release.cover_url:
        return None

    directory.mkdir(parents=True, exist_ok=True)
    cover_path = directory / f"{safe_filename(release.title)}.jpg"
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(release.cover_url)
        response.raise_for_status()
        cover_path.write_bytes(response.content)
    return str(cover_path)


async def download_tracks(job_id: str, tracks: tuple[SpotifyTrack, ...]) -> list[TrackResult]:
    assert provider is not None
    results: list[TrackResult] = []
    for index, track in enumerate(tracks, start=1):
        jobs[job_id].message = f"Скачиваем и конвертируем трек {index}/{len(tracks)}: {track.title}"
        results.append(await download_track_wav(provider, track, job_dir(job_id)))
        save_job(jobs[job_id])
    return results


async def download_track_wav(
    download_provider: DownloadProvider,
    track: SpotifyTrack,
    directory: Path,
) -> TrackResult:
    result = TrackResult(title=track.title, artists=list(track.artists))
    try:
        found = await download_provider.search(track)
        if found is None:
            result.error = "Не найдено на подключенной платформе"
            return result

        downloaded = await download_provider.download(found, directory / "source")
        prefix = f"{track.track_number:02d} " if track.track_number else ""
        wav_path = await convert_to_wav(
            downloaded.file_path,
            directory / "wav" / f"{prefix}{track_filename(track)}.wav",
            sample_rate=settings.wav_sample_rate,
            channels=settings.wav_channels,
        )
        result.path = str(wav_path)
        result.filename = wav_path.name
        return result
    except Exception as exc:
        result.error = str(exc)
        return result


def write_release_zip(zip_path: Path, cover_path: str | None, tracks: list[TrackResult]) -> None:
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        if cover_path:
            archive.write(cover_path, arcname=Path(cover_path).name)
        for track in tracks:
            if track.path:
                archive.write(track.path, arcname=track.filename or Path(track.path).name)


def build_provider(current_settings: Settings) -> DownloadProvider:
    if current_settings.search_provider == "jamendo":
        if not current_settings.jamendo_client_id:
            raise RuntimeError("SEARCH_PROVIDER=jamendo requires JAMENDO_CLIENT_ID")
        return JamendoProvider(current_settings.jamendo_client_id)
    raise RuntimeError(f"Unknown SEARCH_PROVIDER: {current_settings.search_provider}")


def get_job(job_id: str) -> JobResult:
    if job_id not in jobs:
        loaded = load_job(job_id)
        if loaded is None:
            raise HTTPException(status_code=404, detail="Job not found")
        jobs[job_id] = loaded
    return jobs[job_id]


def get_done_job(job_id: str) -> JobResult:
    job = get_job(job_id)
    if job.status != "done":
        raise HTTPException(status_code=409, detail="Release is not ready yet")
    return job


def serialize_job(job: JobResult) -> dict:
    data = asdict(job)
    data["has_cover"] = bool(job.cover_path)
    data["has_zip"] = bool(job.zip_path)
    return data


def save_job(job: JobResult) -> None:
    path = job_dir(job.id) / "job.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(serialize_job(job), ensure_ascii=False, indent=2), encoding="utf-8")


def load_job(job_id: str) -> JobResult | None:
    path = job_dir(job_id) / "job.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    tracks = [TrackResult(**track) for track in data.get("tracks") or []]
    return JobResult(
        id=data["id"],
        status=data["status"],
        message=data["message"],
        kind=data.get("kind"),
        title=data.get("title"),
        artists=data.get("artists"),
        cover_path=data.get("cover_path"),
        zip_path=data.get("zip_path"),
        tracks=tracks,
        error=data.get("error"),
    )


def job_dir(job_id: str) -> Path:
    return settings.download_dir / "jobs" / job_id


def safe_filename(value: str) -> str:
    keep = []
    for char in value:
        keep.append(char if char.isalnum() or char in " ._-" else "_")
    return "".join(keep).strip()[:140] or "release"


def track_filename(track: SpotifyTrack) -> str:
    artist = " - ".join(track.artists)
    name = f"{artist} - {track.title}" if artist else track.title
    return safe_filename(name)


def main() -> None:
    uvicorn.run("downify.web:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
