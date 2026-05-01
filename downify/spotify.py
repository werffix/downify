from __future__ import annotations

import base64
import re
from urllib.parse import urlparse

import httpx

from downify.models import SpotifyRelease, SpotifyTrack


class SpotifyClient:
    token_url = "https://accounts.spotify.com/api/token"
    api_base = "https://api.spotify.com/v1"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None

    async def resolve(self, url: str) -> SpotifyRelease:
        kind, item_id = parse_spotify_url(url)
        if kind == "track":
            return await self._get_track_release(item_id)
        if kind == "album":
            return await self._get_album_release(item_id)
        raise ValueError("Поддерживаются только ссылки Spotify на трек или альбом.")

    async def _headers(self) -> dict[str, str]:
        if self._token is None:
            raw = f"{self.client_id}:{self.client_secret}".encode()
            auth = base64.b64encode(raw).decode()
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    self.token_url,
                    data={"grant_type": "client_credentials"},
                    headers={"Authorization": f"Basic {auth}"},
                )
                response.raise_for_status()
                self._token = response.json()["access_token"]
        return {"Authorization": f"Bearer {self._token}"}

    async def _get_track_release(self, track_id: str) -> SpotifyRelease:
        data = await self._get_json(f"/tracks/{track_id}")
        album = data["album"]
        track = SpotifyTrack(
            title=data["name"],
            artists=tuple(artist["name"] for artist in data["artists"]),
            album=album["name"],
            release_date=album["release_date"],
            cover_url=_largest_image(album.get("images", [])),
            track_number=data.get("track_number"),
        )
        return SpotifyRelease(
            kind="track",
            title=track.title,
            artists=track.artists,
            release_date=track.release_date,
            cover_url=track.cover_url,
            tracks=(track,),
        )

    async def _get_album_release(self, album_id: str) -> SpotifyRelease:
        album = await self._get_json(f"/albums/{album_id}")
        album_title = album["name"]
        artists = tuple(artist["name"] for artist in album["artists"])
        release_date = album["release_date"]
        cover_url = _largest_image(album.get("images", []))

        tracks: list[SpotifyTrack] = []
        items = list(album["tracks"]["items"])
        next_url = album["tracks"].get("next")

        while next_url:
            page = await self._get_absolute_json(next_url)
            items.extend(page["items"])
            next_url = page.get("next")

        for item in items:
            tracks.append(
                SpotifyTrack(
                    title=item["name"],
                    artists=tuple(artist["name"] for artist in item["artists"]) or artists,
                    album=album_title,
                    release_date=release_date,
                    cover_url=cover_url,
                    track_number=item.get("track_number"),
                )
            )

        return SpotifyRelease(
            kind="album",
            title=album_title,
            artists=artists,
            release_date=release_date,
            cover_url=cover_url,
            tracks=tuple(tracks),
        )

    async def _get_json(self, path: str) -> dict:
        return await self._get_absolute_json(f"{self.api_base}{path}")

    async def _get_absolute_json(self, url: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, headers=await self._headers())
            response.raise_for_status()
            return response.json()


def parse_spotify_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if parsed.netloc not in {"open.spotify.com", "spotify.link"}:
        raise ValueError("Пришлите ссылку open.spotify.com на трек или альбом.")

    match = re.search(r"/(track|album)/([A-Za-z0-9]+)", parsed.path)
    if not match:
        raise ValueError("Не смог распознать Spotify-ссылку на трек или альбом.")
    return match.group(1), match.group(2)


def _largest_image(images: list[dict]) -> str | None:
    if not images:
        return None
    return sorted(images, key=lambda image: image.get("width") or 0, reverse=True)[0]["url"]

