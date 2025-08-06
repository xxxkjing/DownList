import flet as ft
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
from PIL  import Image
import io
import time
import threading
import logging

# 设置日志
logging.basicConfig(filename='download.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Cookie 管理
class CookieManager:
    def __init__(self, cookie_file='cookie.txt'):
        self.cookie_file = cookie_file

    def read_cookie(self):
        try:
            with open(self.cookie_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except FileNotFoundError:
            raise Exception("未找到 cookie.txt，请运行 qr_login.py 获取 Cookie")

    def parse_cookie(self):
        cookie_text = self.read_cookie()
        cookie_ = [item.strip().split('=', 1) for item in cookie_text.split(';') if item]
        return {k.strip(): v.strip() for k, v in cookie_}

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
                    'picUrl': song['al'].get('picUrl', '')  # 使用 picUrl，默认为空字符串
                })
        return info
    except requests.RequestException as e:
        logging.error(f"歌单解析失败：{playlist_id}，错误：{str(e)}")
        return {'status': 500, 'msg': str(e)}

# 主程序
class MusicDownloaderApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "网易云音乐下载器"
        self.page.window_width = 800
        self.page.window_height = 600
        self.cookie_manager = CookieManager()
        self.download_dir = "C:\\"
        self.tracks = []
        self.current_song = None
        self.total_size = 0
        self.downloaded_size = 0
        self.start_time = 0
        self.is_paused = False
        self.download_thread = None

        # UI 组件
        self.url_input = ft.TextField(label="歌单 URL", width=500)
        self.quality_dropdown = ft.Dropdown(
            label="音质选择",
            options=[ft.dropdown.Option(q) for q in ['standard', 'exhigh', 'lossless', 'hires', 'sky', 'jyeffect', 'jymaster']],
            value="standard",
            width=200
        )
        self.lyrics_checkbox = ft.Checkbox(label="下载歌词", value=False)
        self.dir_button = ft.ElevatedButton("选择下载目录", on_click=self.select_directory)
        self.dir_text = ft.Text(f"下载目录: {self.download_dir}")
        self.parse_button = ft.ElevatedButton("解析歌单", on_click=self.parse_playlist)
        self.download_button = ft.ElevatedButton("开始下载", on_click=self.start_download, disabled=True)
        self.pause_button = ft.ElevatedButton("暂停", on_click=self.pause_download, disabled=True)
        self.resume_button = ft.ElevatedButton("继续", on_click=self.resume_download, disabled=True)
        self.cancel_button = ft.ElevatedButton("取消", on_click=self.cancel_download, disabled=True)
        self.total_progress = ft.ProgressBar(
            width=1500,
            value=0,
            color="indigo",
            bgcolor=None,
            bar_height=20
        )
        self.total_progress_text = ft.Text("总进度: 0/0")
        self.file_progress = ft.ProgressBar(
            width=1500,
            value=0,
            color="indigo",
            bgcolor=None,
            bar_height=20
        )
        self.file_progress_text = ft.Text("文件进度: 0%")
        self.speed_text = ft.Text("下载速度: 0 KB/s")
        self.song_list = ft.ListView(expand=True, spacing=10, padding=10)

        # 布局
        self.page.add(
            ft.Row([self.url_input, self.parse_button], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([self.quality_dropdown, self.lyrics_checkbox, self.dir_button], alignment=ft.MainAxisAlignment.CENTER),
            self.dir_text,
            ft.Row([self.download_button, self.pause_button, self.resume_button, self.cancel_button], alignment=ft.MainAxisAlignment.CENTER),
            ft.Column([self.total_progress_text, self.total_progress]),
            ft.Column([self.file_progress_text, self.file_progress]),
            self.speed_text,
            ft.Text("歌曲预览:"),
            self.song_list
        )

    def select_directory(self, e):
        dialog = ft.FilePicker(on_result=self.on_directory_picked)
        self.page.overlay.append(dialog)
        self.page.update()
        dialog.get_directory_path()

    def on_directory_picked(self, e: ft.FilePickerResultEvent):
        if e.path:
            self.download_dir = e.path
            self.dir_text.value = f"下载目录: {self.download_dir}"
            self.page.update()

    def parse_playlist(self, e):
        url = self.url_input.value.strip()
        if not url:
            self.page.snack_bar = ft.SnackBar(ft.Text("请输入歌单 URL"))
            self.page.snack_bar.open = True
            self.page.update()
            return

        try:
            cookies = self.cookie_manager.parse_cookie()
            playlist_id = self.extract_playlist_id(url)
            playlist_info = playlist_detail(playlist_id, cookies)
            if playlist_info['status'] != 200:
                self.page.snack_bar = ft.SnackBar(ft.Text(f"歌单解析失败：{playlist_info['msg']}"))
                self.page.snack_bar.open = True
                self.page.update()
                logging.error(f"歌单解析失败：{playlist_info['msg']}")
                return

            self.tracks = playlist_info['playlist']['tracks']
            self.song_list.controls.clear()
            for track in self.tracks:
                self.song_list.controls.append(
                    ft.Row([
                        ft.Image(src=track['picUrl'], width=50, height=50, fit=ft.ImageFit.COVER),
                        ft.Text(f"{track['name']} - {track['artists']} ({track['album']})")
                    ])
                )
            self.total_progress_text.value = f"总进度: 0/{len(self.tracks)}"
            self.download_button.disabled = False
            self.page.update()
            logging.info(f"成功解析歌单：{playlist_info['playlist']['name']}，共 {len(self.tracks)} 首歌曲")

        except Exception as e:
            self.page.snack_bar = ft.SnackBar(ft.Text(f"解析失败：{str(e)}"))
            self.page.snack_bar.open = True
            self.page.update()
            logging.error(f"解析歌单失败：{str(e)}")

    def extract_playlist_id(self, url):
        if 'music.163.com' in url or '163cn.tv' in url:
            index = url.find('id=') + 3
            return url[index:].split('&')[0]
        return url

    def start_download(self, e):
        if not self.tracks:
            self.page.snack_bar = ft.SnackBar(ft.Text("请先解析歌单"))
            self.page.snack_bar.open = True
            self.page.update()
            return

        try:
            self.cookie_manager.read_cookie()
        except Exception as e:
            self.page.snack_bar = ft.SnackBar(ft.Text(str(e)))
            self.page.snack_bar.open = True
            self.page.update()
            logging.error(str(e))
            return

        self.download_button.disabled = True
        self.pause_button.disabled = False
        self.cancel_button.disabled = False
        self.is_paused = False
        self.download_thread = threading.Thread(target=self.download_playlist, args=(
            self.url_input.value.strip(), 
            self.quality_dropdown.value, 
            self.lyrics_checkbox.value
        ), daemon=True)
        self.download_thread.start()

    def pause_download(self, e):
        self.is_paused = True
        self.pause_button.disabled = True
        self.resume_button.disabled = False
        logging.info("下载已暂停")

    def resume_download(self, e):
        self.is_paused = False
        self.pause_button.disabled = False
        self.resume_button.disabled = True
        logging.info("下载已继续")

    def cancel_download(self, e):
        self.is_paused = True
        self.download_thread = None
        self.tracks = []
        self.total_progress.value = 0
        self.file_progress.value = 0
        self.total_progress_text.value = "总进度: 0/0"
        self.file_progress_text.value = "文件进度: 0%"
        self.speed_text.value = "下载速度: 0 KB/s"
        self.song_list.controls.clear()
        self.download_button.disabled = True
        self.pause_button.disabled = True
        self.resume_button.disabled = True
        self.cancel_button.disabled = True
        self.page.update()
        logging.info("下载已取消")

    def download_playlist(self, url, quality, download_lyrics):
        cookies = self.cookie_manager.parse_cookie()
        try:
            playlist_id = self.extract_playlist_id(url)
            playlist_info = playlist_detail(playlist_id, cookies)
            if playlist_info['status'] != 200:
                self.page.snack_bar = ft.SnackBar(ft.Text(f"歌单解析失败：{playlist_info['msg']}"))
                self.page.snack_bar.open = True
                self.page.update()
                logging.error(f"歌单解析失败：{playlist_info['msg']}")
                return

            playlist_name = playlist_info['playlist']['name']
            download_dir = os.path.join(self.download_dir, playlist_name)
            os.makedirs(download_dir, exist_ok=True)

            self.total_progress.value = 0
            self.total_progress_text.value = f"总进度: 0/{len(self.tracks)}"
            self.page.update()

            for i, track in enumerate(self.tracks):
                if self.is_paused:
                    while self.is_paused:
                        time.sleep(0.1)
                        self.page.update()
                    if not self.download_thread:
                        break

                self.current_song = track['name']
                self.download_song(track, quality, download_lyrics, download_dir)
                self.total_progress.value = (i + 1) / len(self.tracks)
                self.total_progress_text.value = f"总进度: {i + 1}/{len(self.tracks)}"
                self.page.update()

            if not self.is_paused:
                self.page.snack_bar = ft.SnackBar(ft.Text(f"歌单 {playlist_name} 下载完成！"))
                self.page.snack_bar.open = True
                self.download_button.disabled = False
                self.pause_button.disabled = True
                self.resume_button.disabled = True
                self.cancel_button.disabled = True
                self.page.update()
                logging.info(f"歌单 {playlist_name} 下载完成")

        except Exception as e:
            self.page.snack_bar = ft.SnackBar(ft.Text(f"下载失败：{str(e)}"))
            self.page.snack_bar.open = True
            self.download_button.disabled = False
            self.pause_button.disabled = True
            self.resume_button.disabled = True
            self.cancel_button.disabled = True
            self.page.update()
            logging.error(f"下载失败：{str(e)}")

    def download_song(self, track, quality, download_lyrics, download_dir):
        song_id = str(track['id'])
        song_name = track['name']
        cookies = self.cookie_manager.parse_cookie()

        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            song_name = song_name.replace(char, '')
            track['artists'] = track['artists'].replace(char, '')
            track['album'] = track['album'].replace(char, '')

        try:
            song_info = name_v1(song_id)['songs'][0]
            artist_names = track['artists']
            album_name = track['album']
            cover_url = song_info['al'].get('picUrl', '')  # 使用 picUrl 作为封面 URL

            url_data = url_v1(song_id, quality, cookies)
            if not url_data.get('data') or not url_data['data'][0].get('url'):
                logging.warning(f"无法下载 {song_name}，可能是 VIP 限制或音质不可用")
                return

            song_url = url_data['data'][0]['url']
            # 先使用临时文件路径下载
            temp_file_path = os.path.join(download_dir, f"{song_name} - {artist_names}.temp")
            
            # 实际文件路径会在下载后根据内容类型确定
            file_path = os.path.join(download_dir, f"{song_name} - {artist_names}")

            if os.path.exists(file_path + '.mp3') or os.path.exists(file_path + '.flac'):
                logging.info(f"{song_name} 已存在，跳过下载")
                return

            final_file_path, file_extension = self.download_file(song_url, file_path)

            self.add_metadata(final_file_path, song_name, artist_names, album_name, cover_url, file_extension)

            if download_lyrics:
                lyric_data = lyric_v1(song_id, cookies)
                lyric = lyric_data.get('lrc', {}).get('lyric', '')
                if lyric:
                    lyric_path = os.path.join(download_dir, f"{song_name} - {artist_names}.lrc")
                    with open(lyric_path, 'w', encoding='utf-8') as f:
                        f.write(lyric)
                    logging.info(f"已下载歌词：{song_name}")

        except Exception as e:
            logging.error(f"下载 {song_name} 失败：{str(e)}")
            print(f"下载 {song_name} 失败：{str(e)}")

    def download_file(self, url, file_path):
        session = requests.Session()
        retries = requests.adapters.Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        session.mount('http://', requests.adapters.HTTPAdapter(max_retries=retries))
        session.mount('https://', requests.adapters.HTTPAdapter(max_retries=retries))
        response = session.get(url, stream=True, timeout=10)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        self.total_size = total_size
        self.downloaded_size = 0
        self.start_time = time.time()
        
        # 先下载到临时文件
        temp_file_path = file_path + '.temp'
        
        with open(temp_file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk and not self.is_paused:
                    f.write(chunk)
                    self.downloaded_size += len(chunk)
                    if total_size > 0:
                        self.file_progress.value = self.downloaded_size / total_size
                        self.file_progress_text.value = f"文件进度: {int(self.file_progress.value * 100)}% ({self.current_song})"
                    elapsed = time.time() - self.start_time
                    speed = self.downloaded_size / elapsed / 1024 if elapsed > 0 else 0
                    self.speed_text.value = f"下载速度: {speed:.2f} KB/s"
                    self.page.update()
                elif self.is_paused:
                    time.sleep(0.1)

        # 检测文件类型并重命名为正确的扩展名
        with open(temp_file_path, 'rb') as f:
            header = f.read(4)
        
        # 根据文件头判断文件类型
        file_extension = '.mp3'  # 默认mp3
        if header.startswith(b'fLaC'):  # FLAC文件的文件头
            file_extension = '.flac'
        
        # 重命名为正确的扩展名
        final_file_path = file_path + file_extension
        os.rename(temp_file_path, final_file_path)
        
        logging.info(f"成功下载文件：{final_file_path}")
        
        return final_file_path, file_extension

    def add_metadata(self, file_path, title, artist, album, cover_url, file_extension):
        try:
            if file_extension == '.flac':
                audio = FLAC(file_path)
                audio['title'] = title
                audio['artist'] = artist
                audio['album'] = album
                if cover_url:
                    cover_response = requests.get(cover_url, timeout=5)
                    cover_response.raise_for_status()
                    image = Image.open(io.BytesIO(cover_response.content))
                    image = image.convert('RGB')  # 将图像转换为 RGB 模式，避免 RGBA 问题
                    image = image.resize((300, 300))
                    img_byte_arr = io.BytesIO()
                    image.save(img_byte_arr, format='JPEG')
                    img_data = img_byte_arr.getvalue()
                    from mutagen.flac import Picture
                    picture = Picture()
                    picture.type = 3  # 封面图片类型
                    picture.mime = 'image/jpeg'
                    picture.desc = 'Front Cover'
                    picture.data = img_data
                    audio.add_picture(picture)
                audio.save()
            else:  # MP3 格式
                audio = MP3(file_path, ID3=EasyID3)
                audio['title'] = title
                audio['artist'] = artist
                audio['album'] = album
                audio.save()
                if cover_url:
                    cover_response = requests.get(cover_url, timeout=5)
                    cover_response.raise_for_status()
                    image = Image.open(io.BytesIO(cover_response.content))
                    image = image.convert('RGB')  # 将图像转换为 RGB 模式，避免 RGBA 问题
                    image = image.resize((300, 300))
                    img_byte_arr = io.BytesIO()
                    image.save(img_byte_arr, format='JPEG')
                    img_data = img_byte_arr.getvalue()
                    audio = ID3(file_path)
                    audio.add(APIC(mime='image/jpeg', data=img_data))
                    audio.save()
            logging.info(f"成功嵌入元数据：{file_path}")
        except Exception as e:
            logging.error(f"嵌入元数据失败：{file_path}，错误：{str(e)}")

def main(page: ft.Page):
    MusicDownloaderApp(page)

if __name__ == "__main__":
    ft.app(target=main)