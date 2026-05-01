# Downify

Telegram bot for Spotify links. It reads public Spotify metadata from the link
(release/track title and cover URL), then searches a separate legal download
provider and sends the matched audio plus the cover file to the chat.

The bundled provider is Jamendo, which is intended for Creative Commons / licensed
downloads. Do not connect providers that download copyrighted audio without the
right to do so.

## Setup

```bash
python3 --version  # must be 3.10+
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

If `python3 -m venv` is missing on Ubuntu/Debian:

```bash
apt update
apt install python3 python3-venv python3-pip ffmpeg
python3 -m venv .venv
```

Fill `.env`:

- `TELEGRAM_BOT_TOKEN` from BotFather
- `JAMENDO_CLIENT_ID` from Jamendo Developer

Run:

```bash
downify-bot
```

or:

```bash
python -m downify.bot
```

## Usage

Send the bot a Spotify track or album link:

```text
https://open.spotify.com/track/...
https://open.spotify.com/album/...
```

Without Spotify Web API credentials, album links expose only public embed/page
metadata. The bot tries to parse the album tracklist from the public Spotify page.
If Spotify does not include the tracklist in the page HTML, the bot will say so.

Track links are returned as `.wav` files. Album links are returned as a `.zip`
archive containing the `.wav` files that were found on the configured legal
provider.

## Provider Notes

Provider code lives in `downify/providers/`. To add another legal platform:

1. Create a class that inherits `DownloadProvider`.
2. Implement `search(self, track: SpotifyTrack) -> ProviderTrack | None`.
3. Return a direct legal `download_url`.
4. Register it in `build_provider()` in `downify/bot.py`.
