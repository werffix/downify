from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse

import httpx

from downify.models import SpotifyRelease, SpotifyTrack


class SpotifyClient:
    """Resolve public Spotify links without Spotify Web API credentials.

    Spotify's Web API can require Premium access for app owners. This resolver uses
    public metadata available for embeds/pages: title and cover. Full album track
    lists and exact release dates are not available through this path.
    """

    oembed_url = "https://open.spotify.com/oembed"

    def __init__(self) -> None:
        pass

    async def resolve(self, url: str) -> SpotifyRelease:
        normalized_url = normalize_spotify_url(url)
        kind, _item_id = parse_spotify_url(normalized_url)
        metadata = await self._get_public_metadata(normalized_url)

        title, artists = parse_public_title(metadata.title)
        album_title = title

        if kind == "album":
            page_html = metadata.html or await self._get_page_html(normalized_url)
            tracks = _parse_album_tracks(page_html, album_title, artists, metadata.thumbnail_url)
            if not tracks:
                tracks = (
                    SpotifyTrack(
                        title=album_title,
                        artists=artists,
                        album=album_title,
                        release_date="unknown",
                        cover_url=metadata.thumbnail_url,
                        track_number=None,
                    ),
                )
        else:
            tracks = (
                SpotifyTrack(
                    title=title,
                    artists=artists,
                    album=album_title,
                    release_date="unknown",
                    cover_url=metadata.thumbnail_url,
                    track_number=None,
                ),
            )

        return SpotifyRelease(
            kind=kind,
            title=album_title,
            artists=artists,
            release_date="unknown",
            cover_url=metadata.thumbnail_url,
            tracks=tracks,
        )

    async def _get_public_metadata(self, url: str) -> "_PublicMetadata":
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            oembed_response = await client.get(self.oembed_url, params={"url": url})
            if oembed_response.status_code < 400:
                data = oembed_response.json()
                title = data.get("title")
                if title:
                    return _PublicMetadata(
                        title=title,
                        thumbnail_url=data.get("thumbnail_url"),
                    )

            page_response = await client.get(url)
            page_response.raise_for_status()
            return _parse_page_metadata(page_response.text)

    async def _get_page_html(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text


class _PublicMetadata:
    def __init__(
        self,
        title: str,
        thumbnail_url: str | None = None,
        html: str | None = None,
    ) -> None:
        self.title = title
        self.thumbnail_url = thumbnail_url
        self.html = html


def normalize_spotify_url(value: str) -> str:
    match = re.search(r"https?://[^\s]+", value.strip())
    if not match:
        raise ValueError("Пришлите Spotify-ссылку на трек или альбом.")

    url = match.group(0).rstrip(").,]")
    parsed = urlparse(url)
    if parsed.netloc not in {"open.spotify.com", "spotify.link"}:
        raise ValueError("Пришлите ссылку open.spotify.com или spotify.link.")

    return url


def parse_spotify_url(url: str) -> tuple[str, str | None]:
    parsed = urlparse(url.strip())
    if parsed.netloc == "spotify.link":
        return "track", None

    match = re.search(r"/(track|album)/([A-Za-z0-9]+)", parsed.path)
    if not match:
        raise ValueError("Не смог распознать Spotify-ссылку на трек или альбом.")
    return match.group(1), match.group(2)


def parse_public_title(value: str) -> tuple[str, tuple[str, ...]]:
    title = _clean_title(value)

    # Common page/oEmbed variants include "Track by Artist", "Album by Artist",
    # or "Artist - Track". Keep this parser conservative so search queries stay useful.
    by_match = re.match(r"(.+?)\s+by\s+(.+)$", title, flags=re.IGNORECASE)
    if by_match:
        return by_match.group(1).strip(), _split_artists(by_match.group(2))

    dash_match = re.match(r"(.+?)\s+-\s+(.+)$", title)
    if dash_match:
        left, right = dash_match.group(1).strip(), dash_match.group(2).strip()
        return right, _split_artists(left)

    return title, ()


def _parse_page_metadata(html: str) -> _PublicMetadata:
    og_title = _meta_content(html, "og:title") or _title_tag(html)
    if not og_title:
        raise ValueError("Spotify не отдал публичные метаданные по этой ссылке.")

    return _PublicMetadata(
        title=og_title,
        thumbnail_url=_meta_content(html, "og:image"),
        html=html,
    )


def _parse_album_tracks(
    html: str,
    album_title: str,
    artists: tuple[str, ...],
    cover_url: str | None,
) -> tuple[SpotifyTrack, ...]:
    tracks: dict[int, str] = {}
    unescaped_html = unescape(html)

    patterns = [
        r'"trackNumber"\s*:\s*(\d+).*?"name"\s*:\s*"([^"]+)"',
        r'"name"\s*:\s*"([^"]+)".{0,500}?"trackNumber"\s*:\s*(\d+)',
        r'"track_number"\s*:\s*(\d+).*?"name"\s*:\s*"([^"]+)"',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, unescaped_html, flags=re.IGNORECASE | re.DOTALL):
            if len(match.groups()) != 2:
                continue
            first, second = match.group(1), match.group(2)
            if first.isdigit():
                number, name = int(first), second
            else:
                number, name = int(second), first
            name = _clean_json_string(name)
            if name and name.lower() != album_title.lower():
                tracks.setdefault(number, name)

    return tuple(
        SpotifyTrack(
            title=name,
            artists=artists,
            album=album_title,
            release_date="unknown",
            cover_url=cover_url,
            track_number=number,
        )
        for number, name in sorted(tracks.items())
    )


def _clean_json_string(value: str) -> str:
    value = value.encode().decode("unicode_escape", errors="ignore")
    return _clean_title(value)


def _meta_content(html: str, property_name: str) -> str | None:
    patterns = [
        rf'<meta\s+property=["\']{re.escape(property_name)}["\']\s+content=["\']([^"\']+)["\']',
        rf'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']{re.escape(property_name)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return _clean_title(match.group(1))
    return None


def _title_tag(html: str) -> str | None:
    match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return _clean_title(match.group(1))


def _clean_title(value: str) -> str:
    title = unescape(value)
    title = re.sub(r"\s*\|\s*Spotify\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^Spotify\s*-\s*", "", title, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", title).strip()


def _split_artists(value: str) -> tuple[str, ...]:
    artists = re.split(r"\s*,\s*|\s+&\s+|\s+and\s+", value.strip())
    return tuple(artist for artist in artists if artist)
