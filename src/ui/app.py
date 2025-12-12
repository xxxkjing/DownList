"""
Flet UI 模块 - 网易云音乐下载器界面
"""
import flet as ft
import os
import threading
import logging
import json

from src.api.netease_api import (
    QUALITY_MAP, url_v1, name_v1, lyric_v1, playlist_detail
)
from src.auth.cookie_manager import CookieManager
from src.core.downloader import Downloader
from src.utils.helpers import (
    NAMING_FORMAT_DISPLAY, sanitize_filename, generate_filename,
    scan_downloaded_files, is_song_downloaded, sort_tracks_by_pinyin,
    sort_tracks_default, extract_playlist_id
)

# 设置日志 (使用 UTF-8 编码)
log_handler = logging.FileHandler('download.log', encoding='utf-8')
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(log_handler)
logging.getLogger().setLevel(logging.INFO)

# 排序选项
SORT_OPTIONS = {
    'default': '默认顺序',
    'pinyin': '拼音排序 (A-Z)'
}


# 配置文件路径
CONFIG_FILE = 'config.json'


class MusicDownloaderApp:
    """网易云音乐下载器应用"""
    
    def __init__(self, page: ft.Page):
        """
        初始化应用
        
        Args:
            page: Flet 页面对象
        """
        self.page = page
        self.page.title = "网易云音乐下载器 v2.1"
        self.page.window.width = 950
        self.page.window.height = 750
        
        # 核心组件
        self.cookie_manager = CookieManager()
        self.downloader = Downloader()
        
        # 设置下载进度回调
        self.downloader.on_progress = self._on_download_progress
        self.downloader.on_track_progress = self._on_track_progress
        
        # 状态
        self.download_dir = self._load_download_dir()
        self.tracks = []
        self.original_tracks = []  # 保存原始顺序
        self.downloaded_files = set()
        self.download_thread = None
        
        # 选择相关
        self.selected_tracks = set()
        self.track_controls = {}
        
        # 初始化 UI
        self._init_ui()
        self._check_login_status()
    
    def _load_download_dir(self) -> str:
        """从配置文件加载下载目录"""
        import platform
        
        # 根据操作系统设置默认下载目录
        if platform.system() == 'Darwin':  # macOS
            default_dir = os.path.expanduser('~/Music')
        elif platform.system() == 'Windows':
            default_dir = 'C:\\'
        else:  # Linux
            default_dir = os.path.expanduser('~/Music')
        
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    saved_dir = config.get('download_dir', default_dir)
                    if os.path.isdir(saved_dir):
                        return saved_dir
        except Exception as e:
            logging.warning(f"加载配置文件失败: {e}")
        
        # 确保默认目录存在
        if not os.path.exists(default_dir):
            try:
                os.makedirs(default_dir, exist_ok=True)
            except:
                default_dir = os.path.expanduser('~')
        
        return default_dir
    
    def _save_download_dir(self):
        """保存下载目录到配置文件"""
        try:
            config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            config['download_dir'] = self.download_dir
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            logging.info(f"已保存下载目录: {self.download_dir}")
        except Exception as e:
            logging.error(f"保存配置文件失败: {e}")
    
    def _init_ui(self):
        """初始化 UI 组件"""
        # 顶部输入区域
        self.url_input = ft.TextField(label="歌单 URL", width=500)
        self.parse_button = ft.ElevatedButton("解析歌单", on_click=self.parse_playlist)
        
        # 设置区域
        self.quality_dropdown = ft.Dropdown(
            label="音质选择",
            options=[ft.dropdown.Option(text=QUALITY_MAP[q], key=q) for q in QUALITY_MAP.keys()],
            value="standard",
            width=200
        )
        
        self.naming_dropdown = ft.Dropdown(
            label="命名格式",
            options=[ft.dropdown.Option(text=v, key=k) for k, v in NAMING_FORMAT_DISPLAY.items()],
            value="default",
            width=230
        )
        
        self.sort_dropdown = ft.Dropdown(
            label="排序方式",
            options=[ft.dropdown.Option(text=v, key=k) for k, v in SORT_OPTIONS.items()],
            value="default",
            width=150,
            on_change=self._on_sort_change
        )
        
        self.lyrics_checkbox = ft.Checkbox(label="下载歌词", value=False)
        self.dir_button = ft.ElevatedButton("选择下载目录", on_click=self.select_directory)
        self.dir_text = ft.Text(f"下载目录: {self.download_dir}", size=12)
        
        # 登录相关
        self.login_status = ft.Text("登录状态: 检测中...", size=12, color=ft.Colors.GREY_600)
        self.login_button = ft.ElevatedButton("重新登录", on_click=self._on_login_click, visible=False)
        
        # 选择按钮
        self.select_all_button = ft.ElevatedButton("全选", on_click=self.select_all_tracks, disabled=True)
        self.deselect_all_button = ft.ElevatedButton("取消全选", on_click=self.deselect_all_tracks, disabled=True)
        self.selected_count_text = ft.Text("已选择: 0 首", size=14, weight=ft.FontWeight.BOLD)
        
        # 下载控制按钮
        self.download_button = ft.ElevatedButton("开始下载", on_click=self.start_download, disabled=True)
        self.pause_button = ft.ElevatedButton("暂停", on_click=self.pause_download, disabled=True)
        self.resume_button = ft.ElevatedButton("继续", on_click=self.resume_download, disabled=True)
        self.cancel_button = ft.ElevatedButton("取消", on_click=self.cancel_download, disabled=True)
        
        # 进度显示
        self.total_progress = ft.ProgressBar(
            width=850, value=0, color=ft.Colors.INDIGO,
            bgcolor=ft.Colors.GREY_300, bar_height=20
        )
        self.total_progress_text = ft.Text("总进度: 0/0")
        self.file_progress = ft.ProgressBar(
            width=850, value=0, color=ft.Colors.BLUE,
            bgcolor=ft.Colors.GREY_300, bar_height=15
        )
        self.file_progress_text = ft.Text("文件进度: 0%")
        self.speed_text = ft.Text("下载速度: 0 KB/s")
        
        # 歌曲列表
        self.song_list = ft.ListView(expand=True, spacing=5, padding=10)
        
        # 布局
        self.page.add(
            ft.Row([self.url_input, self.parse_button], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([
                self.quality_dropdown, 
                self.naming_dropdown,
                self.sort_dropdown,
                self.lyrics_checkbox, 
                self.dir_button
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
            ft.Row([self.dir_text, self.login_status, self.login_button], 
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(),
            ft.Row([
                self.select_all_button, 
                self.deselect_all_button, 
                self.selected_count_text
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=20),
            ft.Row([self.download_button, self.pause_button, self.resume_button, self.cancel_button], 
                   alignment=ft.MainAxisAlignment.CENTER),
            ft.Column([self.total_progress_text, self.total_progress], 
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Column([self.file_progress_text, self.file_progress], 
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            self.speed_text,
            ft.Text("歌曲列表:", size=16, weight=ft.FontWeight.BOLD),
            self.song_list
        )
    
    def _check_login_status(self):
        """检查登录状态"""
        if self.cookie_manager.cookie_exists():
            try:
                self.cookie_manager.parse_cookie()
                self.login_status.value = "登录状态: 已登录 (Cookie 有效)"
                self.login_status.color = ft.Colors.GREEN
                self.login_button.visible = True
                self.login_button.text = "重新登录"
            except Exception:
                self._show_login_required()
        else:
            self._show_login_required()
        self.page.update()
    
    def _show_login_required(self):
        """显示需要登录"""
        self.login_status.value = "登录状态: 未登录"
        self.login_status.color = ft.Colors.RED
        self.login_button.visible = True
        self.login_button.text = "登录网易云"
    
    def _on_login_click(self, e):
        """处理登录按钮点击"""
        self.login_status.value = "登录状态: 正在打开浏览器..."
        self.login_status.color = ft.Colors.ORANGE
        self.login_button.disabled = True
        self.page.update()
        
        def do_login():
            try:
                logging.info("开始浏览器登录流程...")
                success = self.cookie_manager.login_via_browser()
                if success:
                    self.login_status.value = "登录状态: 登录成功"
                    self.login_status.color = ft.Colors.GREEN
                    self.login_button.text = "重新登录"
                    self._show_snackbar("登录成功！Cookie 已保存")
                    logging.info("登录成功")
                else:
                    self.login_status.value = "登录状态: 登录失败或超时"
                    self.login_status.color = ft.Colors.RED
                    self._show_snackbar("登录失败或超时，请重试")
                    logging.warning("登录失败或超时")
            except ImportError as ex:
                error_msg = "缺少 selenium 库，请运行: pip3 install selenium"
                self.login_status.value = f"登录状态: {error_msg}"
                self.login_status.color = ft.Colors.RED
                self._show_snackbar(error_msg)
                logging.error(error_msg)
            except Exception as ex:
                error_msg = str(ex)
                # 截断过长的错误信息
                if len(error_msg) > 100:
                    display_msg = error_msg[:100] + "..."
                else:
                    display_msg = error_msg
                
                self.login_status.value = f"登录状态: 错误"
                self.login_status.color = ft.Colors.RED
                self._show_snackbar(f"登录失败: {display_msg}")
                logging.error(f"登录失败: {error_msg}")
                
                # 如果是 ChromeDriver 相关错误，提供帮助信息
                if 'chromedriver' in error_msg.lower() or 'chrome' in error_msg.lower():
                    import platform
                    if platform.system() == 'Darwin':
                        help_msg = "macOS 用户请确保已安装 Chrome 浏览器，并运行: pip3 install --upgrade selenium"
                    else:
                        help_msg = "请确保已安装 Chrome 浏览器，并运行: pip install --upgrade selenium"
                    self._show_snackbar(help_msg)
                    logging.info(help_msg)
            finally:
                self.login_button.disabled = False
                self.page.update()
        
        threading.Thread(target=do_login, daemon=True).start()
    
    def select_directory(self, e):
        """选择下载目录"""
        dialog = ft.FilePicker(on_result=self._on_directory_picked)
        self.page.overlay.append(dialog)
        self.page.update()
        dialog.get_directory_path()
    
    def _on_directory_picked(self, e: ft.FilePickerResultEvent):
        """处理目录选择结果"""
        if e.path:
            self.download_dir = e.path
            self.dir_text.value = f"下载目录: {self.download_dir}"
            # 保存配置
            self._save_download_dir()
            # 重新扫描已下载文件
            self._scan_downloaded()
            self._refresh_track_list()
            self.page.update()
    
    def _scan_downloaded(self):
        """扫描已下载文件"""
        self.downloaded_files = scan_downloaded_files(self.download_dir)
    
    def _on_sort_change(self, e):
        """处理排序方式变化"""
        self._refresh_track_list()
    
    def _refresh_track_list(self):
        """刷新歌曲列表显示"""
        if not self.original_tracks:
            return
        
        naming_format = self.naming_dropdown.value
        sort_type = self.sort_dropdown.value
        quality = self.quality_dropdown.value
        
        # 排序
        if sort_type == 'pinyin':
            self.tracks = sort_tracks_by_pinyin(
                self.original_tracks, self.downloaded_files, naming_format, quality, QUALITY_MAP
            )
        else:
            self.tracks = sort_tracks_default(
                self.original_tracks, self.downloaded_files, naming_format, quality, QUALITY_MAP
            )
        
        # 重建歌曲列表 UI
        self._build_track_list_ui()
        self.page.update()
    
    def parse_playlist(self, e):
        """解析歌单"""
        url = self.url_input.value.strip()
        if not url:
            self._show_snackbar("请输入歌单 URL")
            return
        
        try:
            self.cookie_manager.read_cookie()
        except FileNotFoundError:
            self._show_snackbar("请先登录获取 Cookie")
            return
        
        # 更新 UI 为加载状态
        self.parse_button.text = "解析中..."
        self.parse_button.disabled = True
        self.url_input.disabled = True
        self.page.update()
        
        threading.Thread(target=self._parse_playlist_thread, args=(url,), daemon=True).start()

    def _parse_playlist_thread(self, url):
        """后台解析歌单线程"""
        try:
            cookies = self.cookie_manager.parse_cookie()
            playlist_id = extract_playlist_id(url)
            
            logging.info(f"开始解析歌单 ID: {playlist_id}")
            
            playlist_info = playlist_detail(playlist_id, cookies)
            
            if playlist_info['status'] != 200:
                self._show_snackbar(f"歌单解析失败：{playlist_info['msg']}")
                logging.error(f"歌单解析失败：{playlist_info['msg']}")
                self._reset_parse_button()
                return
            
            self.original_tracks = playlist_info['playlist']['tracks']
            self._scan_downloaded()
            
            # 由于是在线程中，UI更新不需要 page.run_task，直接修改后调用 page.update 即可
            # (Flet 的 page.update 是线程安全的)
            self._refresh_track_list()
            
            self.total_progress_text.value = f"总进度: 0/{len(self.selected_tracks)}"
            self.download_button.disabled = False
            self.select_all_button.disabled = False
            self.deselect_all_button.disabled = False
            
            logging.info(f"成功解析歌单：{playlist_info['playlist']['name']}，共 {len(self.original_tracks)} 首歌曲")
            self._show_snackbar(f"成功解析歌单，共 {len(self.original_tracks)} 首歌曲")
            
        except Exception as ex:
            self._show_snackbar(f"解析失败：{str(ex)}")
            logging.error(f"解析歌单失败：{str(ex)}")
        finally:
            self._reset_parse_button()
    
    def _reset_parse_button(self):
        """重置解析按钮状态"""
        self.parse_button.text = "解析歌单"
        self.parse_button.disabled = False
        self.url_input.disabled = False
        self.page.update()
    
    def _build_track_list_ui(self):
        """构建歌曲列表 UI"""
        self.song_list.controls.clear()
        self.selected_tracks.clear()
        self.track_controls.clear()
        
        naming_format = self.naming_dropdown.value
        
        for index, track in enumerate(self.tracks):
            track_id = track['id']
            track_name = track['name']
            track_artist = track['artists']
            
            # 检查是否已下载
            is_downloaded = is_song_downloaded(
                track_name, track_artist, self.downloaded_files, naming_format,
                self.quality_dropdown.value, QUALITY_MAP
            )
            
            # 创建复选框（已下载的默认不选中）
            checkbox = ft.Checkbox(
                value=not is_downloaded,
                on_change=lambda e, tid=track_id: self._on_track_select_change(e, tid)
            )
            if not is_downloaded:
                self.selected_tracks.add(track_id)
            
            # 创建进度条和状态文本
            progress_bar = ft.ProgressBar(width=120, value=0, visible=False, bar_height=8)
            
            # 根据下载状态设置初始状态文本
            if is_downloaded:
                status_text = ft.Text("已下载", size=11, color=ft.Colors.GREEN, width=60)
            else:
                status_text = ft.Text("待下载", size=11, color=ft.Colors.GREY_600, width=60)
            
            # 存储控件引用
            self.track_controls[track_id] = {
                'checkbox': checkbox,
                'progress_bar': progress_bar,
                'status_text': status_text,
                'is_downloaded': is_downloaded
            }
            
            # 显示名称（已下载的添加标识）
            display_name = f"{track_name} (已下载)" if is_downloaded else track_name
            
            # 创建歌曲项
            song_item = ft.Container(
                content=ft.Row([
                    checkbox,
                    ft.Text(f"{index + 1}.", size=12, width=30),
                    ft.Image(src=track['picUrl'], width=45, height=45, fit=ft.ImageFit.COVER, border_radius=5) if track.get('picUrl') else ft.Container(width=45, height=45, bgcolor=ft.Colors.GREY_300),
                    ft.Column([
                        ft.Text(display_name, size=13, weight=ft.FontWeight.W_500, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, width=320),
                        ft.Text(f"{track_artist} · {track['album']}", size=11, color=ft.Colors.GREY_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, width=320),
                    ], spacing=2, expand=True),
                    ft.Column([
                        status_text,
                        progress_bar,
                    ], spacing=2, width=130, horizontal_alignment=ft.CrossAxisAlignment.END),
                ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(horizontal=10, vertical=5),
                border_radius=8,
                bgcolor=ft.Colors.GREEN_50 if is_downloaded else (ft.Colors.GREY_100 if index % 2 == 0 else ft.Colors.WHITE),
            )
            
            self.song_list.controls.append(song_item)
        
        self._update_selected_count()
    
    def _on_track_select_change(self, e, track_id):
        """处理单曲选择变化"""
        if e.control.value:
            self.selected_tracks.add(track_id)
        else:
            self.selected_tracks.discard(track_id)
        self._update_selected_count()
    
    def select_all_tracks(self, e):
        """全选所有歌曲"""
        for track_id, controls in self.track_controls.items():
            controls['checkbox'].value = True
            self.selected_tracks.add(track_id)
        self._update_selected_count()
        self.page.update()
    
    def deselect_all_tracks(self, e):
        """取消全选"""
        for track_id, controls in self.track_controls.items():
            controls['checkbox'].value = False
        self.selected_tracks.clear()
        self._update_selected_count()
        self.page.update()
    
    def _update_selected_count(self):
        """更新选中歌曲数量显示"""
        count = len(self.selected_tracks)
        self.selected_count_text.value = f"已选择: {count} 首"
        self.total_progress_text.value = f"总进度: 0/{count}"
        self.download_button.disabled = count == 0
        self.page.update()
    
    def _update_track_status(self, track_id, status, progress, color):
        """更新指定歌曲的下载状态和进度"""
        if track_id in self.track_controls:
            controls = self.track_controls[track_id]
            controls['status_text'].value = status
            controls['status_text'].color = color
            controls['progress_bar'].value = progress
            controls['progress_bar'].visible = progress > 0 or status == "下载中"
            self.page.update()
    
    def _on_download_progress(self, progress, speed, song_name):
        """下载进度回调"""
        self.file_progress.value = progress
        self.file_progress_text.value = f"文件进度: {int(progress * 100)}% ({song_name})"
        self.speed_text.value = f"下载速度: {speed:.2f} KB/s"
        self.page.update()
    
    def _on_track_progress(self, track_id, progress):
        """单曲进度回调"""
        if track_id in self.track_controls:
            controls = self.track_controls[track_id]
            controls['progress_bar'].value = progress
            controls['progress_bar'].visible = True
    
    def start_download(self, e):
        """开始下载"""
        if not self.tracks:
            self._show_snackbar("请先解析歌单")
            return
        
        if len(self.selected_tracks) == 0:
            self._show_snackbar("请至少选择一首歌曲")
            return
        
        try:
            self.cookie_manager.read_cookie()
        except Exception as ex:
            self._show_snackbar(str(ex))
            return
        
        # 重置状态
        for track_id in self.selected_tracks:
            self._update_track_status(track_id, "待下载", 0, ft.Colors.GREY_600)
        
        self.download_button.disabled = True
        self.select_all_button.disabled = True
        self.deselect_all_button.disabled = True
        self.pause_button.disabled = False
        self.cancel_button.disabled = False
        self.downloader.reset()
        
        self.download_thread = threading.Thread(
            target=self._download_playlist_thread,
            args=(self.quality_dropdown.value, self.lyrics_checkbox.value),
            daemon=True
        )
        self.download_thread.start()
    
    def _download_playlist_thread(self, quality, download_lyrics):
        """下载歌单线程"""
        cookies = self.cookie_manager.parse_cookie()
        naming_format = self.naming_dropdown.value
        
        try:
            playlist_name = "DownList_Songs"
            # 尝试获取歌单名称
            for track in self.tracks:
                if track.get('album'):
                    playlist_name = sanitize_filename(track['album'])
                    break
            
            download_dir = os.path.join(self.download_dir, playlist_name)
            os.makedirs(download_dir, exist_ok=True)
            
            selected_tracks = [t for t in self.tracks if t['id'] in self.selected_tracks]
            total_selected = len(selected_tracks)
            
            self.total_progress.value = 0
            self.total_progress_text.value = f"总进度: 0/{total_selected}"
            self.page.update()
            
            completed_count = 0
            for i, track in enumerate(selected_tracks):
                if self.downloader.is_cancelled:
                    break
                
                while self.downloader.is_paused and not self.downloader.is_cancelled:
                    import time
                    time.sleep(0.1)
                
                if self.downloader.is_cancelled:
                    break
                
                self.downloader.current_song = track['name']
                self.downloader.current_track_id = track['id']
                
                self._update_track_status(track['id'], '下载中', 0, ft.Colors.BLUE)
                
                try:
                    self._download_song(track, quality, download_lyrics, download_dir, cookies, naming_format)
                    completed_count += 1
                    self._update_track_status(track['id'], '已完成', 1.0, ft.Colors.GREEN)
                except Exception as ex:
                    self._update_track_status(track['id'], '失败', 0, ft.Colors.RED)
                    logging.error(f"下载失败: {track['name']} - {str(ex)}")
                
                self.total_progress.value = (i + 1) / total_selected
                self.total_progress_text.value = f"总进度: {i + 1}/{total_selected}"
                self.page.update()
            
            if not self.downloader.is_cancelled:
                self._show_snackbar(f"下载完成！成功 {completed_count}/{total_selected} 首")
                self._reset_download_buttons()
                logging.info(f"下载完成，成功 {completed_count}/{total_selected} 首")
        
        except Exception as e:
            self._show_snackbar(f"下载失败：{str(e)}")
            self._reset_download_buttons()
            logging.error(f"下载失败：{str(e)}")
    
    def _download_song(self, track, quality, download_lyrics, download_dir, cookies, naming_format):
        """下载单首歌曲"""
        song_id = str(track['id'])
        song_name = sanitize_filename(track['name'])
        artist_names = sanitize_filename(track['artists'])
        album_name = sanitize_filename(track['album'])
        
        song_info = name_v1(song_id)['songs'][0]
        cover_url = song_info['al'].get('picUrl', '')
        
        url_data = url_v1(song_id, quality, cookies)
        logging.info(f"API 返回数据: song={song_name}, quality={quality}, data={url_data}")
        
        if not url_data.get('data') or not url_data['data'][0].get('url'):
            logging.warning(f"无法下载 {song_name}，可能是 VIP 限制或音质不可用，API返回: {url_data}")
            raise Exception("VIP 限制或音质不可用")
        
        song_url = url_data['data'][0]['url']
        actual_level = url_data['data'][0].get('level', 'unknown')
        actual_type = url_data['data'][0].get('type', 'unknown')
        logging.info(f"下载链接: {song_url}, 实际音质: {actual_level}, 格式: {actual_type}")
        
        file_extension = '.flac' if quality in ['lossless', 'jymaster', 'jyeffect', 'sky'] else '.mp3'
        filename = generate_filename(song_name, artist_names, naming_format, file_extension, quality, QUALITY_MAP)
        file_path = os.path.join(download_dir, filename)
        
        if os.path.exists(file_path):
            logging.info(f"{song_name} 已存在，跳过下载")
            return
        
        logging.info(f"开始下载: {song_name} -> {file_path}")
        success = self.downloader.download_file(song_url, file_path, track['id'])
        if not success:
            logging.error(f"下载失败: {song_name}")
            raise Exception("下载失败")
        
        Downloader.add_metadata(file_path, song_name, artist_names, album_name, cover_url, file_extension)
        
        if download_lyrics:
            lyric_data = lyric_v1(song_id, cookies)
            lyric = lyric_data.get('lrc', {}).get('lyric', '')
            if lyric:
                lyric_filename = generate_filename(song_name, artist_names, naming_format, '.lrc', quality, QUALITY_MAP)
                lyric_path = os.path.join(download_dir, lyric_filename)
                with open(lyric_path, 'w', encoding='utf-8') as f:
                    f.write(lyric)
                logging.info(f"已下载歌词：{song_name}")
    
    def pause_download(self, e):
        """暂停下载"""
        self.downloader.pause()
        self.pause_button.disabled = True
        self.resume_button.disabled = False
        self.page.update()
    
    def resume_download(self, e):
        """继续下载"""
        self.downloader.resume()
        self.pause_button.disabled = False
        self.resume_button.disabled = True
        self.page.update()
    
    def cancel_download(self, e):
        """取消下载"""
        self.downloader.cancel()
        self._reset_download_buttons()
        
        for track_id in self.selected_tracks:
            if self.track_controls.get(track_id, {}).get('status_text', {}).value == '下载中':
                self._update_track_status(track_id, "已取消", 0, ft.Colors.ORANGE)
        
        self.total_progress.value = 0
        self.file_progress.value = 0
        self.total_progress_text.value = "总进度: 0/0"
        self.file_progress_text.value = "文件进度: 0%"
        self.speed_text.value = "下载速度: 0 KB/s"
        self.page.update()
    
    def _reset_download_buttons(self):
        """重置下载按钮状态"""
        self.download_button.disabled = False
        self.select_all_button.disabled = False
        self.deselect_all_button.disabled = False
        self.pause_button.disabled = True
        self.resume_button.disabled = True
        self.cancel_button.disabled = True
        self.page.update()
    
    def _show_snackbar(self, message: str):
        """显示提示消息"""
        self.page.snack_bar = ft.SnackBar(ft.Text(message))
        self.page.snack_bar.open = True
        self.page.update()
