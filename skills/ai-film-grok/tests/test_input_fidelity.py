"""Wave F0 · input fidelity scorer + CLI wiring."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from input_fidelity import (  # noqa: E402
    build_input_fidelity_report,
    fidelity_check,
    fidelity_status,
    receipt_path,
)
from util import write_json  # noqa: E402


def _spec_with_shots(nars: list[str], *, heat: str = "max") -> dict:
    shots = []
    for i, nar in enumerate(nars, start=1):
        shots.append(
            {
                "id": f"shot{i:02d}",
                "nar": nar,
                "dramatic_function": "action",
                "dsl": {"action": "hold", "motion": "push-in"},
            }
        )
    return {
        "title": "fidelity-fixture",
        "heat_scale": heat,
        "source_excerpt": "西门庆与潘金莲在狮子街灯下密会，酒过三巡。",
        "scenes": [{"title": "s1", "shots": shots}],
    }


class InputFidelityTests(unittest.TestCase):
    def test_high_score_when_source_language_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                _spec_with_shots(
                    [
                        "西门庆低声唤潘金莲",
                        "狮子街灯影晃动",
                        "酒过三巡她靠得更近",
                        "密会的心跳盖过脚步",
                    ]
                ),
            )
            write_json(
                root / "receipts" / "story-reception.json",
                {
                    "kind": "story-reception",
                    "source": {
                        "raw_text": "西门庆与潘金莲在狮子街灯下密会，酒过三巡。",
                        "sha256": "abc",
                    },
                    "fidelity": {
                        "immutable_facts": ["狮子街"],
                        "protected_dialogue": ["酒过三巡"],
                        "explicit_constraints": [],
                        "unknowns": [],
                    },
                },
            )
            write_json(
                root / "receipts" / "script-value-debrief.json",
                {
                    "viewer_promise": "看清一段灯下密会如何燃到失控",
                    "must_keep_beat_ids": ["bk_meet", "bk_wine"],
                    "confirmed_by_user": True,
                    "beat_shot_map": [
                        {"beat_id": "bk_meet", "shot_ids": ["shot01"]},
                        {"beat_id": "bk_wine", "shot_ids": ["shot03"]},
                    ],
                },
            )
            report = fidelity_check(root, strict=False, write=True)
            self.assertTrue(report["ok"], report)
            self.assertGreaterEqual(report["score"], 0.75)
            self.assertTrue(receipt_path(root).is_file())
            self.assertEqual(report["protected_dialogue_coverage"]["score"], 1.0)
            self.assertEqual(report["must_keep_map"]["score"], 1.0)

    def test_flags_template_pollution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                _spec_with_shots(
                    [
                        "展厅落锁，加演即将开始",
                        "展厅落锁，贴耳：下一场更紧",
                        "展厅落锁，灯光压暗",
                        "展厅落锁，门轴轻响",
                    ]
                ),
            )
            write_json(
                root / "receipts" / "story-reception.json",
                {
                    "source": {
                        "raw_text": "西门庆与潘金莲在狮子街灯下密会，酒过三巡。",
                        "sha256": "xyz",
                    },
                    "fidelity": {
                        "immutable_facts": [],
                        "protected_dialogue": [],
                        "explicit_constraints": [],
                        "unknowns": [],
                    },
                },
            )
            report = build_input_fidelity_report(root, strict=True, write=False)
            self.assertIn("USER_SOURCE_NAR_POLLUTED", report["codes"])
            self.assertFalse(report["ok"])

    def test_protected_dialogue_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                _spec_with_shots(["西门庆走近", "潘金莲抬眼", "灯影摇晃", "街角无人"]),
            )
            write_json(
                root / "receipts" / "story-reception.json",
                {
                    "source": {
                        "raw_text": "西门庆说：今夜别走。潘金莲在狮子街等他。",
                        "sha256": "p",
                    },
                    "fidelity": {
                        "immutable_facts": [],
                        "protected_dialogue": ["今夜别走"],
                        "explicit_constraints": [],
                        "unknowns": [],
                    },
                },
            )
            report = fidelity_status(root)
            self.assertIn("PROTECTED_DIALOGUE_DROPPED", report["codes"])
            self.assertLess(report["protected_dialogue_coverage"]["score"], 1.0)

    def test_must_keep_unmapped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                _spec_with_shots(["西门庆", "潘金莲", "狮子街", "酒过三巡"]),
            )
            write_json(
                root / "receipts" / "script-value-debrief.json",
                {
                    "viewer_promise": "密会燃点",
                    "must_keep_beat_ids": ["bk_a", "bk_b"],
                    "confirmed_by_user": True,
                },
            )
            write_json(
                root / "receipts" / "story-reception.json",
                {
                    "source": {
                        "raw_text": "西门庆与潘金莲在狮子街灯下密会，酒过三巡。",
                        "sha256": "m",
                    },
                    "fidelity": {
                        "immutable_facts": [],
                        "protected_dialogue": [],
                        "explicit_constraints": [],
                        "unknowns": [],
                    },
                },
            )
            report = build_input_fidelity_report(root, strict=True, write=False)
            self.assertIn("MUST_KEEP_UNMAPPED", report["codes"])
            self.assertEqual(report["must_keep_map"]["score"], 0.0)

    def test_status_without_spec_still_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            report = fidelity_status(root)
            self.assertIn("SOURCE_EXCERPT_MISSING", report["codes"])
            self.assertIn("next_cmd", report)


class CliFidelityWiringTests(unittest.TestCase):
    def test_parser_has_fidelity(self) -> None:
        import argparse

        from cli_workflow import add_workflow_parsers

        p = argparse.ArgumentParser()
        sub = p.add_subparsers(dest="cmd")
        add_workflow_parsers(sub)
        args = p.parse_args(["fidelity", "check", "--root", "/tmp/x", "--soft"])
        self.assertEqual(args.cmd, "fidelity")
        self.assertEqual(args.fidelity_action, "check")
        self.assertTrue(args.soft)

    def test_parser_has_apply_and_design_go(self) -> None:
        import argparse

        from cli_workflow import add_workflow_parsers

        p = argparse.ArgumentParser()
        sub = p.add_subparsers(dest="cmd")
        add_workflow_parsers(sub)
        a = p.parse_args(["fidelity", "apply", "--root", "/tmp/x", "--force"])
        self.assertEqual(a.fidelity_action, "apply")
        self.assertTrue(a.force)
        d = p.parse_args(["design-go", "--root", "/tmp/x"])
        self.assertEqual(d.cmd, "design-go")


class FidelityApplyAndPromptTests(unittest.TestCase):
    def test_apply_stamps_source_quote_and_protected(self) -> None:
        from input_fidelity import apply_fidelity_to_spec, fidelity_check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                _spec_with_shots(["角色走近", "灯影摇晃", "街角无人", "夜色更深"]),
            )
            write_json(
                root / "receipts" / "story-reception.json",
                {
                    "source": {
                        "raw_text": "西门庆与潘金莲在狮子街灯下密会，酒过三巡。今夜别走。",
                        "sha256": "sha1",
                    },
                    "fidelity": {
                        "immutable_facts": ["狮子街"],
                        "protected_dialogue": ["今夜别走"],
                        "explicit_constraints": [],
                        "unknowns": [],
                    },
                },
            )
            write_json(
                root / "receipts" / "script-value-debrief.json",
                {
                    "viewer_promise": "灯下密会燃点",
                    "must_keep_beat_ids": ["bk_meet", "bk_wine"],
                    "confirmed_by_user": True,
                },
            )
            rep = apply_fidelity_to_spec(root, force=True)
            self.assertTrue(rep["ok"])
            spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            shots = spec["scenes"][0]["shots"]
            self.assertTrue(all(s.get("source_quote") for s in shots))
            corpus = " ".join(
                str(s.get("spoken_text") or "") + str(s.get("nar") or "") for s in shots
            )
            self.assertIn("今夜别走", corpus)
            after = fidelity_check(root, write=False)
            self.assertNotIn("MUST_KEEP_UNMAPPED", after.get("codes") or [])

    def test_story_beat_prompt_prefix(self) -> None:
        from input_fidelity import inject_story_beat_into_prompt

        shot = {"source_quote": "狮子街灯下密会"}
        out = inject_story_beat_into_prompt("push-in, soft light", shot)
        self.assertIn("Story beat:", out)
        self.assertIn("狮子街", out)
        out2 = inject_story_beat_into_prompt(out, shot)
        self.assertEqual(out.count("Story beat:"), 1)
        self.assertEqual(out2, out)

    def test_design_go_writes_receipt(self) -> None:
        from input_fidelity import design_go

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                _spec_with_shots(
                    [
                        "西门庆唤潘金莲",
                        "狮子街灯影",
                        "酒过三巡",
                        "密会心跳",
                    ]
                ),
            )
            write_json(
                root / "receipts" / "story-reception.json",
                {
                    "source": {
                        "raw_text": "西门庆与潘金莲在狮子街灯下密会，酒过三巡。",
                        "sha256": "z",
                    },
                    "fidelity": {
                        "immutable_facts": [],
                        "protected_dialogue": [],
                        "explicit_constraints": [],
                        "unknowns": [],
                    },
                },
            )
            write_json(
                root / "receipts" / "script-value-debrief.json",
                {
                    "viewer_promise": "密会燃点",
                    "must_keep_beat_ids": ["a", "b"],
                    "confirmed_by_user": True,
                    "beat_shot_map": [
                        {"beat_id": "a", "shot_ids": ["shot01"]},
                        {"beat_id": "b", "shot_ids": ["shot02"]},
                    ],
                },
            )
            rep = design_go(root, write=True)
            self.assertTrue((root / "receipts" / "design-go.json").is_file())
            self.assertIn("checks", rep)

    def test_advance_allowlists_fidelity(self) -> None:
        from advance import ADVANCE_ACTIONS

        self.assertIn("fidelity-check", ADVANCE_ACTIONS)
        self.assertIn("fidelity-apply", ADVANCE_ACTIONS)
        self.assertIn("design-go", ADVANCE_ACTIONS)


if __name__ == "__main__":
    unittest.main()
