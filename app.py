import os
import uuid
import requests
from flask import Flask, request, jsonify, send_file, render_template_string
from spotipy.oauth2 import SpotifyClientCredentials
import spotipy
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB
from mutagen.wave import WAVE
from mutagen.id3 import ID3 as ID3_WAVE

app = Flask(__name__)

# --- НАСТРОЙКИ ---
SPOTIFY_CLIENT_ID = '11fdc91fd219403c8aeea272ecb21897'
SPOTIFY_CLIENT_SECRET = 'bb1f4ca37b9d4241908661008feab7ce'
DOWNLOAD_FOLDER = 'downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Инициализация Spotify
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

def get_spotify_data(url):
    """Получает метаданные трека из Spotify"""
    try:
        # Очистка ссылки от параметров
        track_id = url.split('/')[-1].split('?')[0]
        track = sp.track(track_id)
        
        if not track:
            return None
            
        return {
            'title': track['name'],
            'artist': track['artists'][0]['name'],
            'album': track['album']['name'],
            'cover_url': track['album']['images'][0]['url'] if track['album']['images'] else None
        }
    except Exception as e:
        print(f"Spotify Error: {e}")
        return None

def download_audio_from_youtube(query, output_path):
    """Ищет и скачивает аудио с YouTube"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav', # Можно поменять на 'mp3'
            'preferredquality': '192',
        }],
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch1', # Ищем только первый результат
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([query])
        return True
    except Exception as e:
        print(f"YouTube Error: {e}")
        return False

def download_cover_image(url, path):
    """Скачивает обложку альбома"""
    if not url:
        return False
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            with open(path, 'wb') as f:
                f.write(response.content)
            return True
    except:
        return False

def embed_metadata(filepath, title, artist, album, cover_path, format='wav'):
    """Вшивает метаданные и обложку в файл"""
    try:
        if format == 'mp3':
            audio = MP3(filepath, ID3=ID3)
            if audio.tags is None:
                audio.add_tags()
            audio.tags.add(TIT2(encoding=3, text=title))
            audio.tags.add(TPE1(encoding=3, text=artist))
            audio.tags.add(TALB(encoding=3, text=album))
            
            if os.path.exists(cover_path):
                with open(cover_path, 'rb') as img:
                    audio.tags.add(APIC(
                        encoding=3, mime='image/jpeg', type=3, desc=u'Cover', data=img.read()
                    ))
            audio.save()
            
        elif format == 'wav':
            # WAV поддерживает теги ID3, но не все плееры их читают
            audio = WAVE(filepath)
            if audio.tags is None:
                audio.add_tags()
            audio.tags.add(TIT2(encoding=3, text=title))
            audio.tags.add(TPE1(encoding=3, text=artist))
            
            if os.path.exists(cover_path):
                with open(cover_path, 'rb') as img:
                    audio.tags.add(APIC(
                        encoding=3, mime='image/jpeg', type=3, desc=u'Cover', data=img.read()
                    ))
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
        <title>Spotify to WAV Downloader</title>
        <style>
            body { background: #121212; color: #fff; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .container { background: #1e1e1e; padding: 40px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); width: 400px; text-align: center; }
            input { width: 90%; padding: 12px; margin: 10px 0; border-radius: 5px; border: 1px solid #333; background: #2a2a2a; color: #fff; }
            button { background: #1db954; color: white; border: none; padding: 12px 24px; border-radius: 25px; cursor: pointer; font-weight: bold; width: 100%; margin-top: 10px; }
            button:hover { background: #1ed760; }
            button:disabled { background: #555; cursor: not-allowed; }
            #status { margin-top: 20px; font-size: 14px; color: #aaa; }
            .download-btn { display: inline-block; margin-top: 20px; padding: 10px 20px; background: #fff; color: #000; text-decoration: none; border-radius: 5px; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Spotify -> WAV</h2>
            <input type="text" id="url" placeholder="Вставьте ссылку Spotify...">
            <button onclick="startDownload()" id="btn">Скачать WAV</button>
            <div id="status"></div>
            <div id="result"></div>
        </div>
        <script>
            async function startDownload() {
                const url = document.getElementById('url').value;
                const btn = document.getElementById('btn');
                const status = document.getElementById('status');
                const result = document.getElementById('result');
                
                if (!url) return alert('Введите ссылку!');
                
                btn.disabled = true;
                status.innerText = '1. Получаем данные из Spotify...';
                result.innerHTML = '';

                try {
                    const res = await fetch('/download', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ url: url })
                    });
                    
                    const data = await res.json();
                    
                    if (data.status === 'processing') {
                        status.innerText = '2. Ищем на YouTube и конвертируем... (это может занять время)';
                        
                        // Опрос статуса
                        const checkInterval = setInterval(async () => {
                            const checkRes = await fetch(`/status/${data.task_id}`);
                            const checkData = await checkRes.json();
                            
                            if (checkData.status === 'done') {
                                clearInterval(checkInterval);
                                status.innerText = 'Готово!';
                                result.innerHTML = `<a href="/file/${checkData.filename}" class="download-btn" download>Скачать файл</a>`;
                                btn.disabled = false;
                            } else if (checkData.status === 'error') {
                                clearInterval(checkInterval);
                                status.innerText = 'Ошибка: ' + checkData.message;
                                btn.disabled = false;
                            } else {
                                status.innerText = checkData.message;
                            }
                        }, 1000);
                    } else {
                        status.innerText = 'Ошибка: ' + data.message;
                        btn.disabled = false;
                    }
                } catch (e) {
                    status.innerText = 'Ошибка сети';
                    btn.disabled = false;
                }
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

# Хранилище статусов задач (в памяти, для простоты)
tasks = {}

@app.route('/download', methods=['POST'])
def create_task():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({'status': 'error', 'message': 'Нет ссылки'})
        
    task_id = str(uuid.uuid4())
    tasks[task_id] = {'status': 'processing', 'message': 'Начало...', 'filename': None}
    
    # Запускаем обработку в фоне (в реальном проекте лучше использовать Celery/RQ)
    import threading
    thread = threading.Thread(target=process_download, args=(task_id, url))
    thread.start()
    
    return jsonify({'status': 'processing', 'task_id': task_id})

def process_download(task_id, spotify_url):
    try:
        # 1. Данные из Spotify
        tasks[task_id]['message'] = 'Получение метаданных...'
        meta = get_spotify_data(spotify_url)
        if not meta:
            tasks[task_id] = {'status': 'error', 'message': 'Трект не найден в Spotify'}
            return
            
        query = f"{meta['title']} {meta['artist']} official audio"
        filename_base = f"{uuid.uuid4().hex}"
        wav_path = os.path.join(DOWNLOAD_FOLDER, f"{filename_base}.wav")
        cover_path = os.path.join(DOWNLOAD_FOLDER, f"{filename_base}.jpg")
        
        # 2. Скачивание обложки
        tasks[task_id]['message'] = 'Загрузка обложки...'
        download_cover_image(meta['cover_url'], cover_path)
        
        # 3. Скачивание аудио с YouTube
        tasks[task_id]['message'] = 'Поиск и загрузка аудио с YouTube...'
        success = download_audio_from_youtube(query, wav_path.replace('.wav', ''))
        
        if not success or not os.path.exists(wav_path):
            tasks[task_id] = {'status': 'error', 'message': 'Не удалось скачать аудио с YouTube'}
            return
            
        # 4. Вшивание метаданных
        tasks[task_id]['message'] = 'Обработка файла...'
        embed_metadata(wav_path, meta['title'], meta['artist'], meta['album'], cover_path, 'wav')
        
        # Очистка обложки
        if os.path.exists(cover_path):
            os.remove(cover_path)
            
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
