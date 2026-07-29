from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import external_review  # noqa: E402


def _workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "film"
    root.mkdir()
    video = root / "master.mp4"
    video.write_bytes(b"not-a-real-video")
    subtitles = root / "subtitles.srt"
    subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\n你好世界\n", encoding="utf-8")
    (root / "film-spec.json").write_text("{}", encoding="utf-8")
    return root, video, subtitles


def test_adult_review_requires_declared_sanitized_inputs(tmp_path: Path) -> None:
    root, video, subtitles = _workspace(tmp_path)
    (root / "film-spec.json").write_text('{"heat_scale":"max"}', encoding="utf-8")
    with pytest.raises(external_review.ExternalReviewError, match="sanitized"):
        external_review.create_report(root, video=video, subtitles=subtitles, sanitized=False)


def test_adult_review_never_sends_raw_video_or_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, video, subtitles = _workspace(tmp_path)
    (root / "film-spec.json").write_text('{"heat_scale":"max"}', encoding="utf-8")
    contract = root / "director-contract.json"
    contract.write_text('{"private":"UNREDACTED_CONTRACT"}', encoding="utf-8")
    monkeypatch.setattr(external_review, "analyze_media", lambda *_args, **_kwargs: {"ok": True})
    with pytest.raises(external_review.ExternalReviewError, match="never raw video"):
        external_review.create_report(
            root, video=video, subtitles=subtitles, director_contract=contract, sanitized=True
        )


def test_symlinked_input_is_rejected(tmp_path: Path) -> None:
    root, _video, _subtitles = _workspace(tmp_path)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"x")
    link = root / "linked.mp4"
    link.symlink_to(outside)
    with pytest.raises(external_review.ExternalReviewError, match="non-symlink"):
        external_review._root_file(root, link, label="video")


def test_report_is_candidate_only_and_provider_failure_is_nonblocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, video, subtitles = _workspace(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "test-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "another-secret")
    monkeypatch.setattr(external_review, "analyze_media", lambda *_args, **_kwargs: {"ok": True})

    def unavailable(*_args, **_kwargs):
        raise external_review.ExternalReviewUnavailable(
            "GROQ_HTTP_429", "provider returned HTTP 429"
        )

    monkeypatch.setattr(external_review, "_groq_transcription", unavailable)
    report = external_review.create_report(root, video=video, subtitles=subtitles, sanitized=True)
    assert report["status"] == "candidate_only"
    assert report["may_approve_production"] is False
    assert report["may_change_provider"] is False
    assert report["providers"]["groq"]["status"] == "unavailable"
    serialized = json.dumps(report, ensure_ascii=False)
    assert "test-secret" not in serialized and "another-secret" not in serialized
    assert Path(report["path"]).is_file()


def test_word_timing_comparison_finds_missing_and_timing_drift() -> None:
    subtitles = [
        {"start_sec": 0.0, "end_sec": 1.0, "text": "你好世界"},
        {"start_sec": 1.0, "end_sec": 2.0, "text": "再见"},
    ]
    words = [
        {"word": "你好", "start": 0.7, "end": 1.0},
        {"word": "世界", "start": 1.0, "end": 1.2},
    ]
    issues = external_review.compare_word_timing(subtitles, words)
    codes = {item["code"] for item in issues}
    assert "subtitle_timing_drift" in codes
    assert "subtitle_missing_from_transcript" in codes


def test_rejects_media_that_fails_local_technical_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, video, subtitles = _workspace(tmp_path)
    monkeypatch.setattr(external_review, "analyze_media", lambda *_args, **_kwargs: {"ok": False})
    with pytest.raises(external_review.ExternalReviewError, match="technical media"):
        external_review.create_report(root, video=video, subtitles=subtitles, sanitized=True)


def test_probe_never_starts_inference_or_exposes_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    report = external_review.capability_probe()
    assert report["inference_started"] is False
    assert report["providers"]["groq"]["status"] == "not_configured"
    assert report["providers"]["gemini"]["status"] == "not_configured"
