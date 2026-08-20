# video-quick-eval

> 如果你是 Agent 工具：直接将
> `https://github.com/tiandaren/video-quick-eval` 安装到 skills 目录。Codex 的默认
> 目标是 `$CODEX_HOME/skills/video-quick-eval`。安装后读取 [SKILL.md](SKILL.md)，
> 运行当前系统对应的 `scripts/setup.*`，再处理用户给出的视频链接或本地文件。
> Python 和计算设备由脚本自动选择，不要先向用户询问。

这个项目包含一个 Codex skill 和一个本地转写 CLI。CLI 用 yt-dlp 获取网络视频，
用 FFmpeg 处理音频，用 faster-whisper 生成带时间戳的原始转写。格式化、摘要和内容
评估由 Codex 完成，不调用本地或外部大模型 API。

## 安装

需要 Python 3.11+ 和 FFmpeg，支持 Windows、macOS 和 Linux。先确认 FFmpeg 可用：

```bash
ffmpeg -version
```

没有 FFmpeg 时，按系统安装：

```bash
# Windows
winget install Gyan.FFmpeg

# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt update && sudo apt install ffmpeg
```

Windows PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& scripts/setup.ps1
```

`setup.ps1` 会检查 `py -3`、PATH 中的 Python 和 Codex 桌面版可用运行时，选择
Python 3.11+ 创建项目内的 `.venv`。默认 `python` 指向旧版 Conda 时，脚本会继续
检查其他候选，不会立即退出。机器上没有兼容版本时，执行：

```powershell
winget install Python.Python.3.12
```

需要固定解释器时执行：

```powershell
& scripts/setup.ps1 -Python "C:\path\to\python.exe"
```

macOS 或 Linux：

```bash
chmod +x scripts/setup.sh scripts/run.sh
./scripts/setup.sh
```

脚本会从 `python3.14` 至 `python3.11` 和 `python3` 中选择兼容版本。需要固定解释器
时执行 `PYTHON=/path/to/python3.12 ./scripts/setup.sh`。

## 转写

Windows：

```powershell
& scripts/run.ps1 --url "https://example.com/video"
& scripts/run.ps1 --local "path/to/video.mp4"
& scripts/run.ps1 --batch "sources.txt"
```

macOS 或 Linux：

```bash
./scripts/run.sh --url "https://example.com/video"
./scripts/run.sh --local "path/to/video.mp4"
./scripts/run.sh --batch "sources.txt"
```

URL 直接交给 yt-dlp，因此可处理 yt-dlp 支持的网站，不包含 Bilibili 专用下载逻辑。
网络失败会有限重试；如果 URL 含 `spm_id_from`、`trackid`、`vd_source` 或 `utm_*`
参数，首次失败后会移除这些跟踪参数再试一次。

每个成功任务生成三个文件：

- `*_transcript.md`：可直接阅读的原始转写。
- `*_transcript.json`：包含时间戳和分段信息。
- `*_manifest.json`：记录来源、下载器、模型、实际设备、耗时和输出路径。

常用参数：

```text
--model-size tiny|base|small|medium|large-v1|large-v2|large-v3
--language zh
--device auto|cpu|cuda
--output-dir <目录>
--keep-audio
```

默认设备是 `auto`。CTranslate2 检测到可用的 NVIDIA CUDA 后使用
`cuda + float16`；没有 CUDA，或 CUDA 模型加载失败时，使用 `cpu + int8`。
`--device cpu` 和 `--device cuda` 只用于强制选择或排查环境问题。

默认模型是随 skill 安装的 `models/whisper/whisper-tiny/`。如果该目录缺少模型，
或用户选择其他模型尺寸，faster-whisper 会在首次运行时下载并缓存：

- Windows：`%LOCALAPPDATA%\video-quick-eval\models\whisper`
- macOS/Linux：`${XDG_CACHE_HOME:-~/.cache}/video-quick-eval/models/whisper`

## Codex 处理顺序

CLI 只负责获取音频和生成原始转写。Codex 必须先使用 `prompts/format.md` 生成
`*_cleaned.md`，再以 cleaned 文件为输入执行 `prompts/summary.md` 或
`prompts/evaluation.md`。摘要和评估可以在 cleaned 文件生成后并行执行，不能直接
读取 Whisper 原始稿。用户只要求原始转写时，跳过这些步骤。

## 解析失败

视频网站会调整页面和播放接口，旧版 yt-dlp 可能无法解析。先更新项目环境中的
yt-dlp，再重试同一链接：

```bash
# Windows
.venv\Scripts\python -m pip install -U yt-dlp

# macOS/Linux
.venv/bin/python -m pip install -U yt-dlp
```

更新后仍失败，通常是网站要求登录 Cookie、地区受限或媒体本身不可访问。此时使用
本地视频、音频或字幕文件继续处理，不在 CLI 中加入网站私有接口。

## 开发验证

```bash
python -m pip install ".[dev]"
python -m pytest -q
python -m compileall -q transcribe.py
```

CI 在 Windows 和 Ubuntu 上测试 Python 3.11、3.12。许可证为 MIT。
