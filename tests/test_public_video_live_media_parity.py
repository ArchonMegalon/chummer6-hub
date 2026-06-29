from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_public_video_live_media_parity.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_public_video_live_media_parity_for_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeAudio:
    CLEAN_SPEECH_AUDIO_GROUPS = {"table-pulse-90s-deepdive"}
    clean_speech_pause_calls: list[bool] = []

    @staticmethod
    def audio_quality(path, allow_clean_speech_pauses=False):
        FakeAudio.clean_speech_pause_calls.append(bool(allow_clean_speech_pauses))
        return {"status": "pass", "reasons": [], "audio_duration_seconds": 3.0, "media_duration_seconds": 3.0}

    @staticmethod
    def probe(path):
        return {"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}


def test_live_parity_passes_when_download_matches_local_asset(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()
    FakeAudio.clean_speech_pause_calls = []
    media_root = tmp_path / "wwwroot" / "media"
    media_root.mkdir(parents=True)
    local = media_root / "demo.mp4"
    local.write_bytes(b"same-public-video-bytes")

    def fake_download(url, output, timeout):
        output.write_bytes(local.read_bytes())
        return module.DownloadedMedia(
            output,
            200,
            {
                "cache-control": "private, no-store, max-age=0",
                "cdn-cache-control": "no-store, max-age=0",
                "cf-cache-status": "BYPASS",
            },
        )

    monkeypatch.setattr(module, "download_file", fake_download)
    monkeypatch.setattr(module, "load_audio_module", lambda: FakeAudio)

    result = module.verify_all(
        media_root=media_root,
        base_url="https://chummer.run",
        timeout=5,
        require_no_store=True,
    )

    assert result["status"] == "pass"
    assert result["scope"]["file_count"] == 1
    assert result["assets"][0]["public_path"] == "/media/demo.mp4"
    assert result["assets"][0]["clean_speech_pauses_allowed"] is False
    assert FakeAudio.clean_speech_pause_calls == [False]


def test_live_parity_fails_stale_cdn_bytes_and_cache_hit(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()
    FakeAudio.clean_speech_pause_calls = []
    media_root = tmp_path / "wwwroot" / "media"
    media_root.mkdir(parents=True)
    local = media_root / "demo.mp4"
    local.write_bytes(b"fresh-local-video-bytes")

    def fake_download(url, output, timeout):
        output.write_bytes(b"stale-cdn-video-bytes")
        return module.DownloadedMedia(
            output,
            200,
            {
                "cache-control": "max-age=14400",
                "cf-cache-status": "HIT",
            },
        )

    monkeypatch.setattr(module, "download_file", fake_download)
    monkeypatch.setattr(module, "load_audio_module", lambda: FakeAudio)

    result = module.verify_all(
        media_root=media_root,
        base_url="https://chummer.run",
        timeout=5,
        require_no_store=True,
    )

    assert result["status"] == "fail"
    assert "/media/demo.mp4:download_sha256_mismatch" in result["issues"]
    assert "/media/demo.mp4:download_size_mismatch" in result["issues"]
    assert "/media/demo.mp4:missing_no_store_cache_header" in result["issues"]
    assert "/media/demo.mp4:cloudflare_cache_hit" in result["issues"]


def test_live_parity_allows_declared_clean_speech_video_pauses(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()
    FakeAudio.clean_speech_pause_calls = []
    media_root = tmp_path / "wwwroot" / "media"
    horizons = media_root / "horizons"
    horizons.mkdir(parents=True)
    local = horizons / "table-pulse-90s-deepdive.mp4"
    local.write_bytes(b"same-public-video-bytes")

    def fake_download(url, output, timeout):
        output.write_bytes(local.read_bytes())
        return module.DownloadedMedia(
            output,
            200,
            {
                "cache-control": "private, no-store, max-age=0",
                "cdn-cache-control": "no-store, max-age=0",
                "cf-cache-status": "BYPASS",
            },
        )

    monkeypatch.setattr(module, "download_file", fake_download)
    monkeypatch.setattr(module, "load_audio_module", lambda: FakeAudio)

    result = module.verify_all(
        media_root=media_root,
        base_url="https://chummer.run",
        timeout=5,
        require_no_store=True,
    )

    assert result["status"] == "pass"
    assert result["assets"][0]["public_path"] == "/media/horizons/table-pulse-90s-deepdive.mp4"
    assert result["assets"][0]["clean_speech_pauses_allowed"] is True
    assert FakeAudio.clean_speech_pause_calls == [True]
