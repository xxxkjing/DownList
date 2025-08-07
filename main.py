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
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import uuid  # 添加uuid模块用于生成唯一标识符
import webbrowser  # 添加浏览器模块

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
                content = f.read().strip()
                if not content:
                    raise Exception("cookie.txt 文件为空，请先登录网易云音乐获取 Cookie")
                return content
        except FileNotFoundError:
            # 创建空的cookie文件
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                f.write("")
            raise Exception("未找到 cookie.txt，已自动创建。请先登录网易云音乐获取 Cookie")

    def parse_cookie(self):
        cookie_text = self.read_cookie()
        cookie_ = [item.strip().split('=', 1) for item in cookie_text.split(';') if item]
        return {k.strip(): v.strip() for k, v in cookie_}

    def check_and_create_cookie_file(self):
        """检查cookie文件是否存在且不为空，如果不存在或为空则创建并打开浏览器"""
        try:
            if not os.path.exists(self.cookie_file):
                # 文件不存在，创建空文件
                with open(self.cookie_file, 'w', encoding='utf-8') as f:
                    f.write("")
                self._open_browser_for_login()
                return False, "cookie.txt 文件不存在，已自动创建。请在打开的浏览器中登录网易云音乐，然后复制 Cookie 到 cookie.txt 文件中。"
            
            # 文件存在，检查是否为空
            with open(self.cookie_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    self._open_browser_for_login()
                    return False, "cookie.txt 文件为空，请在打开的浏览器中登录网易云音乐，然后复制 Cookie 到 cookie.txt 文件中。"
            
            return True, "Cookie 文件检查通过"
            
        except Exception as e:
            return False, f"检查 Cookie 文件时出错：{str(e)}"

    def _open_browser_for_login(self):
        """打开默认浏览器到网易云音乐登录页面"""
        try:
            webbrowser.open('https://music.163.com')
            logging.info("已打开浏览器到网易云音乐网站")
        except Exception as e:
            logging.error(f"打开浏览器失败：{str(e)}")

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
        self.executor = None
        self.completed_count = 0
        self.progress_lock = Lock()
        self.futures = []  # 存储当前的下载任务

        # UI 组件
        self.url_input = ft.TextField(label="歌单 URL", width=500)
        
        # 音质映射字典
        self.quality_map = {
            "标准音质": "standard",
            "极高音质": "exhigh", 
            "无损音质": "lossless",
            "Hi-Res音质": "hires",
            "沉浸环绕声": "sky",
            "高清环绕声": "jyeffect",
            "超清母带": "jymaster"
        }
        
        self.quality_dropdown = ft.Dropdown(
            label="音质选择",
            options=[ft.dropdown.Option(q) for q in self.quality_map.keys()],
            value="标准音质",
            width=200
        )
        self.concurrent_slider = ft.Slider(
            min=1,
            max=10,
            divisions=9,
            value=3,
            label="并发数: {value}",
            width=200
        )
        self.concurrent_text = ft.Text("并发下载数: 3")
        self.lyrics_checkbox = ft.Checkbox(label="下载歌词", value=False)
        self.dir_button = ft.ElevatedButton("选择下载目录", on_click=self.select_directory)
        self.dir_text = ft.Text(f"下载目录: {self.download_dir}")
        
        # 添加Cookie状态显示组件
        self.cookie_status_text = ft.Text("正在检查 Cookie 状态...", color="orange")
        self.refresh_cookie_button = ft.ElevatedButton("刷新 Cookie 状态", on_click=self.check_cookie_status)
        
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
        self.file_progress_text = ft.Text("当前下载: 等待开始...")
        self.speed_text = ft.Text("平均下载速度: 0 KB/s")
        self.song_list = ft.ListView(expand=True, spacing=10, padding=10)

        # 添加并发数变化事件
        self.concurrent_slider.on_change = self.on_concurrent_change

        # 布局
        self.page.add(
            ft.Row([self.url_input, self.parse_button], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([self.quality_dropdown, self.lyrics_checkbox], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([self.concurrent_text, self.concurrent_slider], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([self.dir_button], alignment=ft.MainAxisAlignment.CENTER),
            self.dir_text,
            ft.Row([self.cookie_status_text, self.refresh_cookie_button], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([self.download_button, self.pause_button, self.resume_button, self.cancel_button], alignment=ft.MainAxisAlignment.CENTER),
            ft.Column([self.total_progress_text, self.total_progress]),
            ft.Column([self.file_progress_text, self.file_progress]),
            self.speed_text,
            ft.Text("歌曲预览:"),
            self.song_list
        )

        # 初始化时检查Cookie状态
        self.check_cookie_status(None)

    def on_concurrent_change(self, e):
        concurrent_count = int(self.concurrent_slider.value)
        self.concurrent_text.value = f"并发下载数: {concurrent_count}"
        self.page.update()

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

    def check_cookie_status(self, e):
        """检查Cookie状态"""
        is_valid, message = self.cookie_manager.check_and_create_cookie_file()
        if is_valid:
            self.cookie_status_text.value = "Cookie 状态: ✓ 正常"
            self.cookie_status_text.color = "green"
        else:
            self.cookie_status_text.value = f"Cookie 状态: ✗ {message}"
            self.cookie_status_text.color = "red"
        self.page.update()

    def parse_playlist(self, e):
        url = self.url_input.value.strip()
        if not url:
            self.page.snack_bar = ft.SnackBar(ft.Text("请输入歌单 URL"))
            self.page.snack_bar.open = True
            self.page.update()
            return

        # 解析前先检查Cookie状态
        is_valid, message = self.cookie_manager.check_and_create_cookie_file()
        if not is_valid:
            self.page.snack_bar = ft.SnackBar(ft.Text(message))
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

        # 下载前再次检查Cookie状态
        is_valid, message = self.cookie_manager.check_and_create_cookie_file()
        if not is_valid:
            self.page.snack_bar = ft.SnackBar(ft.Text(message))
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
        self.completed_count = 0
        self.start_time = time.time()
        self.futures = []
        
        # 获取选中的中文音质并转换为英文
        selected_quality_cn = self.quality_dropdown.value
        selected_quality_en = self.quality_map[selected_quality_cn]
        
        self.download_thread = threading.Thread(target=self.download_playlist_parallel, args=(
            self.url_input.value.strip(), 
            selected_quality_en,  # 使用转换后的英文值
            self.lyrics_checkbox.value
        ), daemon=True)
        self.download_thread.start()

    def pause_download(self, e):
        self.is_paused = True
        self.pause_button.disabled = True
        self.resume_button.disabled = False
        
        # 取消所有未开始的任务
        for future in self.futures:
            if not future.done():
                future.cancel()
        
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None
        
        logging.info("下载已暂停")

    def resume_download(self, e):
        if self.is_paused:
            self.is_paused = False
            self.pause_button.disabled = False
            self.resume_button.disabled = True
            
            # 获取选中的中文音质并转换为英文
            selected_quality_cn = self.quality_dropdown.value
            selected_quality_en = self.quality_map[selected_quality_cn]
            
            # 重新启动下载线程
            self.download_thread = threading.Thread(target=self.download_playlist_parallel, args=(
                self.url_input.value.strip(), 
                selected_quality_en,  # 使用转换后的英文值
                self.lyrics_checkbox.value,
                True  # 表示这是恢复下载
            ), daemon=True)
            self.download_thread.start()
            
            logging.info("下载已继续")

    def cancel_download(self, e):
        self.is_paused = True
        
        # 取消所有任务
        for future in self.futures:
            if not future.done():
                future.cancel()
        
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None
            
        self.download_thread = None
        self.tracks = []
        self.completed_count = 0
        self.futures = []
        self.total_progress.value = 0
        self.file_progress.value = 0
        self.total_progress_text.value = "总进度: 0/0"
        self.file_progress_text.value = "当前下载: 等待开始..."
        self.speed_text.value = "平均下载速度: 0 KB/s"
        self.song_list.controls.clear()
        self.download_button.disabled = True
        self.pause_button.disabled = True
        self.resume_button.disabled = True
        self.cancel_button.disabled = True
        self.page.update()
        logging.info("下载已取消")

    def download_playlist_parallel(self, url, quality, download_lyrics, is_resume=False):
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

            if not is_resume:
                self.total_progress.value = 0
                self.total_progress_text.value = f"总进度: 0/{len(self.tracks)}"
                self.page.update()

            # 创建线程池
            concurrent_count = int(self.concurrent_slider.value)
            self.executor = ThreadPoolExecutor(max_workers=concurrent_count)

            # 过滤出还没下载的歌曲
            remaining_tracks = []
            for track in self.tracks:
                if self.is_paused:
                    break
                    
                song_name = track['name']
                artist_names = track['artists']
                
                # 清理文件名
                invalid_chars = '<>:"/\\|?*'
                for char in invalid_chars:
                    song_name = song_name.replace(char, '')
                    artist_names = artist_names.replace(char, '')
                
                file_path = os.path.join(download_dir, f"{song_name} - {artist_names}")
                if not (os.path.exists(file_path + '.mp3') or os.path.exists(file_path + '.flac')):
                    remaining_tracks.append(track)

            # 提交下载任务
            self.futures = []
            for track in remaining_tracks:
                if self.is_paused:
                    break
                future = self.executor.submit(self.download_song_wrapper, track, quality, download_lyrics, download_dir)
                self.futures.append(future)

            # 监控下载进度
            for future in as_completed(self.futures):
                if self.is_paused:
                    break
                
                try:
                    result = future.result()
                    with self.progress_lock:
                        self.completed_count += 1
                        self.total_progress.value = self.completed_count / len(self.tracks)
                        self.total_progress_text.value = f"总进度: {self.completed_count}/{len(self.tracks)}"
                        
                        # 计算平均下载速度
                        elapsed = time.time() - self.start_time
                        avg_speed = self.completed_count / elapsed if elapsed > 0 else 0
                        self.speed_text.value = f"平均下载速度: {avg_speed:.2f} 首/秒"
                        
                        self.page.update()
                        
                except Exception as e:
                    logging.error(f"下载任务失败：{str(e)}")

            if not self.is_paused and self.completed_count >= len(self.tracks):
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
        finally:
            if self.executor:
                self.executor.shutdown(wait=True)
                self.executor = None

    def download_song_wrapper(self, track, quality, download_lyrics, download_dir):
        """下载单首歌曲的包装函数，用于线程池"""
        song_name = track['name']
        try:
            with self.progress_lock:
                self.file_progress_text.value = f"正在下载: {song_name}"
                self.page.update()
            
            result = self.download_song(track, quality, download_lyrics, download_dir)
            
            with self.progress_lock:
                self.file_progress_text.value = f"已完成: {song_name}"
                self.page.update()
                
            return result
        except Exception as e:
            logging.error(f"下载 {song_name} 失败：{str(e)}")
            return None

    def download_playlist(self, url, quality, download_lyrics):
        # 保留原有的串行下载方法作为备用
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
            cover_url = song_info['al'].get('picUrl', '')

            url_data = url_v1(song_id, quality, cookies)
            if not url_data.get('data') or not url_data['data'][0].get('url'):
                logging.warning(f"无法下载 {song_name}，可能是 VIP 限制或音质不可用")
                return

            song_url = url_data['data'][0]['url']
            file_path = os.path.join(download_dir, f"{song_name} - {artist_names}")

            if os.path.exists(file_path + '.mp3') or os.path.exists(file_path + '.flac'):
                logging.info(f"{song_name} 已存在，跳过下载")
                return

            final_file_path, file_extension = self.download_file(song_url, file_path)
            
            if final_file_path and file_extension:  # 确保下载成功
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
        
        try:
            response = session.get(url, stream=True, timeout=10)
            response.raise_for_status()
        except Exception as e:
            logging.error(f"下载请求失败：{str(e)}")
            raise

        total_size = int(response.headers.get('content-length', 0))
        downloaded_size = 0
        
        # 使用UUID生成唯一的临时文件名，避免多线程冲突
        unique_id = str(uuid.uuid4())[:8]
        temp_file_path = file_path + f'.temp_{unique_id}'
        
        try:
            with open(temp_file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self.is_paused:
                        # 如果暂停，直接退出下载
                        break
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
        except Exception as e:
            logging.error(f"写入文件失败：{str(e)}")
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass  # 忽略删除失败的错误
            raise

        # 如果下载被暂停，清理临时文件
        if self.is_paused:
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass  # 忽略删除失败的错误
            return None, None

        # 检测文件类型并重命名为正确的扩展名
        try:
            with open(temp_file_path, 'rb') as f:
                header = f.read(4)
            
            # 根据文件头判断文件类型
            file_extension = '.mp3'  # 默认mp3
            if header.startswith(b'fLaC'):  # FLAC文件的文件头
                file_extension = '.flac'
            
            # 重命名为正确的扩展名
            final_file_path = file_path + file_extension
            
            # 如果目标文件已存在，删除它（可能是之前下载失败的残留）
            if os.path.exists(final_file_path):
                try:
                    os.remove(final_file_path)
                except:
                    pass
            
            os.rename(temp_file_path, final_file_path)
            
            logging.info(f"成功下载文件：{final_file_path}")
            
            return final_file_path, file_extension
        except Exception as e:
            logging.error(f"处理下载文件失败：{str(e)}")
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass  # 忽略删除失败的错误
            raise

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