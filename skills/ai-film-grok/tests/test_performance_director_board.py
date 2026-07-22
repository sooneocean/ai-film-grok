#!/usr/bin/env python3
"""Tests for performance / subtext and director_board lints in film-spec.

These cover the "motion without performance" failure mode: I2V can move
bodies, but subtext / playable_action / body_state are what make a shot
*act*. Also covers the scene-level director decision board.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from film_spec import (  # noqa: E402
    DIRECTOR_BOARD_FIELDS,
    PERFORMANCE_FIELDS,
    FilmSpecError,
    lint_director_board,
    lint_performance,
    validate_film_spec,
)


def _shot(
    sid: str = "shot01",
    fn: str = "hook",
    role: str = "hero",
    *,
    subtext: str | None = None,
    playable_action: str | None = None,
    body_state: str | None = None,
) -> dict:
    dsl = {
        "motion": "slow dolly-in, breath",
        "visible_change": "door closes",
        "story_beat": "she shuts the door",
    }
    if subtext is not None:
        dsl["subtext"] = subtext
    if playable_action is not None:
        dsl["playable_action"] = playable_action
    if body_state is not None:
        dsl["body_state"] = body_state
    return {
        "id": sid,
        "nar": "她关上门。",
        "dramatic_function": fn,
        "shot_role": role,
        "dsl": dsl,
    }


def _scene(shots: list[dict] | None = None, board: dict | None = None) -> dict:
    sc = {"title": "S", "summary": "s", "shots": shots or [_shot()]}
    if board is not None:
        sc["director_board"] = board
    return sc


def _spec(scenes: list[dict] | None = None) -> dict:
    return {
        "title": "T",
        "vo_mode": "storyteller",
        "director_intent": {
            "logline": "测试一句话足够长的命题。",
            "tone": "test",
            "emotional_arc": ["a", "b", "c"],
        },
        "scenes": scenes or [_scene()],
    }


class LintPerformanceTests(unittest.TestCase):
    def test_hero_shot_missing_all_performance_fields_warns(self) -> None:
        shot = _shot()  # no subtext/playable_action/body_state
        r = lint_performance([shot])
        self.assertFalse(r["ok"])
        self.assertIn("SHOT_PERFORMANCE_MISSING", r["codes"])
        issue = r["issues"][0]
        self.assertEqual(set(issue["fields"]), set(PERFORMANCE_FIELDS))
        self.assertTrue(issue["spine"])  # hook is a spine beat

    def test_placeholder_values_treated_as_unauthored(self) -> None:
        shot = _shot(subtext="待补", playable_action="todo", body_state="needs_authoring")
        r = lint_performance([shot])
        self.assertFalse(r["ok"])
        self.assertEqual(len(r["issues"]), 1)

    def test_authored_performance_passes(self) -> None:
        shot = _shot(
            subtext="she wants to lock him in",
            playable_action="reaches for lock",
            body_state="fingers tremble",
        )
        r = lint_performance([shot])
        self.assertTrue(r["ok"], r)

    def test_env_bridge_bed_skipped(self) -> None:
        shot = _shot(fn="bridge", role="env")
        r = lint_performance([shot])
        self.assertTrue(r["ok"])

    def test_non_spine_beat_flagged_but_not_spine(self) -> None:
        shot = _shot(fn="afterglow")
        r = lint_performance([shot])
        self.assertFalse(r["ok"])
        self.assertFalse(r["issues"][0]["spine"])


class LintDirectorBoardTests(unittest.TestCase):
    def test_missing_board_warns(self) -> None:
        r = lint_director_board([_scene(board=None)])
        self.assertFalse(r["ok"])
        self.assertIn("DIRECTOR_BOARD_MISSING", r["codes"])

    def test_placeholder_fields_flagged(self) -> None:
        board = {f: "needs_authoring" for f in DIRECTOR_BOARD_FIELDS}
        board["approval_state"] = "draft"
        r = lint_director_board([_scene(board=board)])
        self.assertFalse(r["ok"])
        self.assertIn("DIRECTOR_BOARD_FIELD_MISSING", r["codes"])
        self.assertEqual(len(r["issues"]), len(DIRECTOR_BOARD_FIELDS))

    def test_authored_board_passes(self) -> None:
        board = {f: f"value-{f}" for f in DIRECTOR_BOARD_FIELDS}
        board["approval_state"] = "approved"
        r = lint_director_board([_scene(board=board)])
        self.assertTrue(r["ok"], r)

    def test_invalid_approval_state_warns(self) -> None:
        board = {f: f"value-{f}" for f in DIRECTOR_BOARD_FIELDS}
        board["approval_state"] = "bogus"
        r = lint_director_board([_scene(board=board)])
        self.assertFalse(r["ok"])
        self.assertIn("DIRECTOR_BOARD_APPROVAL_INVALID", r["codes"])


class ValidateFilmSpecIntegrationTests(unittest.TestCase):
    def test_write_spec_attaches_performance_and_board_reports(self) -> None:
        spec = _spec()
        validate_film_spec(spec, assign_missing_ids=True)
        self.assertIn("_performance_lint", spec)
        self.assertIn("_director_board_lint", spec)
        # default example has no board → warns (soft)
        self.assertFalse(spec["_performance_lint"]["ok"])
        self.assertFalse(spec["_director_board_lint"]["ok"])

    def test_performance_strict_raises(self) -> None:
        spec = _spec()
        spec["performance_strict"] = True
        with self.assertRaises(FilmSpecError) as cm:
            validate_film_spec(spec, assign_missing_ids=True)
        self.assertIn("performance_strict", str(cm.exception))

    def test_scene_strict_raises_on_missing_board(self) -> None:
        spec = _spec()
        spec["scene_strict"] = True
        with self.assertRaises(FilmSpecError) as cm:
            validate_film_spec(spec, assign_missing_ids=True)
        self.assertIn("scene_strict", str(cm.exception))

    def test_strict_passes_when_authored(self) -> None:
        shot = _shot(
            subtext="lock him in",
            playable_action="reaches for lock",
            body_state="tremble",
        )
        board = {f: f"v-{f}" for f in DIRECTOR_BOARD_FIELDS}
        board["approval_state"] = "approved"
        spec = _spec([_scene([shot], board)])
        spec["performance_strict"] = True
        spec["scene_strict"] = True
        validate_film_spec(spec, assign_missing_ids=True)
        self.assertTrue(spec["_performance_lint"]["ok"])
        self.assertTrue(spec["_director_board_lint"]["ok"])


if __name__ == "__main__":
    unittest.main()
