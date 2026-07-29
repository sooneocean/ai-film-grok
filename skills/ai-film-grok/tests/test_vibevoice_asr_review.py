from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import vibevoice_asr_review  # noqa: E402


def _workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "film"
    root.mkdir()
    audio = root / "mix.wav"
    audio.write_bytes(b"RIFF")
    subtitles = root / "subtitles.srt"
    subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\n你好世界\n", encoding="utf-8")
    return root, audio, subtitles


def test_probe_never_runs_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(vibevoice_asr_review.ARGV_ENV, raising=False)
    report = vibevoice_asr_review.capability_probe()
    assert report["inference_started"] is False
    assert report["provider"]["status"] == "not_configured"


def test_report_is_candidate_only_and_hash_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, audio, subtitles = _workspace(tmp_path)
    monkeypatch.setenv(
        vibevoice_asr_review.ARGV_ENV,
        '["adapter","--audio","{audio}","--out","{out}"]',
    )
    monkeypatch.setattr(
        vibevoice_asr_review, "analyze_media", lambda *_args, **_kwargs: {"ok": True}
    )

    def run(command, **_kwargs):
        output = Path(command[command.index("--out") + 1])
        output.write_text(
            json.dumps(
                {"segments": [{"speaker": "nar", "start": 0, "end": 1, "text": "你好世界"}]}
            ),
            encoding="utf-8",
        )
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(vibevoice_asr_review.subprocess, "run", run)
    report = vibevoice_asr_review.create_report(root, audio=audio, subtitles=subtitles)
    assert report["status"] == "candidate_only"
    assert report["may_approve_production"] is False
    assert report["transcript"]["speakers"] == ["nar"]
    assert Path(report["path"]).is_file()


def test_adapter_must_use_controlled_input_and_output_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(vibevoice_asr_review.ARGV_ENV, '["adapter","--audio","{audio}"]')
    with pytest.raises(vibevoice_asr_review.VibeVoiceASRError, match="both"):
        vibevoice_asr_review._argv()


def test_rejects_symlinked_input_inside_workspace(tmp_path: Path) -> None:
    root, audio, _subtitles = _workspace(tmp_path)
    linked = root / "linked.wav"
    linked.symlink_to(audio)
    with pytest.raises(vibevoice_asr_review.VibeVoiceASRError, match="non-symlink"):
        vibevoice_asr_review._root_file(root, linked, label="audio")


def test_rejects_receipts_symlink_before_adapter_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, audio, _subtitles = _workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "receipts").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv(
        vibevoice_asr_review.ARGV_ENV,
        '["adapter","--audio","{audio}","--out","{out}"]',
    )
    monkeypatch.setattr(
        vibevoice_asr_review, "analyze_media", lambda *_args, **_kwargs: {"ok": True}
    )
    with pytest.raises(vibevoice_asr_review.VibeVoiceASRError, match="receipts"):
        vibevoice_asr_review.create_report(root, audio=audio)


def test_adapter_failure_does_not_write_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, audio, _subtitles = _workspace(tmp_path)
    monkeypatch.setenv(
        vibevoice_asr_review.ARGV_ENV,
        '["adapter","--audio","{audio}","--out","{out}"]',
    )
    monkeypatch.setattr(
        vibevoice_asr_review, "analyze_media", lambda *_args, **_kwargs: {"ok": True}
    )
    monkeypatch.setattr(
        vibevoice_asr_review.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 1})(),
    )
    with pytest.raises(vibevoice_asr_review.VibeVoiceASRError, match="failed"):
        vibevoice_asr_review.create_report(root, audio=audio)
    assert not (root / "receipts" / vibevoice_asr_review.REPORT_NAME).exists()
