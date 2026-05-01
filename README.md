# Downify

Minimal black-and-white web app for Spotify links.

The site parses public Spotify metadata from a track or album link, searches a
separate legal download provider, downloads matching audio on the server,
converts it to `.wav`, and shows a release page with downloads.

The bundled provider is Jamendo, intended for Creative Commons / licensed
downloads. Do not connect providers that download audio without the right to do
so.

## What It Does

- Main page: centered Spotify link input, paste button, download button.
- Track link: release page with cover, title/artists, and one `.wav` track download.
- Album link: release page with cover, title/artists, ZIP download, and tracklist.
- Album ZIP includes all downloaded `.wav` tracks plus the release cover.
- Spotify is parsed from public pages/embed pages. No Spotify Web API credentials.

## Docker Setup

Install Docker and Docker Compose on the server:

```bash
apt update
apt install docker.io docker-compose-plugin
systemctl enable --now docker
```

Create `.env`:

```bash
cd ~/downify
cp .env.example .env
nano .env
```

If `.env.example` is missing on your server, create `.env` manually:

```env
JAMENDO_CLIENT_ID=709fa152
DOWNLOAD_DIR=downloads
MAX_ALBUM_TRACKS=25
WAV_SAMPLE_RATE=44100
WAV_CHANNELS=2
SEARCH_PROVIDER=jamendo
HOST=0.0.0.0
PORT=8000
```

For production, create your own Jamendo client id:

https://developer.jamendo.com/

Run:

```bash
docker compose up -d --build
```

Logs:

```bash
docker compose logs -f
```

Open:

```text
http://SERVER_IP:8000
```

## Nginx + Domain + SSL

The production setup is:

```text
Internet -> Nginx 80/443 -> Docker app on 127.0.0.1:8000
```

Point DNS `A` record:

```text
downify.cdcult.ru -> YOUR_SERVER_IP
```

Install Nginx and Certbot:

```bash
apt update
apt install nginx certbot python3-certbot-nginx
systemctl enable --now nginx
```

Install Docker:

```bash
apt install docker.io docker-compose-plugin
systemctl enable --now docker
```

Copy the Nginx config:

```bash
cp deploy/nginx/downify.cdcult.ru.conf /etc/nginx/sites-available/downify.cdcult.ru
ln -s /etc/nginx/sites-available/downify.cdcult.ru /etc/nginx/sites-enabled/downify.cdcult.ru
nginx -t
systemctl reload nginx
```

Run the app:

```bash
docker compose up -d --build
```

Issue the SSL certificate:

```bash
certbot --nginx -d downify.cdcult.ru
```

Check renewal:

```bash
certbot renew --dry-run
```

Open:

```text
https://downify.cdcult.ru
```

Stop:

```bash
docker compose down
```

## Notes

Album tracklists are parsed from public Spotify HTML/embed HTML. If Spotify does
not include a tracklist in the public page for a specific album, Downify cannot
reliably know all tracks without Spotify API access.

WAV files are large. You can reduce file size while keeping `.wav` output:

```env
WAV_SAMPLE_RATE=16000
WAV_CHANNELS=1
```

Provider code lives in `downify/providers/`. To add another legal platform,
create a `DownloadProvider` implementation and register it in `build_provider()`
in `downify/web.py`.
