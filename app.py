import os
import uuid
import requests
import re
import json
from flask import Flask, request, jsonify, send_file, render_template_string
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB
from mutagen.wave import WAVE
from mutagen.id3 import ID3 as ID3_WAVE

app = Flask(__name__)

DOWNLOAD_FOLDER = 'downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# --- ФУНКЦИЯ ПОЛУЧЕНИЯ ДАННЫХ БЕЗ КЛЮЧЕЙ SPOTIFY ---
def get_spotify_data_public(url):
    """
    Получает метаданные трека/альбома/плейлиста через публичный эндпоинт Spotify.
    Не требует Client ID/Secret.
    """
    try:
        # Извлекаем ID из ссылки
        match = re.search(r'(track|album|playlist)/([a-zA-Z0-9]+)', url)
        if not match:
            return None
        
        type_ = match.group(1)
        id_ = match.group(2)
        
        # Используем публичный API Spotify (undocumented, но работает для метаданных)
        # Или более надежный способ: через embed iframe data или open graph tags, 
        # но проще всего использовать spotipy с пустыми кредами или публичным токеном.
        # Однако, самый стабильный способ без регистрации - это парсинг Open Graph данных со страницы open.spotify.com
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Для треков можно попробовать получить данные через oembed или прямой запрос к api.spotify.com/v1/... 
        # Но без токена он вернет 401. 
        
        # АЛЬТЕРНАТИВА: Использовать iTunes Search API для поиска по названию, если мы его знаем? Нет, мы его не знаем.
        
        # РЕШЕНИЕ: Используем библиотеку spotipy, но с публичным клиентом, если возможно, 
        # ИЛИ просто просим пользователя ввести название, если автоматическое получение не работает без ключей.
        
        # НО! Есть способ получить данные через публичный JSON, который отдает Spotify на странице трека.
        # Это сложно парсить. 
        
        # ДАВАЙТЕ СДЕЛАЕМ ПРОЩЕ И НАДЕЖНЕЕ ДЛЯ ТЕБЯ:
        # Мы будем использовать публичный API Deezer или iTunes для поиска, ЕСЛИ пользователь введет название.
        # Но ты хочешь АВТОМАТИЧЕСКИ.
        
        # Ок, вот рабочий хак: многие сайты используют публичный прокси или кэш.
        # Но самый простой способ без ключей - это использовать библиотеку `spotdl` или аналогичную логику внутри кода.
        
        # Поскольку без ключей Spotify API недоступен, мы используем следующий трюк:
        # Мы берем ID трека и ищем его в базе данных MusicBrainz или через публичный поиск Google/YouTube напрямую?
        
        # ЛУЧШИЙ ВАРИАНТ ДЛЯ ТЕБЯ:
        # Так как без ключей Spotify API не отдаст данные надежно, мы сделаем так:
        # 1. Если ссылка на трек: пробуем получить данные через публичный endpoint (если получится).
        # 2. Если не получается: мы НЕ можем автоматически получить название без ключей.
        
        # ПОЭТОМУ: Я сделаю код, который пытается получить данные через публичный метод, 
        # а если не выходит - предлагает ввести название вручную (это единственный легальный способ без ключей).
        
        # НО! Есть библиотека `spotipy`, которая может работать с публичным токеном, если мы его получим.
        # Давай попробуем получить токен через публичный клиент Spotify (web player client).
        
        # Публичные креды веб-плеера Spotify (могут измениться, но часто работают):
        CLIENT_ID = "ac4172ea6b824f0ca3d5862cbe73bc0d" # Пример публичного ID, может не работать
        CLIENT_SECRET = "e5d944456fa943c2b9a0d8c6f8b0e8f0" # Это фейк, реальные секретны
        
        # На самом деле, без своих ключей надежно не получится. 
        # НО! Мы можем использовать парсинг страницы open.spotify.com через requests и BeautifulSoup, 
        # если Spotify не блокирует ботов. Попробуем это.
        
        response = requests.get(f"https://open.spotify.com/{type_}/{id_}", headers=headers, timeout=10)
        if response.status_code != 200:
            return None
            
        # Ищем мета-теги og:title и og:description
        # Обычно там написано: "Song Name by Artist Name | Spotify"
        content = response.text
        
        # Простой парсинг заголовка страницы
        title_match = re.search(r'<title>(.*?)</title>', content)
        if title_match:
            page_title = title_match.group(1)
            # Формат обычно: "Track Name by Artist Name | Spotify" или "Album Name by Artist Name | Spotify"
            if '|' in page_title:
                main_part = page_title.split('|')[0].strip()
                if ' by ' in main_part:
                    parts = main_part.split(' by ')
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        artist = parts[1].strip()
                        # Для альбомов/плейлистов логика сложнее, но для треков сойдет
                        
                        # Попробуем найти обложку через og:image
                        cover_match = re.search(r'meta property="og:image" content="(.*?)"', content)
                        cover_url = cover_match.group(1) if cover_match else None
                        
                        return [{
                            'title': name,
                            'artist': artist,
                            'cover_url': cover_url
                        }]
        
        return None
        
    except Exception as e:
        print(f"Public Parse Error: {e}")
        return None

def download_audio_from_youtube(query, output_path):
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'outtmpl': output_path,
        'quiet': False,  # <--- ВАЖНО: Измените на False, чтобы видеть ошибки
        'no_warnings': False,
        'default_search': 'ytsearch1',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([query])
        return True
    except Exception as e:
        print(f"!!! YOUTUBE ERROR: {e}") # <--- Добавил явный принт ошибки
        return False

def embed_metadata_wav(filepath, title, artist, cover_url):
    try:
        audio = WAVE(filepath)
        if audio.tags is None:
            audio.add_tags()
        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TPE1(encoding=3, text=artist))
        
        if cover_url:
            cover_path = filepath.replace('.wav', '_cover.jpg')
            r = requests.get(cover_url, timeout=5)
            if r.status_code == 200:
                with open(cover_path, 'wb') as f:
                    f.write(r.content)
                with open(cover_path, 'rb') as img:
                    audio.tags.add(APIC(
                        encoding=3, mime='image/jpeg', type=3, desc=u'Cover', data=img.read()
                    ))
                os.remove(cover_path)
        audio.save()
    except Exception as e:
        print(f"Metadata Error: {e}")

@app.route('/')
def index():
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Spotify -> WAV (No Keys)</title>
        <style>
            body { background: #121212; color: #fff; font-family: sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
            .container { background: #1e1e1e; padding: 40px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); width: 400px; text-align: center; }
            h1 { color: #1db954; margin-bottom: 20px; }
            input { width: 90%; padding: 12px; margin: 10px 0; border-radius: 5px; border: 1px solid #333; background: #2a2a2a; color: #fff; }
            button { background: #1db954; color: white; border: none; padding: 12px 24px; border-radius: 25px; cursor: pointer; font-weight: bold; width: 100%; margin-top: 10px; }
            button:hover { background: #1ed760; }
            button:disabled { background: #555; cursor: not-allowed; }
            #status { margin-top: 20px; font-size: 14px; color: #aaa; }
            .download-btn { display: inline-block; margin-top: 20px; padding: 10px 20px; background: #fff; color: #000; text-decoration: none; border-radius: 5px; font-weight: bold; }
            .manual-input { display: none; margin-top: 20px; border-top: 1px solid #333; padding-top: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Spotify -> WAV</h1>
            <input type="text" id="spotify_link" placeholder="Вставьте ссылку Spotify...">
            <button onclick="fetchData()" id="btn_fetch">Найти трек</button>
            
            <div id="manual_fields" class="manual-input">
                <p style="color:#ff6b6b">Не удалось получить данные автоматически. Введите вручную:</p>
                <input type="text" id="title" placeholder="Название трека">
                <input type="text" id="artist" placeholder="Исполнитель">
                <button onclick="startDownloadManual()" id="btn_download">Скачать WAV</button>
            </div>
            
            <div id="status"></div>
            <div id="result"></div>
        </div>

        <script>
            let currentTitle = '';
            let currentArtist = '';
            let currentCover = '';

            async function fetchData() {
                const link = document.getElementById('spotify_link').value;
                const btn = document.getElementById('btn_fetch');
                const status = document.getElementById('status');
                const manualFields = document.getElementById('manual_fields');
                
                if (!link) return alert('Вставьте ссылку!');
                
                btn.disabled = true;
                status.innerText = 'Получение данных из Spotify...';
                manualFields.style.display = 'none';
                document.getElementById('result').innerHTML = '';

                try {
                    const res = await fetch('/get_meta', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ url: link })
                    });
                    
                    const data = await res.json();
                    
                    if (data.status === 'success' && data.tracks && data.tracks.length > 0) {
                        const track = data.tracks[0]; // Берем первый трек для простоты
                        currentTitle = track.title;
                        currentArtist = track.artist;
                        currentCover = track.cover_url;
                        
                        status.innerText = `Найдено: ${currentTitle} - ${currentArtist}`;
                        // Автоматически начинаем скачивание
                        startDownload(currentTitle, currentArtist, currentCover);
                    } else {
                        status.innerText = 'Не удалось получить данные автоматически.';
                        manualFields.style.display = 'block';
                        btn.disabled = false;
                    }
                } catch (e) {
                    status.innerText = 'Ошибка сети';
                    btn.disabled = false;
                }
            }

            async function startDownloadManual() {
                const title = document.getElementById('title').value;
                const artist = document.getElementById('artist').value;
                if (!title || !artist) return alert('Заполните поля!');
                startDownload(title, artist, null);
            }

            async function startDownload(title, artist, cover) {
                const btn = document.getElementById('btn_fetch');
                const btn_manual = document.getElementById('btn_download');
                const status = document.getElementById('status');
                const result = document.getElementById('result');
                
                if(btn_manual) btn_manual.disabled = true;
                btn.disabled = true;
                status.innerText = 'Поиск на YouTube и конвертация...';
                result.innerHTML = '';

                try {
                    const res = await fetch('/download', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ title: title, artist: artist, cover_url: cover })
                    });
                    
                    const data = await res.json();
                    
                    if (data.status === 'processing') {
                        const checkInterval = setInterval(async () => {
                            const checkRes = await fetch(`/status/${data.task_id}`);
                            const checkData = await checkRes.json();
                            
                            if (checkData.status === 'done') {
                                clearInterval(checkInterval);
                                status.innerText = 'Готово!';
                                result.innerHTML = `<a href="/file/${checkData.filename}" class="download-btn" download>Скачать файл</a>`;
                                btn.disabled = false;
                                if(btn_manual) btn_manual.disabled = false;
                            } else if (checkData.status === 'error') {
                                clearInterval(checkInterval);
                                status.innerText = 'Ошибка: ' + checkData.message;
                                btn.disabled = false;
                                if(btn_manual) btn_manual.disabled = false;
                            } else {
                                status.innerText = checkData.message;
                            }
                        }, 1000);
                    } else {
                        status.innerText = 'Ошибка: ' + data.message;
                        btn.disabled = false;
                        if(btn_manual) btn_manual.disabled = false;
                    }
                } catch (e) {
                    status.innerText = 'Ошибка сети';
                    btn.disabled = false;
                    if(btn_manual) btn_manual.disabled = false;
                }
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

tasks = {}

@app.route('/get_meta', methods=['POST'])
def get_meta():
    data = request.json
    url = data.get('url')
    tracks = get_spotify_data_public(url)
    
    if tracks:
        return jsonify({'status': 'success', 'tracks': tracks})
    else:
        return jsonify({'status': 'error', 'message': 'Не удалось распознать'})

@app.route('/download', methods=['POST'])
def create_task():
    data = request.json
    title = data.get('title')
    artist = data.get('artist')
    cover_url = data.get('cover_url')
    
    if not title or not artist:
        return jsonify({'status': 'error', 'message': 'Нет данных'})
        
    task_id = str(uuid.uuid4())
    tasks[task_id] = {'status': 'processing', 'message': 'Начало...', 'filename': None}
    
    import threading
    thread = threading.Thread(target=process_download, args=(task_id, title, artist, cover_url))
    thread.start()
    
    return jsonify({'status': 'processing', 'task_id': task_id})

def process_download(task_id, title, artist, cover_url):
    try:
        query = f"{title} {artist} official audio"
        filename_base = f"{uuid.uuid4().hex}"
        wav_path = os.path.join(DOWNLOAD_FOLDER, f"{filename_base}.wav")
        
        tasks[task_id]['message'] = 'Загрузка аудио с YouTube...'
        success = download_audio_from_youtube(query, wav_path.replace('.wav', ''))
        
        if not success or not os.path.exists(wav_path):
            tasks[task_id] = {'status': 'error', 'message': 'Не удалось скачать аудио'}
            return
            
        tasks[task_id]['message'] = 'Обработка файла...'
        embed_metadata_wav(wav_path, title, artist, cover_url)
            
        tasks[task_id] = {'status': 'done', 'filename': f"{filename_base}.wav"}
        
    except Exception as e:
        tasks[task_id] = {'status': 'error', 'message': str(e)}

@app.route('/status/<task_id>')
def get_status(task_id):
    if task_id in tasks:
        return jsonify(tasks[task_id])
    return jsonify({'status': 'error', 'message': 'Task not found'})

@app.route('/file/<filename>')
def serve_file(filename):
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return "File not found", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
