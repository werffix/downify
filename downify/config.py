from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    spotify_client_id: str
    spotify_client_secret: str
    jamendo_client_id: str | None
    download_dir: Path
    max_album_tracks: int
    search_provider: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        return cls(
            telegram_bot_token=_required("TELEGRAM_BOT_TOKEN"),
            spotify_client_id=_required("SPOTIFY_CLIENT_ID"),
            spotify_client_secret=_required("SPOTIFY_CLIENT_SECRET"),
            jamendo_client_id=os.getenv("JAMENDO_CLIENT_ID"),
            download_dir=Path(os.getenv("DOWNLOAD_DIR", "downloads")),
            max_album_tracks=int(os.getenv("MAX_ALBUM_TRACKS", "25")),
            search_provider=os.getenv("SEARCH_PROVIDER", "jamendo").lower(),
        )


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

