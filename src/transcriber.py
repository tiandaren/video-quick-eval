"""
音频转写模块
支持 Whisper 模型进行音频转文字
"""
import os
from abc import ABC, abstractmethod
from pathlib import Path

from faster_whisper import WhisperModel
from modelscope import snapshot_download

from models import TranscriptSegment, TranscriptResult
from utils import get_logger, get_model_dir, is_cuda_available, is_torch_installed

logger = get_logger(__name__)

# Whisper 模型映射（使用 ModelScope 镜像）
MODEL_MAP = {
    "tiny": "pengzhendong/faster-whisper-tiny",
    'base': 'pengzhendong/faster-whisper-base',
    'small': 'pengzhendong/faster-whisper-small',
    'medium': 'pengzhendong/faster-whisper-medium',
    'large-v1': 'pengzhendong/faster-whisper-large-v1',
    'large-v2': 'pengzhendong/faster-whisper-large-v2',
    'large-v3': 'pengzhendong/faster-whisper-large-v3',
    'large-v3-turbo': 'pengzhendong/faster-whisper-large-v3-turbo',
}


class Transcriber(ABC):
    """转写器基类"""

    @abstractmethod
    def transcript(self, file_path: str) -> TranscriptResult:
        """
        转写音频文件

        :param file_path: 音频路径
        :return: TranscriptResult 对象
        """
        pass


class WhisperTranscriber(Transcriber):
    """Whisper 转写器"""

    def __init__(
            self,
            model_size: str = "base",
            device: str = 'cpu',
            compute_type: str = None,
            cpu_threads: int = 1,
    ):
        """
        初始化 Whisper 转写器

        :param model_size: 模型大小 (tiny/base/small/medium/large-v3等)
        :param device: 设备 (cpu/cuda)
        :param compute_type: 计算类型 (float16/int8等)
        :param cpu_threads: CPU 线程数
        """
        # 设备检测
        if device == 'cpu' or device is None:
            self.device = 'cpu'
        else:
            self.device = "cuda" if self._is_cuda() else "cpu"
            if device == 'cuda' and self.device == 'cpu':
                logger.warning('没有 CUDA，使用 CPU 进行计算')

        self.compute_type = compute_type or ("float16" if self.device == "cuda" else "int8")

        # 模型路径
        model_dir = get_model_dir("whisper")
        model_path = os.path.join(model_dir, f"whisper-{model_size}")

        # 下载模型（如果不存在）
        if not Path(model_path).exists():
            logger.info(f"模型 whisper-{model_size} 不存在，开始下载...")
            repo_id = MODEL_MAP.get(model_size)
            if not repo_id:
                raise ValueError(f"不支持的模型大小: {model_size}")

            model_path = snapshot_download(
                repo_id,
                local_dir=model_path,
            )
            logger.info("模型下载完成")

        # 加载模型
        logger.info(f"加载 Whisper 模型: {model_size}, 设备: {self.device}")
        self.model = WhisperModel(
            model_size_or_path=model_path,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=cpu_threads,
            download_root=model_dir
        )
        logger.info("Whisper 模型加载完成")

    @staticmethod
    def _is_cuda() -> bool:
        """检查 CUDA 是否可用"""
        try:
            if is_cuda_available():
                logger.info("CUDA 可用，使用 GPU")
                return True
            elif is_torch_installed():
                logger.info("只装了 torch，但没有 CUDA，用 CPU")
                return False
            else:
                logger.warning("还没有安装 torch，请先安装")
                return False
        except ImportError:
            return False

    def transcript(self, file_path: str) -> TranscriptResult:
        """
        转写音频文件

        :param file_path: 音频文件路径
        :return: TranscriptResult 对象
        """
        try:
            logger.info(f"开始转写音频: {file_path}")
            segments_raw, info = self.model.transcribe(file_path)

            segments = []
            full_text = ""

            for seg in segments_raw:
                text = seg.text.strip()
                full_text += text + " "
                segments.append(TranscriptSegment(
                    start=seg.start,
                    end=seg.end,
                    text=text
                ))

            result = TranscriptResult(
                language=info.language,
                full_text=full_text.strip(),
                segments=segments,
                raw=None  # 原始 info 对象不可序列化，这里设为 None
            )

            logger.info(f"转写完成，语言: {info.language}, 片段数: {len(segments)}")
            return result

        except Exception as e:
            logger.error(f"转写失败：{e}")
            raise


def get_transcriber(
        transcriber_type: str = "whisper",
        model_size: str = "base",
        device: str = "cpu"
) -> Transcriber:
    """
    获取转写器实例

    :param transcriber_type: 转写器类型 (目前只支持 whisper)
    :param model_size: 模型大小
    :param device: 设备
    :return: 转写器实例
    """
    if transcriber_type.lower() == "whisper":
        return WhisperTranscriber(model_size=model_size, device=device)
    else:
        raise ValueError(f"不支持的转写器类型: {transcriber_type}")
