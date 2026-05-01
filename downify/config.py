from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    jamendo_client_id: str | None
    download_dir: Path
    max_album_tracks: int
    max_zip_part_mb: int
    wav_sample_rate: int
    wav_channels: int
    search_provider: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        return cls(
            telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
            jamendo_client_id=os.getenv("JAMENDO_CLIENT_ID"),
            download_dir=Path(os.getenv("DOWNLOAD_DIR", "downloads")),
            max_album_tracks=int(os.getenv("MAX_ALBUM_TRACKS", "25")),
            max_zip_part_mb=int(os.getenv("MAX_ZIP_PART_MB", "40")),
            wav_sample_rate=int(os.getenv("WAV_SAMPLE_RATE", "22050")),
            wav_channels=int(os.getenv("WAV_CHANNELS", "1")),
            search_provider=os.getenv("SEARCH_PROVIDER", "jamendo").lower(),
        )


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
