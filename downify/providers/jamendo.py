from __future__ import annotations

import httpx

from downify.models import ProviderTrack, SpotifyTrack
from downify.providers.base import DownloadProvider


class JamendoProvider(DownloadProvider):
    source_name = "Jamendo"
    api_url = "https://api.jamendo.com/v3.0/tracks/"

    def __init__(self, client_id: str) -> None:
        self.client_id = client_id

    async def search(self, track: SpotifyTrack) -> ProviderTrack | None:
        params = {
            "client_id": self.client_id,
            "format": "json",
            "limit": 1,
            "audioformat": "mp32",
            "include": "musicinfo",
            "search": track.query,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(self.api_url, params=params)
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        if not results:
            return None

        item = results[0]
        download_url = item.get("audiodownload") or item.get("audio")
        if not download_url:
            return None

        return ProviderTrack(
            title=item.get("name") or track.title,
            artists=(item.get("artist_name") or track.artists[0],),
            source_name=self.source_name,
            download_url=download_url,
            license_name=_license_name(item),
        )


def _license_name(item: dict) -> str | None:
    licenses = item.get("musicinfo", {}).get("licenses") or []
    if not licenses:
        return None
    return licenses[0].get("name") or licenses[0].get("url")

