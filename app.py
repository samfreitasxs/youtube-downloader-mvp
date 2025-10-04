import os
import json
import subprocess
import threading
import uuid
import time
from flask import Flask, render_template, request, send_from_directory, jsonify
from flask_caching import Cache

app = Flask(__name__)
DOWNLOAD_FOLDER = 'downloads'
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

# Garante que a pasta de downloads exista
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/get-formats', methods=['POST'])
def get_formats():
    data = request.get_json()
    url = data.get('url')

    if not url:
        return jsonify({"error": "URL não fornecida."}), 400

    try:
        # Comando para extrair todas as informações do vídeo em formato JSON
        command = ['yt-dlp', '--dump-json', url]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
        video_info = json.loads(result.stdout)

        formats_list = []
        # Filtra os formatos desejados (MP4, com vídeo e áudio)
        # YouTube para alta qualidade separa vídeo e áudio, então vamos pegar os streams de vídeo
        
        # Encontra o melhor áudio m4a (MP4 audio), priorizando original/pt/en
        best_audio = None
        preferred_langs = ['pt', 'en', 'original', None]
        # Primeiro tenta os idiomas preferidos
        for lang in preferred_langs:
            for f in video_info['formats']:
                if (
                    f.get('acodec') != 'none'
                    and f.get('vcodec') == 'none'
                    and f.get('ext') == 'm4a'
                    and (
                        f.get('language') == lang
                        or f.get('language') is None
                        or f.get('language') == ''
                        or f.get('language_preference') == lang
                        or f.get('lang') == lang
                    )
                ):
                    if best_audio is None or f.get('abr', 0) > best_audio.get('abr', 0):
                        best_audio = f
            if best_audio:
                break
        # Se não achou, pega qualquer m4a
        if not best_audio:
            for f in video_info['formats']:
                if (
                    f.get('acodec') != 'none'
                    and f.get('vcodec') == 'none'
                    and f.get('ext') == 'm4a'
                ):
                    if best_audio is None or f.get('abr', 0) > best_audio.get('abr', 0):
                        best_audio = f

        # Filtra os formatos de vídeo (acima de 360p, apenas H.264/AVC, e que tenham URL)
        formats_list = []
        resolutions_seen = set()
        for f in video_info['formats']:
            if (
                f.get('vcodec', '').startswith('avc1')  # Aceita qualquer H.264/AVC
                and f.get('acodec') == 'none'
                and f.get('ext') == 'mp4'
                and f.get('height') and f.get('height') >= 360
                and 'url' in f  # Só formatos com URL disponível
            ):
                height = f.get('height')
                if height not in resolutions_seen:
                    formats_list.append({
                        "format_id": f['format_id'],
                        "resolution": f.get('format_note', f'{height}p')
                    })
                    resolutions_seen.add(height)

        # Encontra o melhor áudio m4a (AAC), priorizando original/pt/en
        best_audio = None
        preferred_langs = ['pt', 'en', 'original', None]
        for lang in preferred_langs:
            for f in video_info['formats']:
                if (
                    f.get('acodec') == 'mp4a.40.2'  # Só AAC
                    and f.get('vcodec') == 'none'
                    and f.get('ext') == 'm4a'
                    and (
                        f.get('language') == lang
                        or f.get('language') is None
                        or f.get('language') == ''
                        or f.get('language_preference') == lang
                        or f.get('lang') == lang
                    )
                ):
                    if best_audio is None or f.get('abr', 0) > best_audio.get('abr', 0):
                        best_audio = f
            if best_audio:
                break
        # Se não achou, pega qualquer m4a AAC
        if not best_audio:
            for f in video_info['formats']:
                if (
                    f.get('acodec') == 'mp4a.40.2'
                    and f.get('vcodec') == 'none'
                    and f.get('ext') == 'm4a'
                ):
                    if best_audio is None or f.get('abr', 0) > best_audio.get('abr', 0):
                        best_audio = f

        # Lista todos os áudios m4a disponíveis
        audio_formats = []
        for f in video_info['formats']:
            if (
                f.get('acodec') != 'none'
                and f.get('vcodec') == 'none'
                and f.get('ext') == 'm4a'
                and 'url' in f
            ):
                audio_formats.append({
                    "format_id": f['format_id'],
                    "abr": f.get('abr'),
                    "language": f.get('language') or f.get('lang') or '',
                    "format_note": f.get('format_note', ''),
                    "filesize": f.get('filesize'),
                })

        # Filtra os formatos de vídeo (acima de 360p, apenas H.264/AVC, e que tenham URL)
        formats_list = []
        resolutions_seen = set()
        for f in video_info['formats']:
            if (
                f.get('vcodec', '').startswith('avc1')  # Aceita qualquer H.264/AVC
                and f.get('acodec') == 'none'
                and f.get('ext') == 'mp4'
                and f.get('height') and f.get('height') >= 360
                and 'url' in f  # Só formatos com URL disponível
            ):
                height = f.get('height')
                if height not in resolutions_seen:
                    formats_list.append({
                        "format_id": f['format_id'],
                        "resolution": f.get('format_note', f'{height}p')
                    })
                    resolutions_seen.add(height)

        if not formats_list or not audio_formats:
             return jsonify({"error": "Não foram encontrados formatos de alta qualidade para este vídeo."}), 404

        return jsonify({
            "formats": formats_list,           # lista de formatos de vídeo
            "audio_format": best_audio,        # objeto do melhor áudio
            "video_id": video_info.get("id")   # id do vídeo
        })

    except subprocess.CalledProcessError:
        return jsonify({"error": "URL inválida ou vídeo indisponível."}), 400
    except Exception as e:
        return jsonify({"error": f"Ocorreu um erro interno: {str(e)}"}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.get_json()
    url = data.get('url')
    video_format_id = data.get('video_format_id')
    audio_format_id = data.get('audio_format_id')
    
    if not all([url, video_format_id, audio_format_id]):
        return jsonify({"error": "Informações incompletas para download."}), 400

    try:
        id_process = subprocess.run(['yt-dlp', '--get-id', url], capture_output=True, text=True, check=True)
        video_id = id_process.stdout.strip()
        info_process = subprocess.run(['yt-dlp', '-j', url], capture_output=True, text=True, check=True)
        video_info = json.loads(info_process.stdout)
        height = 'video'
        for f in video_info['formats']:
            if f['format_id'] == video_format_id:
                height = f.get('height', 'video')
                break

        # Gera um task_id único
        task_id = str(uuid.uuid4())
        cache.set(task_id, 0)
        # Inicia o download em background
        thread = threading.Thread(target=background_download, args=(task_id, url, video_format_id, audio_format_id, video_id, height))
        thread.start()
        return jsonify({"task_id": task_id, "filename": f"{video_id}_{height}p.mp4"})
    except Exception as e:
        return jsonify({"error": f"Falha no download: {str(e)}"}), 500

def background_download(task_id, url, video_format_id, audio_format_id, video_id, height):
    try:
        filename = f"{video_id}_{height}p.mp4"
        output_path = os.path.join(DOWNLOAD_FOLDER, filename)
        command = [
            'yt-dlp',
            '-f', f'{video_format_id}+{audio_format_id}',
            '--merge-output-format', 'mp4',
            '--no-playlist',
            '--no-warnings',
            '-o', os.path.join(DOWNLOAD_FOLDER, '%(id)s_%(height)sp.%(ext)s'),
            url
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            if '%' in line:
                percent = None
                for part in line.split():
                    if '%' in part:
                        try:
                            percent = int(float(part.replace('%','')))
                        except:
                            pass
                if percent is not None:
                    cache.set(task_id, percent)
        process.wait()
        # Aguarda o arquivo aparecer no disco (até 10s)
        for _ in range(10):
            if os.path.exists(output_path):
                cache.set(task_id, 100)
                break
            time.sleep(1)
        else:
            cache.set(task_id, -1)
    except Exception:
        cache.set(task_id, -1)

@app.route('/api/progress/<task_id>')
def get_progress(task_id):
    percent = cache.get(task_id)
    if percent is None:
        return jsonify({"progress": 0})
    return jsonify({"progress": percent})

@app.route('/api/download-file/<filename>')
def download_file(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
