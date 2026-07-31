"""Opt2: edge empty-stream retry, queue shot membership, preflight framing, fail-loud duration."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import contextlib

import aifilm_grok  # noqa: E402
import media_queue  # noqa: E402
import tts_backend  # noqa: E402
from media_queue import MediaQueue, QueueError  # noqa: E402
from preflight import run_preflight  # noqa: E402


def _spec_one(shot_id: str = "shot01", *, framing: str | None = None) -> dict:
    dsl = {
        "subject": "a",
        "action": "blinks",
        "motion": "soft blink, breath, idle not speaking",
    }
    if framing:
        dsl["framing"] = framing
    else:
        dsl["framing"] = "medium, full head, headroom, safe framing no cropping"
    return {
        "title": "opt2",
        "vo_mode": "storyteller",
        "tts_backend": "edge",
        "director_intent": {
            "logline": "雨夜后座升温的完整承诺句。",
            "tone": "测试",
            "emotional_arc": ["a", "b", "c"],
        },
        "sound_plan": {"mood": "rnb"},
        "scenes": [
            {
                "shots": [
                    {
                        "id": shot_id,
                        "dramatic_function": "hook",
                        "nar": "话说她眨眼。",
                        "duration_sec": 6,
                        "dsl": dsl,
                    }
                ]
            }
        ],
    }


class EdgeEmptyRetryTests(unittest.TestCase):
    def test_retries_then_succeeds_on_second_stream(self) -> None:
        results = [b"", b"x" * 600]
        attempts = {"n": 0}

        def fake_asyncio_run(coro):  # noqa: ANN001
            attempts["n"] += 1
            with contextlib.suppress(Exception):
                coro.close()
            return results.pop(0) if results else b"x" * 600

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "vo.mp3"
            with mock.patch("time.sleep", return_value=None):
                with mock.patch("asyncio.run", side_effect=fake_asyncio_run):
                    path = tts_backend.tts_edge("你好世界", out, max_attempts=3, min_bytes=500)
            self.assertTrue(path.is_file())
            self.assertGreaterEqual(path.stat().st_size, 500)
            self.assertEqual(attempts["n"], 2)  # empty then ok

    def test_all_empty_raises(self) -> None:
        def fake_asyncio_run(coro):  # noqa: ANN001
            with contextlib.suppress(Exception):
                coro.close()
            return b"\x00" * 10  # tiny

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "vo.mp3"
            with mock.patch("time.sleep", return_value=None):
                with mock.patch("asyncio.run", side_effect=fake_asyncio_run):
                    with self.assertRaises(tts_backend.TTSError) as ctx:
                        tts_backend.tts_edge("hi", out, max_attempts=2, min_bytes=500)
            self.assertIn("empty/tiny", str(ctx.exception).lower())


class QueueShotMembershipTests(unittest.TestCase):
    def test_ghost_shot_rejected_when_spec_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            (root / "film-spec.json").write_text(
                json.dumps(_spec_one("shot01"), ensure_ascii=False),
                encoding="utf-8",
            )
            prompt = root / "p.txt"
            prompt.write_text("motion", encoding="utf-8")
            still = root / "k.png"
            still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            q = MediaQueue(root, budget_units=10)
            with self.assertRaisesRegex(QueueError, "not in film-spec"):
                q.add_job(
                    shot_id="shotZZ",
                    operation="image_to_video",
                    prompt_file=prompt,
                    inputs=[still],
                    allow_without_pilot=True,
                )

    def test_known_shot_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            (root / "film-spec.json").write_text(
                json.dumps(_spec_one("shot01"), ensure_ascii=False),
                encoding="utf-8",
            )
            prompt = root / "p.txt"
            prompt.write_text("motion", encoding="utf-8")
            still = root / "k.png"
            still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            q = MediaQueue(root, budget_units=10)
            with (
                mock.patch.object(media_queue, "assert_pilot_allows_add"),
                mock.patch.object(media_queue, "assert_heat_allows_media"),
            ):
                job = q.add_job(
                    shot_id="shot01",
                    operation="image_to_video",
                    prompt_file=prompt,
                    inputs=[still],
                    allow_without_pilot=False,
                )
            self.assertEqual(job["shot_id"], "shot01")


class PreflightFramingTests(unittest.TestCase):
    def test_crop_prone_framing_is_hard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            (root / "manifest.json").write_text(
                json.dumps({"schema_version": 1, "gates": {}, "clips": {}, "outputs": {}}),
                encoding="utf-8",
            )
            (root / "style-bible.json").write_text(
                json.dumps({"locked": True, "identity_lock": "ok"}),
                encoding="utf-8",
            )
            (root / "film-spec.json").write_text(
                json.dumps(
                    _spec_one(framing="extreme close-up, face fills the frame, push-in on face"),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            report = run_preflight(root)
            hard = {i["code"] for i in report["hard"]}
            self.assertIn("framing_crop_prone", hard)

    def test_missing_headroom_is_hard_without_strict_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            (root / "manifest.json").write_text(
                json.dumps({"schema_version": 1, "gates": {}, "clips": {}, "outputs": {}}),
                encoding="utf-8",
            )
            (root / "style-bible.json").write_text(
                json.dumps({"locked": True, "identity_lock": "ok"}),
                encoding="utf-8",
            )
            spec = _spec_one(framing="medium shot, full head visible")
            (root / "film-spec.json").write_text(
                json.dumps(spec, ensure_ascii=False), encoding="utf-8"
            )
            report = run_preflight(root)
            hard = {i["code"] for i in report["hard"]}
            self.assertIn("framing_crop_prone", hard)


class AifilmMediaDurationFailLoudTests(unittest.TestCase):
    def test_missing_path_raises_film_error(self) -> None:
        with self.assertRaises(aifilm_grok.FilmError):
            aifilm_grok.media_duration(Path("/nonexistent/opt2-missing.mp4"))


if __name__ == "__main__":
    unittest.main()
