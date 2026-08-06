"""Fail-closed discipline for production gates (P0-1, senior-dev quality plan).

A safety gate must NEVER silently swallow an unexpected exception and then
return ``{"ok": True}``. If a verification subsystem errors, the gate must
block (fail-closed), not pass.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest import mock

import pytest


def _make_user_approved_root(tmp_path: Path) -> Path:
    root = tmp_path / "film"
    rec = root / "receipts"
    rec.mkdir(parents=True)
    (root / "film-spec.json").write_text(json.dumps({}), encoding="utf-8")
    (rec / "pilot-approval.json").write_text(
        json.dumps(
            {
                "approved": True,
                "approved_by": "user",
                "user_phrase": "pilot 过",
                "shots": ["shot01"],
            }
        ),
        encoding="utf-8",
    )
    return root


def test_pilot_bulk_check_unexpected_error_is_fail_closed(tmp_path: Path) -> None:
    """A non-gate exception from the bulk allow-check must block, not pass."""
    from production_gates import ProductionGateError, assert_pilot_allows_add

    root = _make_user_approved_root(tmp_path)

    stub = types.ModuleType("pilot_pack")

    def _boom(root, force: bool = False) -> None:  # pragma: no cover - injected
        raise ValueError("injected bulk-check failure")

    stub.assert_pilot_go_allows_bulk = _boom

    with mock.patch.dict(sys.modules, {"pilot_pack": stub}):
        with pytest.raises(ProductionGateError):
            assert_pilot_allows_add(
                root, shot_id="shot01", existing_shot_ids=set(), env_skip=False
            )


def test_pilot_bulk_check_production_error_propagates(tmp_path: Path) -> None:
    """A ProductionGateError from the bulk allow-check propagates unchanged."""
    from production_gates import ProductionGateError, assert_pilot_allows_add

    root = _make_user_approved_root(tmp_path)

    stub = types.ModuleType("pilot_pack")

    def _boom(root, force: bool = False) -> None:  # pragma: no cover - injected
        raise ProductionGateError("HARD bulk block")

    stub.assert_pilot_go_allows_bulk = _boom

    with mock.patch.dict(sys.modules, {"pilot_pack": stub}):
        with pytest.raises(ProductionGateError, match="HARD bulk block"):
            assert_pilot_allows_add(
                root, shot_id="shot01", existing_shot_ids=set(), env_skip=False
            )
