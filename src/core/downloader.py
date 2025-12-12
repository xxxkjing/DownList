"""
下载核心逻辑模块
"""
import os
import io
import time
import logging
import requests
from PIL import Image
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC
from mutagen.flac import FLAC, Picture


class Downloader:
    """
    下载器类，封装下载状态和控制逻辑
    """
    
    def __init__(self):
        """初始化下载器"""
        self.is_paused = False
        self.is_cancelled = False
        self.total_size = 0
        self.downloaded_size = 0
        self.start_time = 0
        self.current_song = None
        self.current_track_id = None
        
        # 进度回调函数
        self.on_progress = None  # (progress, speed, song_name) -> None
        self.on_track_progress = None  # (track_id, progress) -> None
    
    def reset(self):
        """重置下载状态"""
        self.is_paused = False
        self.is_cancelled = False
        self.total_size = 0
        self.downloaded_size = 0
        self.start_time = 0
    
    def pause(self):
        """暂停下载"""
        self.is_paused = True
        logging.info("下载已暂停")
    
    def resume(self):
        """继续下载"""
        self.is_paused = False
        logging.info("下载已继续")
    
    def cancel(self):
        """取消下载"""
        self.is_cancelled = True
        self.is_paused = False
        logging.info("下载已取消")
    
    def download_file(self, url: str, file_path: str, track_id: int = None) -> bool:
        """
        下载文件
        
        Args:
            url: 文件下载链接
            file_path: 保存路径
            track_id: 歌曲 ID（用于进度回调）
            
        Returns:
            是否下载成功
        """
        session = requests.Session()
        retries = requests.adapters.Retry(
            total=3, 
            backoff_factor=1, 
            status_forcelist=[429, 500, 502, 503, 504]
        )
        session.mount('http://', requests.adapters.HTTPAdapter(max_retries=retries))
        session.mount('https://', requests.adapters.HTTPAdapter(max_retries=retries))
        
        try:
            response = session.get(url, stream=True, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            logging.error(f"下载请求失败：{str(e)}")
            return False
        
        total_size = int(response.headers.get('content-length', 0))
        self.total_size = total_size
        self.downloaded_size = 0
        self.start_time = time.time()
        
        try:
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self.is_cancelled:
                        return False
                    
                    while self.is_paused and not self.is_cancelled:
                        time.sleep(0.1)
                    
                    if self.is_cancelled:
                        return False
                    
                    if chunk:
                        f.write(chunk)
                        self.downloaded_size += len(chunk)
                        
                        if total_size > 0:
                            progress = self.downloaded_size / total_size
                            elapsed = time.time() - self.start_time
                            speed = self.downloaded_size / elapsed / 1024 if elapsed > 0 else 0
                            
                            # 调用进度回调
                            if self.on_progress:
                                self.on_progress(progress, speed, self.current_song)
                            if self.on_track_progress and track_id:
                                self.on_track_progress(track_id, progress)
            
            logging.info(f"成功下载文件：{file_path}")
            return True
            
        except Exception as e:
            logging.error(f"下载文件失败：{str(e)}")
            return False
    
    @staticmethod
    def add_metadata(file_path: str, title: str, artist: str, album: str, 
                     cover_url: str, file_extension: str) -> bool:
        """
        为音频文件嵌入元数据
        
        Args:
            file_path: 文件路径
            title: 歌曲名
            artist: 艺术家
            album: 专辑名
            cover_url: 封面图片 URL
            file_extension: 文件扩展名
            
        Returns:
            是否成功
        """
        try:
            # 下载封面图片
            cover_data = None
            if cover_url:
                try:
                    cover_response = requests.get(cover_url, timeout=5)
                    cover_response.raise_for_status()
                    image = Image.open(io.BytesIO(cover_response.content))
                    image = image.convert('RGB')
                    image = image.resize((300, 300))
                    img_byte_arr = io.BytesIO()
                    image.save(img_byte_arr, format='JPEG')
                    cover_data = img_byte_arr.getvalue()
                except Exception as e:
                    logging.warning(f"下载封面失败：{str(e)}")
            
            if file_extension == '.flac':
                audio = FLAC(file_path)
                audio['title'] = title
                audio['artist'] = artist
                audio['album'] = album
                if cover_data:
                    picture = Picture()
                    picture.type = 3  # 封面图片类型
                    picture.mime = 'image/jpeg'
                    picture.desc = 'Front Cover'
                    picture.data = cover_data
                    audio.add_picture(picture)
                audio.save()
            else:  # MP3 格式
                audio = MP3(file_path, ID3=EasyID3)
                audio['title'] = title
                audio['artist'] = artist
                audio['album'] = album
                audio.save()
                if cover_data:
                    audio = ID3(file_path)
                    audio.add(APIC(mime='image/jpeg', data=cover_data))
                    audio.save()
            
            logging.info(f"成功嵌入元数据：{file_path}")
            return True
            
        except Exception as e:
            logging.error(f"嵌入元数据失败：{file_path}，错误：{str(e)}")
            return False
