from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SpotifyTrack:
    title: str
    artists: tuple[str, ...]
    album: str
    release_date: str
    cover_url: str | None
    track_number: int | None = None

    @property
    def query(self) -> str:
        artist = self.artists[0] if self.artists else ""
        return f"{artist} {self.title}".strip()

    @property
    def caption(self) -> str:
        artist = ", ".join(self.artists)
        heading = f"{artist} - {self.title}" if artist else self.title
        return f"{heading}\n{self.album} ({self.release_date})"


@dataclass(frozen=True)
class SpotifyRelease:
    kind: str
    title: str
    artists: tuple[str, ...]
    release_date: str
    cover_url: str | None
    tracks: tuple[SpotifyTrack, ...]


@dataclass(frozen=True)
class ProviderTrack:
    title: str
    artists: tuple[str, ...]
    source_name: str
    download_url: str
    license_name: str | None = None


@dataclass(frozen=True)
class DownloadedTrack:
    provider_track: ProviderTrack
    file_path: Path
