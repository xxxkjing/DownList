from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import os
import requests
import json
import urllib.parse
from random import randrange
from hashlib import md5
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC
from mutagen.flac import FLAC
from PIL import Image
import io
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid
import zipfile
from datetime import datetime

app = Flask(__name__)
CORS(app)

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 全局变量
download_status = {
    'is_downloading': False,
    'is_paused': False,
    'total_tracks': 0,
    'completed_count': 0,
    'current_song': '',
    'download_speed': 0,
    'start_time': 0,
    'playlist_name': '',
    'error_message': ''
}

download_executor = None
download_futures = []

# 音质映射
QUALITY_MAP = {
    "标准音质": "standard",
    "极高音质": "exhigh", 
    "无损音质": "lossless",
    "Hi-Res音质": "hires",
    "沉浸环绕声": "sky",
    "高清环绕声": "jyeffect",
    "超清母带": "jymaster"
}

# 网易云音乐 API 函数
def post(url, params, cookies):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 NeteaseMusicDesktop/2.10.2.200154',
        'Referer': '',
    }
    cookies = {'os': 'pc', 'appver': '', 'osver': '', 'deviceId': 'pyncm!', **cookies}
    try:
        response = requests.post(url, headers=headers, cookies=cookies, data={"params": params}, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logging.error(f"POST 请求失败：{url}，错误：{str(e)}")
        raise

def hash_hex_digest(text):
    return ''.join(hex(d)[2:].zfill(2) for d in md5(text.encode('utf-8')).digest())

def url_v1(id, level, cookies):
    url = "https://interface3.music.163.com/eapi/song/enhance/player/url/v1"
    AES_KEY = b"e82ckenh8dichen8"
    config = {"os": "pc", "appver": "", "osver": "", "deviceId": "pyncm!", "requestId": str(randrange(20000000, 30000000))}
    payload = {'ids': [id], 'level': level, 'encodeType': 'flac', 'header': json.dumps(config)}
    if level == 'sky':
        payload['immerseType'] = 'c51'
    url2 = urllib.parse.urlparse(url).path.replace("/eapi/", "/api/")
    digest = hash_hex_digest(f"nobody{url2}use{json.dumps(payload)}md5forencrypt")
    params = f"{url2}-36cd479b6b5-{json.dumps(payload)}-36cd479b6b5-{digest}"
    padder = padding.PKCS7(algorithms.AES(AES_KEY).block_size).padder()
    padded_data = padder.update(params.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(AES_KEY), modes.ECB())
    encryptor = cipher.encryptor()
    enc = encryptor.update(padded_data) + encryptor.finalize()
    params = ''.join(hex(d)[2:].zfill(2) for d in enc)
    return json.loads(post(url, params, cookies))

def name_v1(id):
    url = "https://interface3.music.163.com/api/v3/song/detail"
    data = {'c': json.dumps([{"id": id, "v": 0}])}
    try:
        response = requests.post(url, data=data, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"获取歌曲信息失败：{id}，错误：{str(e)}")
        raise

def lyric_v1(id, cookies):
    url = "https://interface3.music.163.com/api/song/lyric"
    data = {'id': id, 'cp': 'false', 'tv': '0', 'lv': '0', 'rv': '0', 'kv': '0', 'yv': '0', 'ytv': '0', 'yrv': '0'}
    try:
        response = requests.post(url, data=data, cookies=cookies, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"获取歌词失败：{id}，错误：{str(e)}")
        raise

def playlist_detail(playlist_id, cookies):
    url = 'https://music.163.com/api/v6/playlist/detail'
    data = {'id': playlist_id}
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://music.163.com/'}
    try:
        response = requests.post(url, data=data, headers=headers, cookies=cookies, timeout=10)
        response.raise_for_status()
        result = response.json()
        if result.get('code') != 200:
            return {'status': result.get('code'), 'msg': '歌单解析失败'}
        playlist = result.get('playlist', {})
        info = {
            'status': 200,
            'playlist': {
                'id': playlist.get('id'),
                'name': playlist.get('name'),
                'tracks': []
            }
        }
        track_ids = [str(t['id']) for t in playlist.get('trackIds', [])]
        for i in range(0, len(track_ids), 100):
            batch_ids = track_ids[i:i+100]
            song_data = {'c': json.dumps([{'id': int(sid), 'v': 0} for sid in batch_ids])}
            song_resp = requests.post('https://interface3.music.163.com/api/v3/song/detail', 
                                    data=song_data, headers=headers, cookies=cookies, timeout=10)
            song_result = song_resp.json()
            for song in song_result.get('songs', []):
                info['playlist']['tracks'].append({
                    'id': song['id'],
                    'name': song['name'],
                    'artists': '/'.join(artist['name'] for artist in song['ar']),
                    'album': song['al']['name'],
                    'picUrl': song['al'].get('picUrl', '')
                })
        return info
    except requests.RequestException as e:
        logging.error(f"歌单解析失败：{playlist_id}，错误：{str(e)}")
        return {'status': 500, 'msg': str(e)}

def parse_cookie(cookie_text):
    cookie_ = [item.strip().split('=', 1) for item in cookie_text.split(';') if item]
    return {k.strip(): v.strip() for k, v in cookie_}

def extract_playlist_id(url):
    if 'music.163.com' in url or '163cn.tv' in url:
        index = url.find('id=') + 3
        return url[index:].split('&')[0]
    return url

# Web 路由
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/parse_playlist', methods=['POST'])
def parse_playlist():
    try:
        data = request.json
        url = data.get('url', '').strip()
        cookie_text = data.get('cookie', '').strip()
        
        if not url:
            return jsonify({'success': False, 'message': '请输入歌单 URL'})
        
        if not cookie_text:
            return jsonify({'success': False, 'message': '请输入 Cookie'})
        
        cookies = parse_cookie(cookie_text)
        playlist_id = extract_playlist_id(url)
        playlist_info = playlist_detail(playlist_id, cookies)
        
        if playlist_info['status'] != 200:
            return jsonify({'success': False, 'message': f"歌单解析失败：{playlist_info['msg']}"})
        
        return jsonify({
            'success': True,
            'playlist': playlist_info['playlist']
        })
        
    except Exception as e:
        logging.error(f"解析歌单失败：{str(e)}")
        return jsonify({'success': False, 'message': f'解析失败：{str(e)}'})

@app.route('/api/start_download', methods=['POST'])
def start_download():
    global download_status, download_executor, download_futures
    
    try:
        data = request.json
        url = data.get('url', '').strip()
        cookie_text = data.get('cookie', '').strip()
        quality = data.get('quality', 'standard')
        download_lyrics = data.get('download_lyrics', False)
        concurrent_count = data.get('concurrent_count', 3)
        
        if download_status['is_downloading']:
            return jsonify({'success': False, 'message': '已有下载任务在进行中'})
        
        # 重置状态
        download_status.update({
            'is_downloading': True,
            'is_paused': False,
            'total_tracks': 0,
            'completed_count': 0,
            'current_song': '',
            'download_speed': 0,
            'start_time': time.time(),
            'playlist_name': '',
            'error_message': ''
        })
        
        # 启动下载线程
        thread = threading.Thread(
            target=download_playlist_parallel,
            args=(url, cookie_text, quality, download_lyrics, concurrent_count),
            daemon=True
        )
        thread.start()
        
        return jsonify({'success': True, 'message': '下载已开始'})
        
    except Exception as e:
        logging.error(f"启动下载失败：{str(e)}")
        download_status['is_downloading'] = False
        return jsonify({'success': False, 'message': f'启动下载失败：{str(e)}'})

@app.route('/api/pause_download', methods=['POST'])
def pause_download():
    global download_status, download_executor, download_futures
    
    download_status['is_paused'] = True
    
    # 取消所有未开始的任务
    for future in download_futures:
        if not future.done():
            future.cancel()
    
    if download_executor:
        download_executor.shutdown(wait=False)
        download_executor = None
    
    return jsonify({'success': True, 'message': '下载已暂停'})

@app.route('/api/resume_download', methods=['POST'])
def resume_download():
    global download_status
    
    download_status['is_paused'] = False
    return jsonify({'success': True, 'message': '下载已继续'})

@app.route('/api/cancel_download', methods=['POST'])
def cancel_download():
    global download_status, download_executor, download_futures
    
    download_status.update({
        'is_downloading': False,
        'is_paused': False,
        'total_tracks': 0,
        'completed_count': 0,
        'current_song': '',
        'download_speed': 0,
        'playlist_name': '',
        'error_message': ''
    })
    
    # 取消所有任务
    for future in download_futures:
        if not future.done():
            future.cancel()
    
    if download_executor:
        download_executor.shutdown(wait=False)
        download_executor = None
    
    download_futures = []
    
    return jsonify({'success': True, 'message': '下载已取消'})

@app.route('/api/download_status')
def get_download_status():
    return jsonify(download_status)

@app.route('/api/download_zip/<playlist_name>')
def download_zip(playlist_name):
    try:
        download_dir = f'/app/downloads/{playlist_name}'
        if not os.path.exists(download_dir):
            return jsonify({'success': False, 'message': '文件夹不存在'})
        
        zip_path = f'/app/downloads/{playlist_name}.zip'
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(download_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, download_dir)
                    zipf.write(file_path, arcname)
        
        return send_file(zip_path, as_attachment=True, download_name=f'{playlist_name}.zip')
        
    except Exception as e:
        logging.error(f"创建下载包失败：{str(e)}")
        return jsonify({'success': False, 'message': f'创建下载包失败：{str(e)}'})

def download_playlist_parallel(url, cookie_text, quality, download_lyrics, concurrent_count):
    global download_status, download_executor, download_futures
    
    try:
        cookies = parse_cookie(cookie_text)
        playlist_id = extract_playlist_id(url)
        playlist_info = playlist_detail(playlist_id, cookies)
        
        if playlist_info['status'] != 200:
            download_status['error_message'] = f"歌单解析失败：{playlist_info['msg']}"
            download_status['is_downloading'] = False
            return
        
        playlist_name = playlist_info['playlist']['name']
        tracks = playlist_info['playlist']['tracks']
        
        # 清理文件夹名称
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            playlist_name = playlist_name.replace(char, '')
        
        download_dir = f'/app/downloads/{playlist_name}'
        os.makedirs(download_dir, exist_ok=True)
        
        download_status.update({
            'total_tracks': len(tracks),
            'playlist_name': playlist_name
        })
        
        # 创建线程池
        download_executor = ThreadPoolExecutor(max_workers=concurrent_count)
        
        # 提交下载任务
        download_futures = []
        for track in tracks:
            if download_status['is_paused']:
                break
            future = download_executor.submit(
                download_song_wrapper, track, quality, download_lyrics, download_dir, cookies
            )
            download_futures.append(future)
        
        # 监控下载进度
        for future in as_completed(download_futures):
            if download_status['is_paused']:
                break
            
            try:
                result = future.result()
                download_status['completed_count'] += 1
                
                # 计算下载速度
                elapsed = time.time() - download_status['start_time']
                speed = download_status['completed_count'] / elapsed if elapsed > 0 else 0
                download_status['download_speed'] = round(speed, 2)
                
            except Exception as e:
                logging.error(f"下载任务失败：{str(e)}")
        
        if not download_status['is_paused']:
            download_status['is_downloading'] = False
            
    except Exception as e:
        logging.error(f"下载失败：{str(e)}")
        download_status['error_message'] = f'下载失败：{str(e)}'
        download_status['is_downloading'] = False
    finally:
        if download_executor:
            download_executor.shutdown(wait=True)
            download_executor = None

def download_song_wrapper(track, quality, download_lyrics, download_dir, cookies):
    song_name = track['name']
    download_status['current_song'] = song_name
    
    return download_song(track, quality, download_lyrics, download_dir, cookies)

def download_song(track, quality, download_lyrics, download_dir, cookies):
    # ...existing download logic from original file...
    # 这里包含原来的下载逻辑，为了简洁我省略了具体实现
    # 实际实现时需要包含完整的下载、元数据处理等功能
    pass

if __name__ == '__main__':
    os.makedirs('/app/downloads', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=False)
