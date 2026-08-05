"""P1: agent-review-final assist draft — never auto-approves review-final."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from advance import ADVANCE_ACTIONS, _validate_argv  # noqa: E402
from agent_review_final import (  # noqa: E402
    agent_review_stale,
    build_agent_review_final,
)
from director_review import SCORECARD_DIMENSIONS  # noqa: E402
from dispatch import structured_next_action  # noqa: E402


def _write_minimal_film(root: Path, *, sha: str = "a" * 64) -> None:
    (root / "out").mkdir(parents=True, exist_ok=True)
    (root / "receipts").mkdir(parents=True, exist_ok=True)
    media = root / "out" / "film_final.mp4"
    media.write_bytes(b"\x00\x00fake-mp4")
    # real sha of the file
    import hashlib

    digest = hashlib.sha256(media.read_bytes()).hexdigest()
    man = {
        "title": "Assist Demo",
        "review_contract_version": 3,
        "gates": {
            "style_locked": True,
            "clips_complete": True,
            "final_complete": False,
            "desktop_exported": False,
        },
        "outputs": {
            "final_film": {
                "path": str(media),
                "sha256": digest,
                "duration_sec": 12.0,
            }
        },
    }
    (root / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (root / "film-spec.json").write_text(
        json.dumps({"title": "Assist Demo", "duration_sec": 12, "shots": []}),
        encoding="utf-8",
    )
    (root / "out" / "quality-report.json").write_text(
        json.dumps(
            {
                "duration_sec": 12.0,
                "hard_fail": False,
                "gates": {
                    "motion": {"status": "pass"},
                    "audio": {"status": "pass"},
                    "subtitles": {"status": "pass"},
                    "freeze": {"status": "pass"},
                    "black_frames": {"status": "pass"},
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "out" / "final.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8"
    )


class AgentReviewFinalCore(unittest.TestCase):
    def test_builds_full_scorecard_and_never_auto_approves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_film(root)
            report = build_agent_review_final(root, write=True)
            self.assertTrue(report["ok"])
            self.assertFalse(report["auto_approved"])
            self.assertTrue(report["never_auto_approves_review_final"])
            self.assertEqual(set(report["scorecard"]), set(SCORECARD_DIMENSIONS))
            self.assertEqual(set(report["screening_evidence"]), set(SCORECARD_DIMENSIONS))
            self.assertEqual(set(report["grades"]), set(SCORECARD_DIMENSIONS))
            self.assertTrue((root / "receipts" / "agent-review-final.json").is_file())
            # without reviewer → no assist input that can sneak into review-final
            self.assertFalse(report.get("assist_input_written"))
            self.assertIsNone(report.get("assist_input_path"))
            # gates unchanged
            man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(man["gates"]["final_complete"])

    def test_with_reviewer_writes_assist_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_film(root)
            report = build_agent_review_final(
                root,
                reviewer="dex",
                notes="已完整观看",
                human_minutes=2.0,
                write=True,
            )
            self.assertTrue(report["assist_input_written"])
            path = Path(report["assist_input_path"])
            self.assertTrue(path.is_file())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["kind"], "final-review-input")
            self.assertTrue(payload["approve"])
            self.assertTrue(payload["watched_full"])
            self.assertEqual(payload["reviewer"], "dex")
            self.assertEqual(set(payload["scorecard"]), set(SCORECARD_DIMENSIONS))
            self.assertIn("review-file", report["next_cmd"])
            self.assertFalse(report["auto_approved"])

    def test_stale_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_film(root)
            self.assertTrue(agent_review_stale(root))
            build_agent_review_final(root, write=True)
            self.assertFalse(agent_review_stale(root))
            # drift sha
            man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            man["outputs"]["final_film"]["sha256"] = "b" * 64
            (root / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
            # file still same but record claims different → stale
            # _final_record prefers file sha if... actually it uses manifest sha if path exists
            # force by rewriting media so hash changes while receipt keeps old
            (root / "out" / "film_final.mp4").write_bytes(b"\x00changed")
            self.assertTrue(agent_review_stale(root))

    def test_missing_media_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(Exception):
                build_agent_review_final(root)


class AgentReviewFinalP3PostLane(unittest.TestCase):
    def test_machine_lane_present_and_never_auto_approve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_film(root)
            report = build_agent_review_final(root, write=True)
            self.assertTrue(report.get("p3_post_lane"))
            lane = report.get("machine_lane") or (report.get("l0") or {}).get("machine_lane")
            self.assertIsInstance(lane, dict)
            self.assertIn("caption_pixel", lane)
            self.assertIn("timeline_clock", lane)
            self.assertFalse(report["auto_approved"])
            self.assertTrue(report["never_auto_approves_review_final"])
            # gates untouched
            man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(man["gates"]["final_complete"])

    def test_double_burn_route_fails_subs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_film(root)
            (root / "receipts" / "post-route.json").write_text(
                json.dumps(
                    {
                        "kind": "post-route",
                        "caption_path": "master_hf",
                        "plate_subs": "burn",
                    }
                ),
                encoding="utf-8",
            )
            report = build_agent_review_final(root, write=True)
            self.assertEqual(report["scorecard"].get("subs"), "fail")
            self.assertFalse(report.get("objective_all_pass"))

    def test_dual_clock_fails_dead_air(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_film(root)
            (root / "receipts" / "film_timeline.json").write_text(
                json.dumps({"shot_starts": [0.0, 6.0, 12.0], "output_duration": 18.0}),
                encoding="utf-8",
            )
            (root / "timeline.json").write_text(
                json.dumps(
                    {
                        "shot_starts": [0.0, 7.6, 15.0],
                        "shots": [
                            {"id": "s01", "duration_sec": 7.6},
                            {"id": "s02", "duration_sec": 7.4},
                            {"id": "s03", "duration_sec": 6.0},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = build_agent_review_final(root, write=True)
            self.assertEqual(report["scorecard"].get("dead_air"), "fail")
            self.assertFalse(report.get("objective_all_pass"))
            lane = report.get("machine_lane") or {}
            self.assertTrue((lane.get("timeline_clock") or {}).get("dual_clock"))

    def test_mix_partial_notes_audio_but_does_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_film(root)
            (root / "receipts" / "final-mix-partial.json").write_text(
                json.dumps(
                    {
                        "kind": "final-mix-partial",
                        "partial": True,
                        "reason_code": "sidechain_mix_failed_amix_fallback",
                        "affected_tracks": ["mx", "dx"],
                    }
                ),
                encoding="utf-8",
            )
            report = build_agent_review_final(root, write=True)
            self.assertEqual(report["scorecard"].get("audio"), "pass")
            note = ((report.get("l0") or {}).get("dimensions") or {}).get("audio", {}).get(
                "note"
            ) or ""
            self.assertIn("mix PARTIAL", note)


class AgentReviewFinalApply(unittest.TestCase):
    def test_apply_rejects_missing_phrase(self) -> None:
        from agent_review_final import AgentReviewFinalError, apply_agent_review_final

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_film(root)
            with self.assertRaises(AgentReviewFinalError):
                apply_agent_review_final(root, reviewer="dex", user_phrase="")

    def test_apply_rejects_forged_agent_phrase(self) -> None:
        from agent_review_final import AgentReviewFinalError, apply_agent_review_final

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_film(root)
            with self.assertRaises(AgentReviewFinalError):
                apply_agent_review_final(root, reviewer="dex", user_phrase="agent self-approve")

    def test_apply_dry_run_with_ok_phrase(self) -> None:
        from agent_review_final import apply_agent_review_final

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_minimal_film(root)
            report = apply_agent_review_final(
                root,
                reviewer="dex",
                user_phrase="可以",
                notes="已完整观看",
                dry_run=True,
            )
            self.assertTrue(report["ok"])
            self.assertFalse(report["applied"])
            self.assertTrue(report["dry_run"])
            self.assertFalse(report["auto_forged"])
            self.assertTrue((root / "receipts" / "agent-review-final-apply.json").is_file())
            self.assertTrue((root / "receipts" / "final-review-input.assist.json").is_file())


class AgentReviewFinalPolicy(unittest.TestCase):
    def test_dispatch_policy_local_none(self) -> None:
        act = structured_next_action(
            {
                "id": "agent-review-final",
                "cmd": 'aifilm agent-review-final --root "/film"',
                "stage": "post",
            }
        )
        assert act is not None
        self.assertEqual(act["approval_class"], "none")
        self.assertEqual(act["spend_class"], "local")
        self.assertEqual(act["argv"][0], "agent-review-final")

    def test_review_final_still_human(self) -> None:
        act = structured_next_action(
            {
                "id": "review-final",
                "cmd": 'aifilm review-final --root "/film" --approve --reviewer dex',
            }
        )
        assert act is not None
        self.assertEqual(act["approval_class"], "human_required")

    def test_advance_allowlisted(self) -> None:
        self.assertIn("agent-review-final", ADVANCE_ACTIONS)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            action = {
                "skill_id": "quality.inspect",
                "spend_class": "local",
                "approval_class": "none",
                "argv": ["agent-review-final", "--root", str(root)],
            }
            policy, argv = _validate_argv(root=root, action_id="agent-review-final", action=action)
            self.assertEqual(policy.prefix, ("agent-review-final",))
            self.assertEqual(argv[0], "agent-review-final")


if __name__ == "__main__":
    unittest.main()
