from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from downify.models import DownloadedTrack, ProviderTrack, SpotifyTrack


class DownloadProvider(ABC):
    source_name: str

    @abstractmethod
    async def search(self, track: SpotifyTrack) -> ProviderTrack | None:
        """Find a legally downloadable track matching Spotify metadata."""

    async def download(self, provider_track: ProviderTrack, destination: Path) -> DownloadedTrack:
        destination.mkdir(parents=True, exist_ok=True)
        artist = " - ".join(provider_track.artists)
        display_name = (
            f"{artist} - {provider_track.title}.mp3" if artist else f"{provider_track.title}.mp3"
        )
        safe_name = _safe_filename(display_name)
        file_path = destination / safe_name

        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            response = await client.get(provider_track.download_url)
            response.raise_for_status()
            file_path.write_bytes(response.content)

        return DownloadedTrack(provider_track=provider_track, file_path=file_path)


def _safe_filename(value: str) -> str:
    keep = []
    for char in value:
        keep.append(char if char.isalnum() or char in " ._-" else "_")
    return "".join(keep).strip()[:180] or "track.mp3"
