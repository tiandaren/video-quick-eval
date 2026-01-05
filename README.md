# **Video-QuickEval**

快速将 Bilibili/YouTube 视频转写为文本，支持大模型智能优化。

内置部分提示词，用于优化视频文本、质量评估和总结。

## 安装

### 前置要求

1. **Python 3.8+**
2. **FFmpeg**：用于音视频处理

#### 安装 FFmpeg

Windows (使用 winget):
```bash
winget install ffmpeg
```

macOS (使用 Homebrew):
```bash
brew install ffmpeg
```

Linux (Ubuntu/Debian):
```bash
sudo apt install ffmpeg
```

### 安装依赖

```bash
pip install -r requirements.txt
```

## 配置

### 1. 创建配置文件

复制示例配置文件并修改：

```bash
cp config.example.json config.json
```

### 2. 配置大语言模型

编辑 `config.json`：

```json
{
  "llm": {
    "provider": "openai",
    "api_key": "your-api-key-here",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "temperature": 0.3,
    "max_tokens": 12000
  },
  "transcribe": {
    "model_size": "tiny",
    "cpu_threads": 4,
    "auto_optimize": true
  }
}
```

### 3. 配置提示词

在 `prompts/` 目录下创建或修改提示词模板（Markdown 格式）。提示词文件必须包含 `{transcript_text}` 占位符。

示例提示词：
- `evaluation.md`: 内容评估与分析
- `summary.md`: 内容总结
- `format.md`: 格式化整理

## 使用方法

#### 交互式运行

```bash
python transcribe.py
```

程序会提示你输入视频链接、选择提示词等。

#### 命令行模式

单个视频：
```bash
python transcribe.py --url "https://www.bilibili.com/video/BV1xx411c7mD"
```

使用多个提示词：
```bash
python transcribe.py --url "视频链接" --prompts evaluation,summary,format
```

指定 Whisper 模型：
```bash
python transcribe.py --url "视频链接" --model-size base
```

批量处理（从文件读取）：
```bash
python transcribe.py --batch urls.txt
```

列出可用提示词：
```bash
python transcribe.py --list-prompts
```

## 项目结构

```
video-transcribe-ai/
├── transcribe.py           # 交互式/单视频处理脚本
├── config.json             # 配置文件（需自行创建）
├── config.example.json     # 配置文件示例
├── requirements.txt        # Python 依赖
├── video.txt              # 批量处理视频列表（可选）
├── failed_videos.txt      # 失败视频记录（自动生成）
├── src/                   # 源代码模块（可选，用于模块化开发）
│   ├── __init__.py
│   ├── downloader.py      # 视频下载器
│   ├── transcriber.py     # 音频转写器
│   ├── models.py          # 数据模型
│   └── utils.py           # 工具函数
├── prompts/               # 提示词模板
│   ├── evaluation.md      # 评估提示词
│   ├── summary.md         # 总结提示词
│   └── format.md          # 格式化提示词
├── output/                # 输出目录（自动创建）
├── data/                  # 临时数据目录（自动创建）
├── models/                # 模型缓存目录（自动创建）
│   └── whisper/           # Whisper 模型存储
│       ├── whisper-tiny/
│       ├── whisper-base/
│       └── whisper-small/
└── logs/                  # 日志目录（自动创建）
    └── app.log            # 应用日志
```

## 输出文件

处理完成后，会在 `output/` 目录生成：

- `{video_title}_raw.md`: 原始转写文本（包含视频信息）
- `{video_title}_{prompt_name}.md`: 经过 LLM 优化后的文本
- `batch_report_{timestamp}.json`: 批量处理报告（批量模式）

## 工作流程

1. **下载音频**：从指定平台下载视频音频（MP3 格式，64kbps）
2. **音频转写**：使用 Faster-Whisper 模型将音频转为文字
3. **繁简转换**：自动将繁体中文转为简体中文（需要 opencc）
4. **链式处理**：
   - 如果提示词中包含 `format`，先进行格式化
   - 其他提示词使用格式化后的文本进行处理
5. **LLM 优化**：使用配置的大语言模型和提示词对文本进行优化
6. **保存结果**：保存原始转写稿和优化后的文本
7. **清理临时文件**：删除下载的音频文件

**注意**：

- 模型首次使用时会自动从 ModelScope 下载
- 模型存储在 `models/whisper/` 目录
- 如果模型下载不完整，删除对应目录后重新运行即可

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License

## 致谢

- [faster-whisper](https://github.com/guillaumekln/faster-whisper) - 高效的 Whisper 实现
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 强大的视频下载工具
- [ModelScope](https://modelscope.cn/) - 模型托管平台
- [OpenCC](https://github.com/BYVoid/OpenCC) - 繁简转换工具
- [JefferyHcool/BiliNote](https://github.com/JefferyHcool/BiliNote) - 项目灵感来源

## 更新日志

### v1.0.0
- 初始版本发布
- 支持 Bilibili、YouTube 视频转写
- 集成 Faster-Whisper 和 LLM
- 支持批量处理和多提示词
- 支持繁简转换

## 技术栈

- **视频下载**: yt-dlp
- **音频转写**: faster-whisper (基于 CTranslate2)
- **大模型**: OpenAI API、Anthropic API、国内大模型 API
- **繁简转换**: OpenCC
- **模型托管**: ModelScope

## 联系方式

如有问题或建议，欢迎通过 Issue 反馈。
