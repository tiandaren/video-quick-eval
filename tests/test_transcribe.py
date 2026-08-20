import json
import sys
import types
from pathlib import Path

import transcribe


def test_resolve_device_auto_prefers_cuda(monkeypatch):
    fake_ct2 = types.SimpleNamespace(get_cuda_device_count=lambda: 1)
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2)
    assert transcribe.resolve_device("auto") == "cuda"


def test_resolve_device_auto_falls_back_to_cpu(monkeypatch):
    fake_ct2 = types.SimpleNamespace(get_cuda_device_count=lambda: 0)
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2)
    assert transcribe.resolve_device("auto") == "cpu"


def test_detect_source_type_is_platform_agnostic():
    assert transcribe.detect_source_type("https://youtu.be/abcdefghijk") == "online"
    assert transcribe.detect_source_type("https://www.bilibili.com/video/BV123") == "online"
    assert transcribe.detect_source_type("https://example.com/video/123") == "online"
    assert transcribe.detect_source_type("C:/videos/demo.mp4") == "local"


def test_transcribe_audio_uses_faster_whisper(monkeypatch, tmp_path):
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"audio")

    class Segment:
        start = 0.0
        end = 1.0
        text = "  hello  "

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, path, **kwargs):
            assert Path(path) == audio
            return iter([Segment()]), types.SimpleNamespace(language="en", duration=1.0)

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    result = transcribe.transcribe_audio(str(audio), model_dir=tmp_path / "models")
    assert result["text"] == "hello"
    assert result["language"] == "en"
    assert result["segments"][0]["start"] == 0.0
    assert result["device"] in {"cpu", "cuda"}


def test_transcribe_audio_prefers_bundled_model(monkeypatch, tmp_path):
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"audio")
    bundled = tmp_path / "models" / "whisper-tiny"
    bundled.mkdir(parents=True)
    (bundled / "model.bin").write_bytes(b"model")
    loaded = {}

    class Segment:
        start = 0.0
        end = 1.0
        text = "hello"

    class FakeModel:
        def __init__(self, source, **kwargs):
            loaded["source"] = source

        def transcribe(self, path, **kwargs):
            return iter([Segment()]), types.SimpleNamespace(language="en", duration=1.0)

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    transcribe.transcribe_audio(str(audio), model_dir=tmp_path / "models")
    assert Path(loaded["source"]) == bundled


def test_transcribe_audio_auto_falls_back_when_cuda_load_fails(monkeypatch, tmp_path):
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"audio")
    loaded_devices = []

    class Segment:
        start = 0.0
        end = 1.0
        text = "hello"

    class FakeModel:
        def __init__(self, source, **kwargs):
            loaded_devices.append(kwargs["device"])
            if kwargs["device"] == "cuda":
                raise RuntimeError("CUDA runtime unavailable")

        def transcribe(self, path, **kwargs):
            return iter([Segment()]), types.SimpleNamespace(language="en", duration=1.0)

    monkeypatch.setattr(transcribe, "resolve_device", lambda requested: "cuda")
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    result = transcribe.transcribe_audio(str(audio), model_dir=tmp_path / "models")

    assert loaded_devices == ["cuda", "cpu"]
    assert result["device"] == "cpu"
    assert result["compute_type"] == "int8"


def test_process_video_writes_transcript_and_manifest(monkeypatch, tmp_path):
    audio = tmp_path / "temporary.mp3"
    audio.write_bytes(b"audio")
    monkeypatch.setattr(
        transcribe,
        "extract_audio_from_local_video",
        lambda source, data: {"audio_path": str(audio), "title": "Demo", "source_id": "demo", "extractor": "local"},
    )
    monkeypatch.setattr(
        transcribe,
        "transcribe_audio",
        lambda *args, **kwargs: {
            "text": "transcript",
            "language": "en",
            "duration": 1.0,
            "segments": [{"start": 0.0, "end": 1.0, "text": "transcript"}],
            "device": "cpu",
            "compute_type": "int8",
        },
    )

    result = transcribe.process_video(
        str(tmp_path / "video.mp4"),
        output_dir=str(tmp_path / "output"),
        data_dir=str(tmp_path / "data"),
        model_dir=str(tmp_path / "models"),
    )

    assert result["success"] is True
    assert set(result["files"]) == {"transcript_markdown", "transcript_json", "manifest"}
    assert all(Path(path).is_file() for path in result["files"].values())
    manifest = json.loads(Path(result["files"]["manifest"]).read_text(encoding="utf-8"))
    assert manifest["asr_backend"] == "faster-whisper"
    assert manifest["device"] == "cpu"
    assert manifest["compute_type"] == "int8"
    assert manifest["status"] == "success"
    assert not audio.exists()


def test_download_audio_uses_generic_yt_dlp_options(monkeypatch, tmp_path):
    captured = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, source, download):
            output = tmp_path / "abc.mp3"
            output.write_bytes(b"audio")
            return {"id": "abc", "title": "Demo", "extractor_key": "Generic"}

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(transcribe, "_require_executable", lambda name: name)
    result = transcribe.download_audio("https://example.com/video", tmp_path)
    assert result["audio_path"].endswith("abc.mp3")
    assert captured["retries"] >= 3
    assert captured["noplaylist"] is True


def test_strip_tracking_parameters_keeps_media_parameters():
    source = "https://example.com/watch?v=abc&p=2&spm_id_from=home&trackid=xyz&vd_source=user"
    assert transcribe.strip_tracking_parameters(source) == "https://example.com/watch?v=abc&p=2"


def test_default_model_dir_uses_user_cache_without_bundled_model(monkeypatch, tmp_path):
    monkeypatch.setattr(transcribe, "PROJECT_DIR", tmp_path / "skill")
    if transcribe.os.name == "nt":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "cache"))
    else:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert transcribe.default_model_dir() == tmp_path / "cache" / "video-quick-eval" / "models" / "whisper"


def test_download_audio_retries_once_with_clean_url(monkeypatch, tmp_path):
    calls = []

    class FakeYoutubeDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, source, download):
            calls.append(source)
            if len(calls) == 1:
                raise RuntimeError("Failed to extract play info")
            (tmp_path / "abc.mp3").write_bytes(b"audio")
            return {"id": "abc", "title": "Demo", "extractor_key": "Generic"}

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setattr(transcribe, "_require_executable", lambda name: name)
    transcribe.download_audio("https://example.com/video?v=abc&spm_id_from=home", tmp_path)
    assert calls == [
        "https://example.com/video?v=abc&spm_id_from=home",
        "https://example.com/video?v=abc",
    ]
