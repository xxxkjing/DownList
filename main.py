"""
网易云音乐下载器 v2.1
应用入口文件
"""
import flet as ft
from src.ui.app import MusicDownloaderApp


def main(page: ft.Page):
    """应用主入口"""
    MusicDownloaderApp(page)


if __name__ == "__main__":
    ft.app(target=main)