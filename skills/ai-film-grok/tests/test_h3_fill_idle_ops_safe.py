"""Fill-Idle capacity plan must not default overnight until-empty without exclusive flag."""

from __future__ import annotations

from pathlib import Path

from h3_fill_idle import capacity_plan


def test_capacity_plan_safe_ops(tmp_path: Path):
    (tmp_path / "film-spec.json").write_text("{}", encoding="utf-8")
    plan = capacity_plan(tmp_path)
    ops = "\n".join(plan.get("ops") or [])
    assert "run-next" in ops
    assert "--i-own-the-gpu" in ops
    assert plan.get("default_safe") == "run-next --max 5"
    bare = [
        o
        for o in (plan.get("ops") or [])
        if "until-empty" in o and "--execute" in o and "--i-own-the-gpu" not in o
    ]
    assert not bare
