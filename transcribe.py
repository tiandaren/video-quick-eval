"""
视频转写工具 - 增强版（支持大模型文本整合）
- 快速转写视频为文本
- 自动调用大模型进行文本优化整合
- 支持 OpenAI、Anthropic、国内大模型等
- 显示每个阶段的耗时
- 支持多提示词处理
- 支持批量处理
- 支持本地视频文件
"""
import os
import sys
import json
import logging
import time
import argparse
import subprocess
from pathlib import Path
from typing import Optional, List
from datetime import datetime

import yt_dlp
from faster_whisper import WhisperModel
from modelscope import snapshot_download

# ==================== 配置 ====================
OUTPUT_DIR = Path("output")
DATA_DIR = Path("data")
MODEL_DIR = Path("models/whisper")
PROMPTS_DIR = Path("prompts")
CONFIG_FILE = Path("config.json")

OUTPUT_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
MODEL_DIR.mkdir(exist_ok=True)
PROMPTS_DIR.mkdir(exist_ok=True)
Path("logs").mkdir(exist_ok=True)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/app.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# B站搜索模块
try:
    from src.bilibili_search import search_bilibili_videos, format_duration, format_play_count
    BILIBILI_SEARCH_AVAILABLE = True
except ImportError:
    BILIBILI_SEARCH_AVAILABLE = False
    logger.warning("B站搜索模块不可用，请安装: pip install bilibili-api-python")

# ==================== 工具函数 ====================
def format_time(seconds: float) -> str:
    """格式化时间显示"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}分{secs:.0f}秒"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}小时{minutes}分"

def detect_platform(url: str) -> str:
    """检测视频平台"""
    # 先检查是否为本地文件
    if os.path.exists(url) or (not url.startswith('http://') and not url.startswith('https://')):
        return 'Local'

    url_lower = url.lower()
    if 'bilibili.com' in url_lower or 'b23.tv' in url_lower:
        return 'Bilibili'
    elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return 'YouTube'
    else:
        return 'Unknown'

# ==================== 提示词管理 ====================
def list_available_prompts() -> List[str]:
    """列出所有可用的提示词"""
    prompts = []
    for file in PROMPTS_DIR.glob("*.md"):
        if file.name != "README.md":
            # 检查文件是否为空
            if file.stat().st_size > 0:
                # 检查是否包含必需的占位符
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if content.strip():  # 文件不为空
                            prompts.append(file.stem)
                except Exception as e:
                    logger.warning(f"无法读取提示词文件 {file}: {e}")
    return sorted(prompts)

def load_prompt(prompt_name: str = "evaluation") -> str:
    """从 prompts 文件夹加载提示词"""
    prompt_file = PROMPTS_DIR / f"{prompt_name}.md"

    if not prompt_file.exists():
        logger.warning(f"提示词文件不存在: {prompt_file}")
        logger.warning(f"可用的提示词: {', '.join(list_available_prompts())}")
        logger.warning("使用默认提示词")
        return """请优化以下文本，去除冗余，重构逻辑结构：

{transcript_text}"""

    with open(prompt_file, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    # 检查文件是否为空
    if not content:
        logger.error(f"提示词文件为空: {prompt_file}")
        return None

    # 检查是否包含必需的占位符
    if '{transcript_text}' not in content:
        logger.warning(f"提示词文件缺少 {{transcript_text}} 占位符: {prompt_file}")
        logger.warning("将在末尾自动添加占位符")
        content += "\n\n{transcript_text}"

    return content

# ==================== 配置管理 ====================
def load_config() -> dict:
    """加载配置文件"""
    if not CONFIG_FILE.exists():
        logger.warning(f"配置文件不存在: {CONFIG_FILE}")
        logger.warning("请复制 config.example.json 为 config.json 并填入 API key")
        return {}

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# ==================== 繁简转换 ====================
def traditional_to_simplified(text: str) -> str:
    """繁体转简体"""
    try:
        from opencc import OpenCC
        cc = OpenCC('t2s')
        return cc.convert(text)
    except ImportError:
        logger.warning("未安装 opencc-python-reimplemented，跳过繁简转换")
        return text

# ==================== 视频下载 ====================
def download_audio(video_url: str) -> tuple[str, str]:
    """下载视频音频"""
    start_time = time.time()
    logger.info(f"开始下载音频: {video_url}")

    output_template = str(DATA_DIR / "%(id)s.%(ext)s")

    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': output_template,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '64',
        }],
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        video_id = info.get("id")
        title = info.get("title", "未知标题")
        audio_path = str(DATA_DIR / f"{video_id}.mp3")

    elapsed = time.time() - start_time
    logger.info(f"音频下载完成: {title} (耗时: {format_time(elapsed)})")
    return audio_path, title

def extract_audio_from_local_video(video_path: str, quality: str = "fast") -> tuple[str, str]:
    """从本地视频提取音频"""
    start_time = time.time()
    logger.info(f"从本地视频提取音频: {video_path}")

    # 检查文件是否存在
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"本地视频文件不存在: {video_path}")

    # 检查是否为视频文件
    video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.webm', '.m4v'}
    video_path_obj = Path(video_path)
    if video_path_obj.suffix.lower() not in video_extensions:
        raise ValueError(f"不支持的视频格式: {video_path_obj.suffix}")

    # 生成音频文件名
    title = video_path_obj.stem
    audio_path = str(DATA_DIR / f"{title}.mp3")

    # 音频质量映射
    quality_map = {
        "fast": "32",
        "medium": "64",
        "slow": "128"
    }
    bitrate = quality_map.get(quality, '64')

    try:
        # 使用 ffmpeg 提取音频并转换为 mp3
        cmd = [
            'ffmpeg',
            '-i', video_path,
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

        elapsed = time.time() - start_time
        logger.info(f"音频提取完成: {title} (耗时: {format_time(elapsed)})")
        return audio_path, title

    except subprocess.CalledProcessError as e:
        logger.error(f"音频提取失败: {e.stderr.decode('utf-8', errors='ignore')}")
        raise RuntimeError(f"FFmpeg 提取音频失败: {e}")
    except FileNotFoundError:
        raise RuntimeError("FFmpeg 未安装或不在 PATH 中,请先安装 FFmpeg")


# ==================== 音频转写 ====================
def transcribe_audio(
    audio_path: str,
    model_size: str = "tiny",
    cpu_threads: int = 4
) -> str:
    """转写音频为文本"""
    start_time = time.time()
    model_path = MODEL_DIR / f"whisper-{model_size}"

    # 下载模型（如果不存在）
    if not model_path.exists():
        logger.info(f"下载 Whisper {model_size} 模型...")
        model_map = {
            "tiny": "pengzhendong/faster-whisper-tiny",
            "base": "pengzhendong/faster-whisper-base",
            "small": "pengzhendong/faster-whisper-small",
        }
        repo_id = model_map.get(model_size)
        if not repo_id:
            raise ValueError(f"不支持的模型: {model_size}")

        download_start = time.time()
        snapshot_download(repo_id, local_dir=str(model_path))
        download_elapsed = time.time() - download_start
        logger.info(f"模型下载完成 (耗时: {format_time(download_elapsed)})")

    # 加载模型
    logger.info(f"加载 Whisper 模型 ({model_size})...")
    load_start = time.time()
    model = WhisperModel(
        model_size_or_path=str(model_path),
        device="cpu",
        compute_type="int8",
        cpu_threads=cpu_threads
    )
    load_elapsed = time.time() - load_start
    logger.info(f"模型加载完成 (耗时: {format_time(load_elapsed)})")

    # 转写
    logger.info("开始转写音频...")
    transcribe_start = time.time()
    segments_generator, info = model.transcribe(audio_path, language="zh")

    full_text = ""
    segment_count = 0
    for segment in segments_generator:
        full_text += segment.text.strip() + " "
        segment_count += 1

    full_text = full_text.strip()
    transcribe_elapsed = time.time() - transcribe_start
    logger.info(f"转写完成: {segment_count} 段 (耗时: {format_time(transcribe_elapsed)})")

    # 繁简转换
    logger.info("繁简转换...")
    convert_start = time.time()
    full_text = traditional_to_simplified(full_text)
    convert_elapsed = time.time() - convert_start
    logger.info(f"繁简转换完成 (耗时: {format_time(convert_elapsed)})")

    total_elapsed = time.time() - start_time
    logger.info(f"转写总耗时: {format_time(total_elapsed)}, 共 {len(full_text)} 字符")
    return full_text

# ==================== 大模型文本优化 ====================
def optimize_text_with_llm(text: str, config: dict, prompt_name: str = "evaluation") -> Optional[str]:
    """使用大模型优化文本"""
    if not config or 'llm' not in config:
        logger.warning("未配置大模型，跳过文本优化")
        return None

    llm_config = config['llm']
    provider = llm_config.get('provider', 'openai')

    logger.info(f"使用 {provider} 和提示词 '{prompt_name}' 进行文本优化...")

    try:
        if provider == 'openai':
            return _optimize_with_openai(text, llm_config, prompt_name)
        elif provider == 'anthropic':
            return _optimize_with_anthropic(text, llm_config, prompt_name)
        else:
            logger.error(f"不支持的提供商: {provider}")
            return None
    except Exception as e:
        logger.error(f"文本优化失败: {e}")
        return None

def _optimize_with_openai(text: str, config: dict, prompt_name: str) -> str:
    """使用 OpenAI API 优化文本"""
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("未安装 openai 库，请运行: pip install openai")
        return None

    start_time = time.time()

    client = OpenAI(
        api_key=config.get('api_key'),
        base_url=config.get('base_url', 'https://api.openai.com/v1')
    )

    # 加载提示词模板
    prompt_template = load_prompt(prompt_name)
    prompt = prompt_template.format(transcript_text=text)

    try:
        response = client.chat.completions.create(
            model=config.get('model', 'gpt-4o-mini'),
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=config.get('temperature', 0.3),
            max_tokens=config.get('max_tokens', 4000)
        )

        # 处理不同的响应格式
        if hasattr(response, 'choices'):
            optimized_text = response.choices[0].message.content
        elif isinstance(response, dict):
            optimized_text = response.get('choices', [{}])[0].get('message', {}).get('content', '')
        elif isinstance(response, str):
            if response.strip().startswith('<!doctype') or response.strip().startswith('<html'):
                logger.error("API 返回了 HTML 页面而不是 JSON 响应")
                return None
            optimized_text = response
        else:
            logger.error(f"未知的响应格式: {type(response)}")
            return None

        if not optimized_text:
            logger.error("API 返回空内容")
            return None

        if optimized_text.strip().startswith('<!doctype') or optimized_text.strip().startswith('<html'):
            logger.error("API 返回了 HTML 页面而不是文本内容")
            return None

        elapsed = time.time() - start_time
        logger.info(f"文本优化完成 (耗时: {format_time(elapsed)})")
        return optimized_text

    except Exception as e:
        logger.error(f"API 调用失败: {e}")
        if hasattr(e, 'response'):
            logger.error(f"HTTP 状态码: {getattr(e.response, 'status_code', 'unknown')}")
        return None

def _optimize_with_anthropic(text: str, config: dict, prompt_name: str) -> str:
    """使用 Anthropic API 优化文本"""
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.error("未安装 anthropic 库，请运行: pip install anthropic")
        return None

    start_time = time.time()
    client = Anthropic(api_key=config.get('api_key'))

    prompt_template = load_prompt(prompt_name)
    prompt = prompt_template.format(transcript_text=text)

    response = client.messages.create(
        model=config.get('model', 'claude-3-5-sonnet-20241022'),
        max_tokens=config.get('max_tokens', 4000),
        temperature=config.get('temperature', 0.3),
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    optimized_text = response.content[0].text
    elapsed = time.time() - start_time
    logger.info(f"文本优化完成 (耗时: {format_time(elapsed)})")
    return optimized_text

# ==================== 主函数 ====================
def process_video(
    video_url: str,
    model_size: str = "tiny",
    cpu_threads: int = 4,
    enable_llm_optimization: bool = True,
    prompt_names: List[str] = None
) -> dict:
    """处理视频：下载 + 转写 + 优化"""
    total_start = time.time()

    # 检测平台
    platform = detect_platform(video_url)

    print("\n" + "=" * 60)
    print("视频转写工具（增强版 - 支持大模型优化）")
    print(f"平台: {platform}")
    print("=" * 60 + "\n")

    # 加载配置
    config = load_config()

    # 如果没有指定提示词，使用空列表（由调用方决定默认行为）
    if prompt_names is None:
        prompt_names = []

    # 1. 下载音频或从本地视频提取音频
    if platform == "Local":
        print(f"📁 步骤 1: 从本地视频提取音频...")
        try:
            audio_path, title = extract_audio_from_local_video(video_url)
        except Exception as e:
            logger.error(f"音频提取失败: {e}")
            return {"success": False, "error": str(e), "video_url": video_url, "platform": platform}
    else:
        print(f"📥 步骤 1: 下载音频 ({platform})...")
        try:
            audio_path, title = download_audio(video_url)
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return {"success": False, "error": str(e), "video_url": video_url, "platform": platform}

    # 2. 转写音频
    print("\n🎤 步骤 2: 转写音频...")
    try:
        transcript_text = transcribe_audio(audio_path, model_size, cpu_threads)
    except Exception as e:
        logger.error(f"转写失败: {e}")
        return {"success": False, "error": str(e), "video_url": video_url, "title": title}

    # 3. 大模型优化（可选，支持多提示词链式处理）
    optimized_texts = {}
    formatted_text = transcript_text  # 默认使用原始转写

    if enable_llm_optimization and prompt_names:
        print(f"\n🤖 步骤 3: 大模型优化 (使用 {len(prompt_names)} 个提示词)...")

        # 检查是否有 format 提示词，如果有则优先处理
        if "format" in prompt_names:
            print(f"   - 使用提示词: format (格式化转录稿)")

            # 先检查提示词是否有效
            prompt_template = load_prompt("format")
            if prompt_template:
                formatted_text = optimize_text_with_llm(transcript_text, config, "format")
                if formatted_text:
                    optimized_texts["format"] = formatted_text
                    print(f"     ✓ 格式化完成，后续提示词将使用格式化后的文本")
                else:
                    logger.warning("格式化失败，后续提示词将使用原始转写")
                    formatted_text = transcript_text
            else:
                logger.warning("format 提示词无效，跳过")

            # 从列表中移除 format，避免重复处理
            prompt_names = [p for p in prompt_names if p != "format"]

        # 处理其他提示词（使用格式化后的文本）
        for prompt_name in prompt_names:
            print(f"   - 使用提示词: {prompt_name}")

            # 先检查提示词是否有效
            prompt_template = load_prompt(prompt_name)
            if not prompt_template:
                logger.warning(f"跳过无效的提示词: {prompt_name}")
                continue

            # 使用格式化后的文本
            optimized_text = optimize_text_with_llm(formatted_text, config, prompt_name)
            if optimized_text:
                optimized_texts[prompt_name] = optimized_text

    # 4. 保存结果
    print("\n💾 步骤 4: 保存结果...")
    save_start = time.time()

    # 生成时间戳（格式：YYMMDD）
    timestamp = datetime.now().strftime("%y%m%d")

    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_'))[:50]

    # 保存原始转写
    raw_file = OUTPUT_DIR / f"{timestamp}_{safe_title}_raw.md"
    with open(raw_file, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write(f"**视频链接**: {video_url}\n\n")
        f.write("---\n\n")
        f.write("## 原始转写\n\n")
        f.write(transcript_text)

    # 保存优化版本（多个）
    optimized_files = {}
    for prompt_name, optimized_text in optimized_texts.items():
        optimized_file = OUTPUT_DIR / f"{timestamp}_{safe_title}_{prompt_name}.md"
        with open(optimized_file, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n")
            f.write(f"**视频链接**: {video_url}\n\n")
            f.write(f"**提示词**: {prompt_name}\n\n")
            f.write("---\n\n")
            f.write(optimized_text)
        optimized_files[prompt_name] = str(optimized_file)

    save_elapsed = time.time() - save_start
    logger.info(f"结果保存完成 (耗时: {format_time(save_elapsed)})")

    # 总耗时
    total_elapsed = time.time() - total_start

    print("\n" + "=" * 60)
    print("✅ 处理完成！")
    print(f"⏱️  总耗时: {format_time(total_elapsed)}")
    print(f"📄 原始转写: {raw_file}")
    for prompt_name, file_path in optimized_files.items():
        print(f"✨ 优化版本 ({prompt_name}): {file_path}")
    print("=" * 60)

    # 打印预览
    print("\n原始转写预览:")
    print("-" * 60)
    print(transcript_text[:200] + ("..." if len(transcript_text) > 200 else ""))
    print("-" * 60)

    return {
        "success": True,
        "title": title,
        "video_url": video_url,
        "platform": platform,
        "raw_file": str(raw_file),
        "optimized_files": optimized_files,
        "transcript_text": transcript_text,
        "optimized_texts": optimized_texts,
        "total_time": total_elapsed
    }

# ==================== 批量处理 ====================
def process_batch(
    video_urls: List[str],
    model_size: str = "tiny",
    cpu_threads: int = 4,
    enable_llm_optimization: bool = True,
    prompt_names: List[str] = None
) -> List[dict]:
    """批量处理多个视频"""
    print("\n" + "=" * 60)
    print(f"批量处理模式 - 共 {len(video_urls)} 个视频")
    print("=" * 60)

    results = []
    for i, url in enumerate(video_urls, 1):
        print(f"\n{'='*60}")
        print(f"处理第 {i}/{len(video_urls)} 个视频")
        print(f"{'='*60}")

        try:
            result = process_video(
                video_url=url,
                model_size=model_size,
                cpu_threads=cpu_threads,
                enable_llm_optimization=enable_llm_optimization,
                prompt_names=prompt_names
            )
            results.append(result)
        except Exception as e:
            logger.error(f"处理视频失败: {url}, 错误: {e}")
            results.append({
                "success": False,
                "video_url": url,
                "error": str(e)
            })

    # 生成批量处理报告
    print("\n" + "=" * 60)
    print("批量处理完成！")
    print("=" * 60)

    success_count = sum(1 for r in results if r.get("success", False))
    fail_count = len(results) - success_count

    print(f"\n✅ 成功: {success_count} 个")
    print(f"❌ 失败: {fail_count} 个")

    if fail_count > 0:
        print("\n失败的视频:")
        for r in results:
            if not r.get("success", False):
                print(f"  - {r.get('video_url', 'unknown')}: {r.get('error', 'unknown error')}")

    # 保存批量处理报告
    report_file = OUTPUT_DIR / f"batch_report_{int(time.time())}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n📊 详细报告已保存: {report_file}")

    return results

# ==================== 命令行入口 ====================
def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="视频转写工具 - 支持多提示词和批量处理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 交互式运行
  python transcribe.py

  # 单个视频，使用默认提示词
  python transcribe.py --url "https://www.bilibili.com/video/BV1xxx"

  # 单个视频，使用多个提示词
  python transcribe.py --url "https://..." --prompts evaluation,summary

  # 批量处理
  python transcribe.py --batch urls.txt

  # B站搜索并转录（默认前5个）
  python transcribe.py --search "Python教程"

  # B站搜索并转录前10个
  python transcribe.py --search "Python教程" --search-count 10

  # 列出可用的提示词
  python transcribe.py --list-prompts
        """
    )

    parser.add_argument('--url', type=str, help='视频链接')
    parser.add_argument('--local', type=str, help='本地视频文件路径')
    parser.add_argument('--batch', type=str, help='批量处理文件（每行一个 URL）')
    parser.add_argument('--search', type=str, help='B站搜索关键词')
    parser.add_argument('--search-count', type=int, default=5, help='搜索结果数量（默认5）')
    parser.add_argument('--search-order', type=str, default='totalrank',
                        choices=['totalrank', 'pubdate', 'click', 'dm'],
                        help='搜索排序方式：totalrank=综合排序, pubdate=最新发布, click=最多播放, dm=最多弹幕')
    parser.add_argument('--prompts', type=str, help='提示词名称，多个用逗号分隔（如: evaluation,summary）')
    parser.add_argument('--no-llm', action='store_true', help='禁用大模型优化')
    parser.add_argument('--model-size', type=str, default='tiny', choices=['tiny', 'base', 'small'], help='Whisper 模型大小')
    parser.add_argument('--cpu-threads', type=int, default=4, help='CPU 线程数')
    parser.add_argument('--list-prompts', action='store_true', help='列出所有可用的提示词')

    args = parser.parse_args()

    # 列出可用提示词
    if args.list_prompts:
        prompts = list_available_prompts()
        print("\n可用的提示词:")
        for prompt in prompts:
            print(f"  - {prompt}")
        return

    # 解析提示词
    prompt_names = None
    if args.prompts:
        prompt_names = [p.strip() for p in args.prompts.split(',')]
        # 验证提示词是否存在
        available = list_available_prompts()
        for p in prompt_names:
            if p not in available:
                print(f"错误: 提示词 '{p}' 不存在")
                print(f"可用的提示词: {', '.join(available)}")
                return

    # B站搜索模式
    if args.search:
        if not BILIBILI_SEARCH_AVAILABLE:
            print("错误: B站搜索功能不可用")
            print("请安装依赖: pip install bilibili-api-python")
            return

        print(f"\n🔍 搜索B站视频: {args.search}")
        print(f"   数量: {args.search_count}")
        print(f"   排序: {args.search_order}")

        # 搜索视频
        videos = search_bilibili_videos(
            keyword=args.search,
            count=args.search_count,
            order=args.search_order
        )

        if not videos:
            print("错误: 搜索无结果或搜索失败")
            return

        # 显示搜索结果
        print(f"\n📊 找到 {len(videos)} 个视频:")
        for i, video in enumerate(videos, 1):
            print(f"  {i}. {video['title']}")
            print(f"     时长: {format_duration(video['duration'])}, "
                  f"播放: {format_play_count(video['play'])}, "
                  f"UP主: {video['author']}")

        # 提取URL列表
        urls = [video['url'] for video in videos]

        # 如果没有指定提示词，使用所有可用的提示词
        if prompt_names is None:
            prompt_names = list_available_prompts()
            if prompt_names:
                print(f"\n未指定提示词，将使用所有可用的提示词: {', '.join(prompt_names)}")
            else:
                print("\n警告: 未找到可用的提示词，将只进行原始转写")

        # 调用批量处理
        print(f"\n🎬 开始批量转录...")
        process_batch(
            video_urls=urls,
            model_size=args.model_size,
            cpu_threads=args.cpu_threads,
            enable_llm_optimization=not args.no_llm,
            prompt_names=prompt_names
        )
        return

    # 批量处理模式
    if args.batch:
        batch_file = Path(args.batch)
        if not batch_file.exists():
            print(f"错误: 批量处理文件不存在: {batch_file}")
            return

        with open(batch_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        if not urls:
            print("错误: 批量处理文件为空")
            return

        # 如果没有指定提示词，使用所有可用的提示词
        if prompt_names is None:
            prompt_names = list_available_prompts()
            if prompt_names:
                print(f"未指定提示词，将使用所有可用的提示词: {', '.join(prompt_names)}")
            else:
                print("警告: 未找到可用的提示词，将只进行原始转写")

        process_batch(
            video_urls=urls,
            model_size=args.model_size,
            cpu_threads=args.cpu_threads,
            enable_llm_optimization=not args.no_llm,
            prompt_names=prompt_names
        )
        return

    # 单个视频处理
    video_url = args.url or args.local
    if not video_url:
        # 交互式模式
        print("\n请输入视频链接或本地视频文件路径:")
        video_url = input("> ").strip()

        if not video_url:
            print("错误: 请输入有效的视频链接")
            return

        # 询问是否启用大模型
        if not args.no_llm:
            print("\n是否启用大模型文本优化？(y/n，默认 y):")
            enable_opt = input("> ").strip().lower()
            enable_llm = enable_opt != 'n'

            if enable_llm and not prompt_names:
                # 显示可用提示词
                available = list_available_prompts()
                print(f"\n可用的提示词: {', '.join(available)}")
                print("请选择提示词（多个用逗号分隔，直接回车则选择全部）:")
                prompts_input = input("> ").strip()

                if prompts_input:
                    # 如果用户输入了内容，就按用户输入的来
                    prompt_names = [p.strip() for p in prompts_input.split(',')]
                else:
                    # 如果用户没输入内容（直接回车），就使用全部可用的提示词
                    prompt_names = available

        else:
            enable_llm = False
    else:
        # 命令行模式
        enable_llm = not args.no_llm

        # 如果没有指定提示词，使用所有可用的提示词
        if enable_llm and prompt_names is None:
            prompt_names = list_available_prompts()
            if prompt_names:
                print(f"未指定提示词，将使用所有可用的提示词: {', '.join(prompt_names)}")
            else:
                print("警告: 未找到可用的提示词，将只进行原始转写")

    try:
        process_video(
            video_url=video_url,
            model_size=args.model_size,
            cpu_threads=args.cpu_threads,
            enable_llm_optimization=enable_llm,
            prompt_names=prompt_names
        )
    except Exception as e:
        logger.error(f"处理失败: {e}")
        print(f"\n错误: {e}")

if __name__ == "__main__":
    main()
