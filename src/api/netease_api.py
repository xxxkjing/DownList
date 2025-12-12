"""
网易云音乐 API 封装模块
"""
import json
import urllib.parse
import requests
import logging
from random import randrange
from hashlib import md5
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# 音质映射：API 参数 -> 中文显示名称
QUALITY_MAP = {
    'standard': '标准',
    'exhigh': '极高',
    'lossless': '无损',
    'jyeffect': '高清臻音',
    'jymaster': '超清母带',
    'sky': '沉浸环绕声',
}

# 反向映射：中文名称 -> API 参数
QUALITY_MAP_REVERSE = {v: k for k, v in QUALITY_MAP.items()}


def post(url: str, params: str, cookies: dict) -> str:
    """
    发送 POST 请求到网易云 API
    
    Args:
        url: API 地址
        params: 加密后的参数
        cookies: Cookie 字典
        
    Returns:
        响应文本
    """
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


def hash_hex_digest(text: str) -> str:
    """计算文本的 MD5 哈希值"""
    return ''.join(hex(d)[2:].zfill(2) for d in md5(text.encode('utf-8')).digest())


def url_v1(song_id: str, level: str, cookies: dict) -> dict:
    """
    获取歌曲下载链接
    
    Args:
        song_id: 歌曲 ID
        level: 音质级别
        cookies: Cookie 字典
        
    Returns:
        包含下载链接的字典
    """
    url = "https://interface3.music.163.com/eapi/song/enhance/player/url/v1"
    AES_KEY = b"e82ckenh8dichen8"
    config = {"os": "pc", "appver": "", "osver": "", "deviceId": "pyncm!", "requestId": str(randrange(20000000, 30000000))}
    payload = {'ids': [int(song_id)], 'level': level, 'encodeType': 'flac', 'header': json.dumps(config)}
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


def name_v1(song_id: str) -> dict:
    """
    获取歌曲详细信息
    
    Args:
        song_id: 歌曲 ID
        
    Returns:
        歌曲信息字典
    """
    url = "https://interface3.music.163.com/api/v3/song/detail"
    data = {'c': json.dumps([{"id": int(song_id), "v": 0}])}
    try:
        response = requests.post(url, data=data, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"获取歌曲信息失败：{song_id}，错误：{str(e)}")
        raise


def lyric_v1(song_id: str, cookies: dict) -> dict:
    """
    获取歌曲歌词
    
    Args:
        song_id: 歌曲 ID
        cookies: Cookie 字典
        
    Returns:
        歌词数据字典
    """
    url = "https://interface3.music.163.com/api/song/lyric"
    data = {'id': song_id, 'cp': 'false', 'tv': '0', 'lv': '0', 'rv': '0', 'kv': '0', 'yv': '0', 'ytv': '0', 'yrv': '0'}
    try:
        response = requests.post(url, data=data, cookies=cookies, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"获取歌词失败：{song_id}，错误：{str(e)}")
        raise


def playlist_detail(playlist_id: str, cookies: dict) -> dict:
    """
    获取歌单详情
    
    Args:
        playlist_id: 歌单 ID
        cookies: Cookie 字典
        
    Returns:
        歌单信息字典，包含歌曲列表
    """
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
