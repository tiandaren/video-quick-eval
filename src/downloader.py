"""
视频下载器模块
支持 Bilibili、YouTube 等平台的视频/音频下载
"""
import os
from abc import ABC, abstractmethod
from typing import Optional

import yt_dlp

from models import AudioDownloadResult, DownloadQuality
from utils import get_data_dir, extract_video_id, get_logger

logger = get_logger(__name__)

# 音频质量映射
QUALITY_MAP = {
    "fast": "32",
    "medium": "64",
    "slow": "128"
}


class Downloader(ABC):
    """下载器基类"""

    def __init__(self):
        self.quality = QUALITY_MAP.get('fast')
        self.cache_data = get_data_dir()

    @abstractmethod
    def download(
            self,
            video_url: str,
            output_dir: str = None,
            quality: DownloadQuality = "fast",
            need_video: Optional[bool] = False
    ) -> AudioDownloadResult:
        """
        下载音频

        :param video_url: 资源链接
        :param output_dir: 输出路径
        :param quality: 音频质量 fast | medium | slow
        :param need_video: 是否需要视频
        :return: AudioDownloadResult 对象
        """
        pass

    @abstractmethod
    def download_video(self, video_url: str, output_dir: Optional[str] = None) -> str:
        """
        下载视频

        :param video_url: 视频链接
        :param output_dir: 输出目录
        :return: 视频文件路径
        """
        pass


class BilibiliDownloader(Downloader):
    """Bilibili 下载器"""

    def __init__(self):
        super().__init__()
        logger.info("初始化 Bilibili 下载器")

    def download(
            self,
            video_url: str,
            output_dir: Optional[str] = None,
            quality: DownloadQuality = "fast",
            need_video: Optional[bool] = False
    ) -> AudioDownloadResult:
        """下载 Bilibili 音频"""
        if output_dir is None:
            output_dir = self.cache_data

        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': QUALITY_MAP.get(quality, '64'),
                }
            ],
            'noplaylist': True,
            'quiet': False,
        }

        logger.info(f"开始下载 Bilibili 音频: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id")
            title = info.get("title")
            duration = info.get("duration", 0)
            cover_url = info.get("thumbnail")
            audio_path = os.path.join(output_dir, f"{video_id}.mp3")

        logger.info(f"音频下载完成: {audio_path}")
        return AudioDownloadResult(
            file_path=audio_path,
            title=title,
            duration=duration,
            cover_url=cover_url,
            platform="bilibili",
            video_id=video_id,
            raw_info=info,
            video_path=None
        )

    def download_video(
            self,
            video_url: str,
            output_dir: Optional[str] = None,
    ) -> str:
        """下载 Bilibili 视频"""
        if output_dir is None:
            output_dir = self.cache_data

        os.makedirs(output_dir, exist_ok=True)
        video_id = extract_video_id(video_url, "bilibili")
        video_path = os.path.join(output_dir, f"{video_id}.mp4")

        # 检查是否已存在
        if os.path.exists(video_path):
            logger.info(f"视频已存在: {video_path}")
            return video_path

        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bv*[ext=mp4]/bestvideo+bestaudio/best',
            'outtmpl': output_path,
            'noplaylist': True,
            'quiet': False,
            'merge_output_format': 'mp4',
        }

        logger.info(f"开始下载 Bilibili 视频: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id")
            video_path = os.path.join(output_dir, f"{video_id}.mp4")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件未找到: {video_path}")

        logger.info(f"视频下载完成: {video_path}")
        return video_path


class YoutubeDownloader(Downloader):
    """YouTube 下载器"""

    def __init__(self):
        super().__init__()
        logger.info("初始化 YouTube 下载器")

    def download(
            self,
            video_url: str,
            output_dir: Optional[str] = None,
            quality: DownloadQuality = "fast",
            need_video: Optional[bool] = False
    ) -> AudioDownloadResult:
        """下载 YouTube 音频"""
        if output_dir is None:
            output_dir = self.cache_data

        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': QUALITY_MAP.get(quality, '64'),
                }
            ],
            'noplaylist': True,
            'quiet': False,
        }

        logger.info(f"开始下载 YouTube 音频: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id")
            title = info.get("title")
            duration = info.get("duration", 0)
            cover_url = info.get("thumbnail")
            audio_path = os.path.join(output_dir, f"{video_id}.mp3")

        logger.info(f"音频下载完成: {audio_path}")
        return AudioDownloadResult(
            file_path=audio_path,
            title=title,
            duration=duration,
            cover_url=cover_url,
            platform="youtube",
            video_id=video_id,
            raw_info=info,
            video_path=None
        )

    def download_video(
            self,
            video_url: str,
            output_dir: Optional[str] = None,
    ) -> str:
        """下载 YouTube 视频"""
        if output_dir is None:
            output_dir = self.cache_data

        os.makedirs(output_dir, exist_ok=True)
        video_id = extract_video_id(video_url, "youtube")
        video_path = os.path.join(output_dir, f"{video_id}.mp4")

        if os.path.exists(video_path):
            logger.info(f"视频已存在: {video_path}")
            return video_path

        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': output_path,
            'noplaylist': True,
            'quiet': False,
            'merge_output_format': 'mp4',
        }

        logger.info(f"开始下载 YouTube 视频: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id")
            video_path = os.path.join(output_dir, f"{video_id}.mp4")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件未找到: {video_path}")

        logger.info(f"视频下载完成: {video_path}")
        return video_path


# 平台下载器映射
PLATFORM_DOWNLOADERS = {
    'bilibili': BilibiliDownloader,
    'youtube': YoutubeDownloader,
}


def get_downloader(platform: str) -> Downloader:
    """
    根据平台获取下载器实例

    :param platform: 平台名称 (bilibili/youtube)
    :return: 下载器实例
    """
    downloader_cls = PLATFORM_DOWNLOADERS.get(platform.lower())
    if not downloader_cls:
        raise ValueError(f"不支持的平台: {platform}")

    return downloader_cls()
