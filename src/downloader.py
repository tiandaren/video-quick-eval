"""
视频下载器模块
支持 Bilibili、YouTube 等平台的视频/音频下载,以及本地视频处理
"""
import os
import subprocess
import json
from abc import ABC, abstractmethod
from typing import Optional
from pathlib import Path

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


class LocalVideoDownloader(Downloader):
    """本地视频处理器"""

    def __init__(self):
        super().__init__()
        logger.info("初始化本地视频处理器")

    def download(
            self,
            video_url: str,
            output_dir: Optional[str] = None,
            quality: DownloadQuality = "fast",
            need_video: Optional[bool] = False
    ) -> AudioDownloadResult:
        """
        从本地视频提取音频

        :param video_url: 本地视频文件路径
        :param output_dir: 输出目录
        :param quality: 音频质量
        :param need_video: 是否需要视频(本地视频已存在,忽略此参数)
        :return: AudioDownloadResult 对象
        """
        video_path = Path(video_url)

        # 检查文件是否存在
        if not video_path.exists():
            raise FileNotFoundError(f"本地视频文件不存在: {video_path}")

        if not video_path.is_file():
            raise ValueError(f"路径不是文件: {video_path}")

        # 检查是否为视频文件
        video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.webm', '.m4v'}
        if video_path.suffix.lower() not in video_extensions:
            raise ValueError(f"不支持的视频格式: {video_path.suffix}")

        if output_dir is None:
            output_dir = self.cache_data

        os.makedirs(output_dir, exist_ok=True)

        # 生成音频文件名
        video_id = video_path.stem
        audio_path = os.path.join(output_dir, f"{video_id}.mp3")

        # 使用 ffmpeg 提取音频
        logger.info(f"从本地视频提取音频: {video_path}")

        try:
            # 使用 ffmpeg 提取音频并转换为 mp3
            bitrate = QUALITY_MAP.get(quality, '64')
            cmd = [
                'ffmpeg',
                '-i', str(video_path),
                '-vn',  # 不处理视频
                '-acodec', 'libmp3lame',
                '-ab', f'{bitrate}k',
                '-ar', '44100',
                '-y',  # 覆盖已存在的文件
                audio_path
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            logger.info(f"音频提取完成: {audio_path}")

        except subprocess.CalledProcessError as e:
            logger.error(f"音频提取失败: {e.stderr.decode('utf-8', errors='ignore')}")
            raise RuntimeError(f"FFmpeg 提取音频失败: {e}")
        except FileNotFoundError:
            raise RuntimeError("FFmpeg 未安装或不在 PATH 中,请先安装 FFmpeg")

        # 获取视频信息(时长等)
        duration = self._get_video_duration(str(video_path))
        title = video_path.stem

        return AudioDownloadResult(
            file_path=audio_path,
            title=title,
            duration=duration,
            cover_url=None,
            platform="local",
            video_id=video_id,
            raw_info={"local_path": str(video_path)},
            video_path=str(video_path)
        )

    def download_video(
            self,
            video_url: str,
            output_dir: Optional[str] = None,
    ) -> str:
        """
        本地视频不需要下载,直接返回路径

        :param video_url: 本地视频文件路径
        :param output_dir: 输出目录(忽略)
        :return: 视频文件路径
        """
        video_path = Path(video_url)

        if not video_path.exists():
            raise FileNotFoundError(f"本地视频文件不存在: {video_path}")

        logger.info(f"使用本地视频: {video_path}")
        return str(video_path)

    @staticmethod
    def _get_video_duration(video_path: str) -> int:
        """
        获取视频时长(秒)

        :param video_path: 视频文件路径
        :return: 时长(秒)
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'json',
                video_path
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            info = json.loads(result.stdout.decode('utf-8'))
            duration = float(info.get('format', {}).get('duration', 0))
            return int(duration)

        except Exception as e:
            logger.warning(f"无法获取视频时长: {e}")
            return 0


# 平台下载器映射
PLATFORM_DOWNLOADERS = {
    'bilibili': BilibiliDownloader,
    'youtube': YoutubeDownloader,
    'local': LocalVideoDownloader,
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
