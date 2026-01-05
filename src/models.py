"""
数据模型定义
"""
from dataclasses import dataclass
from typing import List, Optional
import enum


class DownloadQuality(str, enum.Enum):
    """音频下载质量枚举"""
    fast = "fast"
    medium = "medium"
    slow = "slow"


@dataclass
class TranscriptSegment:
    """转写文本片段"""
    start: float  # 开始时间（秒）
    end: float  # 结束时间（秒）
    text: str  # 该段文字


@dataclass
class TranscriptResult:
    """转写结果"""
    language: Optional[str]  # 检测语言（如 "zh"、"en"）
    full_text: str  # 完整合并后的文本
    segments: List[TranscriptSegment]  # 分段结构
    raw: Optional[dict] = None  # 原始响应数据


@dataclass
class AudioDownloadResult:
    """音频下载结果"""
    file_path: str  # 本地音频路径
    title: str  # 视频标题
    duration: float  # 视频时长（秒）
    cover_url: Optional[str]  # 视频封面图
    platform: str  # 平台，如 "bilibili"
    video_id: str  # 唯一视频ID
    raw_info: dict  # yt-dlp 的原始 info 字典
    video_path: Optional[str] = None  # 可选视频文件路径
