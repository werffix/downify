from __future__ import annotations

import asyncio
import shutil
from pathlib import Path


class MediaError(RuntimeError):
    pass


async def convert_to_wav(source: Path, destination: Path) -> Path:
    if shutil.which("ffmpeg") is None:
        raise MediaError(
            "ffmpeg не установлен. Установите его на сервере: apt update && apt install ffmpeg"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "44100",
        "-ac",
        "2",
        str(destination),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    if process.returncode != 0:
        details = stderr.decode(errors="ignore")[-800:]
        raise MediaError(f"ffmpeg не смог сконвертировать аудио: {details}")

    return destination

