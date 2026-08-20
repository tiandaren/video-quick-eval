"""轻量视频转录 CLI：yt-dlp/FFmpeg 获取音频，faster-whisper 生成转录稿。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


PROJECT_DIR = Path(__file__).resolve().parent
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".flv", ".wmv", ".webm", ".m4v"}
MODEL_SIZES = {"tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3"}

logger = logging.getLogger("video_quick_eval")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.propagate = False


def _runtime_path(value: Optional[str], env_name: str, default: str) -> Path:
    """按 CLI 参数、环境变量、默认值的顺序解析运行目录。"""
    return Path(value or os.getenv(env_name) or default).expanduser().resolve()


def default_model_dir() -> Path:
    """优先使用随包模型；否则使用用户缓存，避免写入只读安装目录。"""
    bundled = PROJECT_DIR / "models" / "whisper"
    if bundled.exists() and any(bundled.glob("whisper-*/model.bin")):
        return bundled
    if os.name == "nt":
        cache_root = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        cache_root = Path(os.getenv("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    return cache_root / "video-quick-eval" / "models" / "whisper"


def resolve_device(requested: str) -> str:
    """自动优先使用可用的 NVIDIA CUDA；无 CUDA 时安全回退到 CPU。"""
    if requested not in {"auto", "cpu", "cuda"}:
        raise ValueError(f"不支持的计算设备: {requested}")
    if requested != "auto":
        return requested
    try:
        import ctranslate2

        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception as exc:
        # 探测失败不应阻止普通电脑运行；显式 --device cuda 仍会直接暴露错误。
        logger.warning("CUDA 探测失败，将使用 CPU: %s", exc)
        return "cpu"


def detect_source_type(source: str) -> str:
    """URL 一律交给 yt-dlp；其他输入按本地文件处理。"""
    return "online" if source.lower().startswith(("http://", "https://")) else "local"


def strip_tracking_parameters(source: str) -> str:
    """移除常见跟踪参数，保留 v、p 等媒体定位参数。"""
    tracking_names = {"spm_id_from", "trackid", "vd_source"}
    parts = urlsplit(source)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key.lower() not in tracking_names and not key.lower().startswith("utm_")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _require_executable(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(f"需要 {name}，但 PATH 中未找到该程序")
    return executable


def _safe_name(value: str) -> str:
    """过滤 Windows 不允许的文件名字符，并控制文件名长度。"""
    cleaned = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff._ -]+", "_", value).strip(" ._")
    return (cleaned or "untitled")[:80]


def traditional_to_simplified(text: str) -> str:
    try:
        from opencc import OpenCC
    except ImportError:
        return text
    return OpenCC("t2s").convert(text)


def extract_audio_from_local_video(video_path: str, data_dir: Path) -> Dict[str, str]:
    """用 FFmpeg 从本地视频提取单声道 16 kHz 音频，减少 ASR 读取开销。"""
    path = Path(video_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"本地视频不存在: {path}")
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"不支持的视频格式: {path.suffix}")
    _require_executable("ffmpeg")
    data_dir.mkdir(parents=True, exist_ok=True)
    output = data_dir / f"{_safe_name(path.stem)}.mp3"
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", "-y", str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"FFmpeg 提取音频失败: {exc.stderr.strip()}") from exc
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg 未生成有效音频: {output}")
    return {"audio_path": str(output), "title": path.stem, "source_id": path.stem, "extractor": "local"}


def download_audio(source: str, data_dir: Path) -> Dict[str, str]:
    """通过 yt-dlp 下载任意受支持网站的最佳音频，并统一转为 MP3。"""
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("在线下载需要安装 yt-dlp") from exc
    _require_executable("ffmpeg")
    data_dir.mkdir(parents=True, exist_ok=True)

    # 控制重试次数，避免网络波动立即失败，也避免无限重试阻塞 Codex。
    options = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(data_dir / "%(id)s.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "48"}],
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 10,
        "extractor_retries": 3,
        "socket_timeout": 30,
        "continuedl": True,
        "concurrent_fragment_downloads": 1,
        "quiet": True,
        "no_warnings": True,
    }
    clean_source = strip_tracking_parameters(source)
    attempts = [source]
    if clean_source != source:
        attempts.append(clean_source)

    info = None
    last_error: Optional[Exception] = None
    # 仅在原 URL 失败且确实含跟踪参数时，用规范化 URL 再试一次。
    for candidate in attempts:
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(candidate, download=True)
            break
        except Exception as exc:
            last_error = exc
    if info is None:
        raise RuntimeError(f"yt-dlp 下载失败（已尝试 {len(attempts)} 次）: {last_error}") from last_error

    source_id = str(info.get("id") or "").strip()
    if not source_id:
        raise RuntimeError("yt-dlp 未返回视频 ID")
    output = data_dir / f"{source_id}.mp3"
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"下载后未找到有效音频: {output}")
    return {
        "audio_path": str(output),
        "title": str(info.get("title") or source_id),
        "source_id": source_id,
        "extractor": str(info.get("extractor_key") or info.get("extractor") or "yt-dlp"),
    }


def transcribe_audio(
    audio_path: str,
    model_size: str = "tiny",
    model_dir: Optional[Path] = None,
    cpu_threads: int = 4,
    device: str = "auto",
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """使用 faster-whisper 转录，并保留时间戳供 Codex 后续分析引用。"""
    if model_size not in MODEL_SIZES:
        raise ValueError(f"不支持的模型: {model_size}")
    path = Path(audio_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"音频不存在: {path}")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("转录需要安装 faster-whisper") from exc

    cache_dir = model_dir or _runtime_path(None, "VIDEO_QUICK_EVAL_MODEL_DIR", str(default_model_dir()))
    cache_dir.mkdir(parents=True, exist_ok=True)
    bundled = cache_dir / f"whisper-{model_size}"
    model_source = str(bundled) if (bundled / "model.bin").is_file() else model_size
    actual_device = resolve_device(device)
    compute_type = "float16" if actual_device == "cuda" else "int8"
    logger.info("加载 faster-whisper 模型: %s（%s / %s）", model_source, actual_device, compute_type)
    try:
        model = WhisperModel(
            model_source,
            device=actual_device,
            compute_type=compute_type,
            cpu_threads=max(1, cpu_threads),
            download_root=str(cache_dir),
        )
    except Exception as exc:
        if device == "auto" and actual_device == "cuda":
            # 驱动能发现显卡但 CUDA/cuDNN 运行库不可用时，仍保证默认命令可以运行。
            logger.warning("CUDA 模型加载失败，将回退到 CPU: %s", exc)
            actual_device, compute_type = "cpu", "int8"
            try:
                model = WhisperModel(
                    model_source,
                    device=actual_device,
                    compute_type=compute_type,
                    cpu_threads=max(1, cpu_threads),
                    download_root=str(cache_dir),
                )
            except Exception as cpu_exc:
                raise RuntimeError(f"无法加载 Whisper 模型 {model_size}: {cpu_exc}") from cpu_exc
        else:
            raise RuntimeError(f"无法加载 Whisper 模型 {model_size}: {exc}") from exc

    kwargs: Dict[str, Any] = {"vad_filter": True}
    if language:
        kwargs["language"] = language
    try:
        raw_segments, info = model.transcribe(str(path), **kwargs)
        segments = [
            {"start": round(float(segment.start), 3), "end": round(float(segment.end), 3), "text": segment.text.strip()}
            for segment in raw_segments
            if segment.text and segment.text.strip()
        ]
    except Exception as exc:
        raise RuntimeError(f"转录失败: {exc}") from exc

    text = traditional_to_simplified(" ".join(item["text"] for item in segments)).strip()
    if not text:
        raise RuntimeError("转录结果为空")
    return {
        "text": text,
        "language": getattr(info, "language", None),
        "duration": getattr(info, "duration", None),
        "segments": segments,
        "device": actual_device,
        "compute_type": compute_type,
    }


def _write_outputs(
    output_dir: Path,
    source: str,
    source_type: str,
    media: Dict[str, str],
    transcript: Dict[str, Any],
    model_size: str,
    elapsed: float,
) -> Dict[str, str]:
    """写出 Markdown、结构化转录和 manifest，供 Codex 直接读取。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{datetime.now():%Y%m%d_%H%M%S_%f}_{_safe_name(media['title'])}"
    markdown_path = output_dir / f"{prefix}_transcript.md"
    json_path = output_dir / f"{prefix}_transcript.json"
    manifest_path = output_dir / f"{prefix}_manifest.json"

    markdown_path.write_text(
        f"# {media['title']}\n\n- Source: {source}\n- Language: {transcript['language'] or 'unknown'}\n\n## Transcript\n\n{transcript['text']}\n",
        encoding="utf-8",
    )
    json_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
    files = {
        "transcript_markdown": str(markdown_path),
        "transcript_json": str(json_path),
        "manifest": str(manifest_path),
    }
    manifest = {
        "status": "success",
        "source": source,
        "source_type": source_type,
        "source_id": media["source_id"],
        "title": media["title"],
        "extractor": media["extractor"],
        "asr_backend": "faster-whisper",
        "model_size": model_size,
        "device": transcript["device"],
        "compute_type": transcript["compute_type"],
        "language": transcript["language"],
        "duration": transcript["duration"],
        "elapsed": round(elapsed, 3),
        "files": files,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return files


def process_video(
    source: str,
    *,
    model_size: str = "tiny",
    cpu_threads: int = 4,
    device: str = "auto",
    language: Optional[str] = None,
    output_dir: Optional[str] = None,
    data_dir: Optional[str] = None,
    model_dir: Optional[str] = None,
    keep_audio: bool = False,
) -> Dict[str, Any]:
    """完成单个视频的获取、转录和结果落盘。"""
    started = time.monotonic()
    source_type = detect_source_type(source)
    data_path = _runtime_path(data_dir, "VIDEO_QUICK_EVAL_DATA_DIR", "data")
    output_path = _runtime_path(output_dir, "VIDEO_QUICK_EVAL_OUTPUT_DIR", "output")
    model_path = _runtime_path(model_dir, "VIDEO_QUICK_EVAL_MODEL_DIR", str(default_model_dir()))
    audio_path: Optional[Path] = None
    try:
        media = extract_audio_from_local_video(source, data_path) if source_type == "local" else download_audio(source, data_path)
        audio_path = Path(media["audio_path"])
        transcript = transcribe_audio(str(audio_path), model_size, model_path, cpu_threads, device, language)
        elapsed = time.monotonic() - started
        files = _write_outputs(output_path, source, source_type, media, transcript, model_size, elapsed)
        return {
            "success": True,
            "source": source,
            "title": media["title"],
            "transcript_text": transcript["text"],
            "files": files,
            "elapsed": elapsed,
        }
    except Exception as exc:
        logger.error("处理失败 %s: %s", source, exc)
        return {"success": False, "source": source, "error": str(exc), "elapsed": time.monotonic() - started}
    finally:
        # 下载音频是中间产物；默认清理，避免 skill 长期占用磁盘。
        if audio_path and not keep_audio:
            try:
                audio_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("无法清理临时音频: %s", audio_path)


def process_batch(sources: Iterable[str], **kwargs: Any) -> List[Dict[str, Any]]:
    results = [process_video(source, **kwargs) for source in sources]
    output_dir = _runtime_path(kwargs.get("output_dir"), "VIDEO_QUICK_EVAL_OUTPUT_DIR", "output")
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / f"batch_report_{datetime.now():%Y%m%d_%H%M%S}.json"
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="用 yt-dlp/FFmpeg 获取音频，并用 faster-whisper 快速转录视频。")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--url", help="yt-dlp 支持的视频网址")
    group.add_argument("--local", help="本地视频路径")
    group.add_argument("--batch", help="批量输入文件，每行一个网址或路径")
    parser.add_argument("--model-size", default="tiny", choices=sorted(MODEL_SIZES))
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default="auto",
        help="计算设备；默认自动优先使用 CUDA，无可用 CUDA 时使用 CPU",
    )
    parser.add_argument("--language", help="语言提示，如 zh、en；默认自动识别")
    parser.add_argument("--output-dir")
    parser.add_argument("--data-dir")
    parser.add_argument("--model-dir")
    parser.add_argument("--keep-audio", action="store_true", help="保留下载或提取的音频")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    common = {
        "model_size": args.model_size,
        "cpu_threads": max(1, args.cpu_threads),
        "device": args.device,
        "language": args.language,
        "output_dir": args.output_dir,
        "data_dir": args.data_dir,
        "model_dir": args.model_dir,
        "keep_audio": args.keep_audio,
    }
    if args.batch:
        path = Path(args.batch).expanduser()
        if not path.is_file():
            print(f"批量文件不存在: {path}", file=sys.stderr)
            return 2
        sources = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
        results = process_batch(sources, **common)
    else:
        source = args.url or args.local
        if not source:
            print("请提供 --url、--local 或 --batch。", file=sys.stderr)
            return 2
        results = [process_video(source, **common)]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(result.get("success") for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
