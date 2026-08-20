---
name: video-quick-eval
description: Quickly transcribe local videos or URLs supported by yt-dlp with bundled faster-whisper, then clean up, summarize, or evaluate the transcript in Codex. Use when the user asks to turn video content into text or analyze its content.
metadata:
  short-description: Fast video transcription and analysis
---

# Video Quick Eval

Use the bundled CLI only for media acquisition and transcription. Content analysis belongs to Codex; never request an external LLM API key or call a local OpenAI/Anthropic client.

## Transcribe

Use the project-local virtual environment. If it does not exist, run the platform setup script once; it creates `.venv` and installs the declared dependencies. The setup script searches for Python 3.11+ instead of assuming the default `python` is compatible, so an older active Conda Python should not stop setup when another compatible runtime is available.

```powershell
& scripts/setup.ps1
& scripts/run.ps1 --url <video-url>
& scripts/run.ps1 --local <video-path>
& scripts/run.ps1 --batch <sources.txt>
```

On macOS/Linux, use `./scripts/setup.sh` and `./scripts/run.sh`. Do not call an unverified system Python. `VIDEO_QUICK_EVAL_PYTHON` may override the launcher when the user already has a compatible environment.

The URL path is platform-neutral: pass any yt-dlp-supported website directly to `--url`. Do not add site-specific logic unless a demonstrated failure requires it.

The CLI writes three files per successful item:

- `*_transcript.md`: readable transcript.
- `*_transcript.json`: timestamped segments.
- `*_manifest.json`: source, extractor, ASR model, timing, and file paths.

Read the manifest first. If `status` is not `success`, report the error and do not present partial output as complete.

## Analyze in Codex

After transcription succeeds, preserve this processing order:

1. Read the raw transcript.
2. Unless the user requested raw transcription only, read `prompts/format.md` and apply it first. Save the result as `_cleaned.md`.
3. Use `_cleaned.md`—never the raw Whisper transcript—as the input for all later analysis:
   - For a summary, read `prompts/summary.md` and save `_summary.md`.
   - For content evaluation, read `prompts/evaluation.md` and save `_evaluation.md`.

`format` is a mandatory dependency for summary and evaluation. Complete and verify the cleaned transcript before starting either downstream task. Summary and evaluation may run in parallel after `_cleaned.md` exists, and each downstream agent must receive that cleaned file rather than the raw transcript.

Use the prompt text as analysis guidance; do not run it through the Python CLI. For a long transcript, the main agent may delegate formatting to one subagent and wait for its cleaned artifact. It may then delegate summary and evaluation independently. For one short deliverable, handle it directly while preserving the same dependency order.

Save requested analysis next to the transcript with a descriptive suffix such as `_cleaned.md`, `_summary.md`, or `_evaluation.md`, and return clickable paths.

FFmpeg must be available on `PATH`. The default model is `whisper-tiny`: use a bundled model when present, otherwise let faster-whisper download it once into the user's cache. Do not assume the repository contains model binaries.

Device selection defaults to `auto`: use CUDA with float16 when CTranslate2 detects a usable NVIDIA GPU, otherwise use CPU with int8. If CUDA model loading fails in auto mode, fall back to CPU; an explicit `--device cuda` should surface the failure. Only override automatic selection when requested or troubleshooting.
