"""
工具函数模块
"""
import os
import re
from typing import Set, Optional

# 命名格式常量
NAMING_FORMATS = {
    'default': '歌曲名 - 艺术家',
    'artist_first': '艺术家 - 歌曲名',
    'default_quality': '歌曲名 - 艺术家 [音质]',
    'artist_first_quality': '艺术家 - 歌曲名 [音质]'
}

# 命名格式显示名称
NAMING_FORMAT_DISPLAY = {
    'default': '歌曲名 - 艺术家',
    'artist_first': '艺术家 - 歌曲名',
    'default_quality': '歌曲名 - 艺术家 [音质]',
    'artist_first_quality': '艺术家 - 歌曲名 [音质]'
}


def sanitize_filename(filename: str) -> str:
    """
    清理文件名中的非法字符
    
    Args:
        filename: 原始文件名
        
    Returns:
        清理后的文件名
    """
    import platform
    
    # Windows 和 macOS/Linux 的非法字符略有不同
    if platform.system() == 'Windows':
        invalid_chars = '<>:"/\\|?*'
    else:  # macOS 和 Linux
        # macOS 和 Linux 主要限制 / 和 null 字符
        # 但为了兼容性，我们也移除其他可能有问题的字符
        invalid_chars = '/<>:"|?*\\'
    
    for char in invalid_chars:
        filename = filename.replace(char, '')
    
    # 移除前后空格和点（避免隐藏文件）
    filename = filename.strip().strip('.')
    
    # 如果文件名为空，使用默认名称
    if not filename:
        filename = 'untitled'
    
    return filename


def generate_filename(song_name: str, artist: str, format_key: str, extension: str, 
                      quality: str = None, quality_map: dict = None) -> str:
    """
    根据命名格式生成文件名
    
    Args:
        song_name: 歌曲名
        artist: 艺术家名
        format_key: 命名格式键值
        extension: 文件扩展名 (如 '.mp3', '.flac')
        quality: 音质参数 (如 'lossless', 'standard')
        quality_map: 音质映射字典 (如 {'lossless': '无损'})
        
    Returns:
        完整文件名
    """
    song_name = sanitize_filename(song_name)
    artist = sanitize_filename(artist)
    
    # 获取音质中文名称
    quality_name = ''
    if quality and quality_map:
        quality_name = quality_map.get(quality, quality)
    
    if format_key == 'artist_first':
        return f"{artist} - {song_name}{extension}"
    elif format_key == 'default_quality' and quality_name:
        return f"{song_name} - {artist} [{quality_name}]{extension}"
    elif format_key == 'artist_first_quality' and quality_name:
        return f"{artist} - {song_name} [{quality_name}]{extension}"
    else:
        return f"{song_name} - {artist}{extension}"


def scan_downloaded_files(directory: str) -> Set[str]:
    """
    扫描目录中已下载的音乐文件（包括子目录）
    
    Args:
        directory: 目录路径
        
    Returns:
        文件名集合（不含扩展名）
    """
    downloaded = set()
    if not os.path.exists(directory):
        return downloaded
    
    extensions = {'.mp3', '.flac'}
    # 递归扫描所有子目录
    for root, dirs, files in os.walk(directory):
        for filename in files:
            name, ext = os.path.splitext(filename)
            if ext.lower() in extensions:
                downloaded.add(name.lower())
    
    return downloaded


def is_song_downloaded(song_name: str, artist: str, downloaded_files: Set[str], 
                       naming_format: str = 'default', quality: str = None,
                       quality_map: dict = None) -> bool:
    """
    检查歌曲是否已下载
    
    匹配规则：
    - 带音质的命名格式 (xxx_quality)：需要歌曲名+艺术家+音质都匹配
    - 不带音质的命名格式：只需歌曲名+艺术家匹配（忽略文件中的音质标识）
    
    Args:
        song_name: 歌曲名
        artist: 艺术家名
        downloaded_files: 已下载文件名集合
        naming_format: 当前命名格式 ('default', 'artist_first', 'default_quality', 'artist_first_quality')
        quality: 当前选择的音质 (如 'lossless')
        quality_map: 音质映射字典 (如 {'lossless': '无损'})
        
    Returns:
        是否已下载
    """
    song_name = sanitize_filename(song_name).lower()
    artist = sanitize_filename(artist).lower()
    
    # 判断是否使用带音质的命名格式
    use_quality_naming = naming_format in ['default_quality', 'artist_first_quality']
    
    # 获取音质中文名称
    quality_name = ''
    if quality and quality_map:
        quality_name = quality_map.get(quality, quality).lower()
    
    # 构建基础匹配名（不带音质）
    base_names = [
        f"{song_name} - {artist}",  # default
        f"{artist} - {song_name}",  # artist_first
    ]
    
    # 如果使用带音质的命名格式，需要精确匹配音质
    if use_quality_naming and quality_name:
        # 构建带音质的匹配名
        quality_names = [
            f"{song_name} - {artist} [{quality_name}]",  # default_quality
            f"{artist} - {song_name} [{quality_name}]",  # artist_first_quality
        ]
        # 只匹配带当前音质的文件
        for downloaded_name in downloaded_files:
            if downloaded_name in quality_names:
                return True
        return False
    else:
        # 不带音质的命名格式：只要歌曲名和艺术家匹配就算已下载
        for downloaded_name in downloaded_files:
            # 移除文件名中的音质标识后再匹配
            base_name = re.sub(r'\s*\[[^\]]+\]\s*$', '', downloaded_name)
            if base_name in base_names or downloaded_name in base_names:
                return True
        return False


def get_pinyin_initial(text: str) -> str:
    """
    获取中文文本的拼音首字母
    
    对于非中文字符，直接返回首字符的大写形式
    
    Args:
        text: 输入文本
        
    Returns:
        拼音首字母（大写）
    """
    try:
        from pypinyin import pinyin, Style
        
        if not text:
            return '#'
        
        first_char = text[0]
        
        # 判断是否为中文字符
        if '\u4e00' <= first_char <= '\u9fff':
            result = pinyin(first_char, style=Style.FIRST_LETTER)
            if result and result[0]:
                return result[0][0].upper()
        
        # 非中文字符
        if first_char.isalpha():
            return first_char.upper()
        
        return '#'
        
    except ImportError:
        # pypinyin 未安装时，直接返回首字符
        if text and text[0].isalpha():
            return text[0].upper()
        return '#'


def sort_tracks_by_pinyin(tracks: list, downloaded_files: Set[str] = None, 
                          naming_format: str = 'default', quality: str = None,
                          quality_map: dict = None) -> list:
    """
    按拼音首字母排序歌曲列表
    
    已下载的歌曲会排到末尾
    
    Args:
        tracks: 歌曲列表
        downloaded_files: 已下载文件名集合
        naming_format: 命名格式
        quality: 音质参数
        quality_map: 音质映射字典
        
    Returns:
        排序后的歌曲列表
    """
    if downloaded_files is None:
        downloaded_files = set()
    
    def sort_key(track):
        name = track.get('name', '')
        artist = track.get('artists', '')
        is_downloaded = is_song_downloaded(name, artist, downloaded_files, naming_format, quality, quality_map)
        pinyin_initial = get_pinyin_initial(name)
        # 已下载的排在后面 (True > False)
        return (is_downloaded, pinyin_initial, name)
    
    return sorted(tracks, key=sort_key)


def sort_tracks_default(tracks: list, downloaded_files: Set[str] = None,
                        naming_format: str = 'default', quality: str = None,
                        quality_map: dict = None) -> list:
    """
    默认顺序排序（保持原顺序，但已下载的排到末尾）
    
    Args:
        tracks: 歌曲列表
        downloaded_files: 已下载文件名集合
        naming_format: 命名格式
        quality: 音质参数
        quality_map: 音质映射字典
        
    Returns:
        排序后的歌曲列表
    """
    if downloaded_files is None:
        return tracks.copy()
    
    not_downloaded = []
    downloaded = []
    
    for track in tracks:
        name = track.get('name', '')
        artist = track.get('artists', '')
        if is_song_downloaded(name, artist, downloaded_files, naming_format, quality, quality_map):
            downloaded.append(track)
        else:
            not_downloaded.append(track)
    
    return not_downloaded + downloaded


def extract_playlist_id(url: str) -> str:
    """
    从 URL 提取歌单 ID
    
    Args:
        url: 歌单 URL 或直接的歌单 ID
        
    Returns:
        歌单 ID
    """
    if 'music.163.com' in url or '163cn.tv' in url:
        match = re.search(r'id=(\d+)', url)
        if match:
            return match.group(1)
        # 尝试另一种 URL 格式
        index = url.find('id=') + 3
        if index > 2:
            return url[index:].split('&')[0]
    return url
