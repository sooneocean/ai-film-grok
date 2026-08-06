#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cli_plan_mutation import PlanMutationError, run  # noqa: E402


def test_top_level_plan_edit_delegates_to_extracted_mutation(monkeypatch, tmp_path, capsys) -> None:
    import aifilm_grok
    import cli_plan_mutation

    calls: list[tuple[str, Path]] = []

    def fake_run(args: Namespace, root: Path) -> tuple[dict[str, object], int]:
        calls.append((args.plan_action, root))
        return {"ok": True, "action": args.plan_action, "route": "extracted"}, 0

    monkeypatch.setattr(cli_plan_mutation, "run", fake_run)

    code = aifilm_grok.main(
        [
            "plan",
            "edit",
            "--root",
            str(tmp_path),
            "--node",
            "story",
            "--set",
            "title=Updated",
        ]
    )

    assert code == 0
    assert calls == [("edit", tmp_path.resolve())]
    assert json.loads(capsys.readouterr().out)["route"] == "extracted"


class PlanMutationRouteTests(unittest.TestCase):
    def test_plan_parser_domain_preserves_lock_and_run_contracts(self) -> None:
        from cli_plan import add_plan_parsers

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="cmd", required=True)
        add_plan_parsers(subparsers)

        run_args = parser.parse_args(
            [
                "plan",
                "run",
                "--root",
                "film",
                "--received-file",
                "reception.json",
                "--target-duration",
                "60",
                "--apply-film-spec",
            ]
        )
        lock_args = parser.parse_args(
            ["plan", "lock", "--root", "film", "--scope", "shots", "--user-phrase", "approved"]
        )
        replan_args = parser.parse_args(
            ["plan", "replan", "--root", "film", "--node", "story", "--descendants"]
        )

        self.assertEqual(run_args.plan_action, "run")
        self.assertEqual(run_args.target_duration, 60.0)
        self.assertTrue(run_args.apply_film_spec)
        self.assertEqual(lock_args.scope, "shots")
        self.assertTrue(replan_args.descendants)

    def test_missing_graph_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PlanMutationError) as ctx:
                run(Namespace(plan_action="edit", node="story", set=["goal=x"]), Path(tmp))
            self.assertEqual(ctx.exception.code, "GRAPH_MISSING")

    def test_replan_requires_explicit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "drama-graph.json").write_text('{"schema_version": 2}\n', encoding="utf-8")
            with self.assertRaises(PlanMutationError) as ctx:
                run(Namespace(plan_action="replan", node="story", descendants=False), root)
            self.assertEqual(ctx.exception.code, "DESCENDANTS_CONFIRM_REQUIRED")


if __name__ == "__main__":
    unittest.main()
