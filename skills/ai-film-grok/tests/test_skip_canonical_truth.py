"""S1.2 · --skip-canonical-truth / AIFILM_SKIP_CANONICAL_TRUTH contract."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_require_blocks_canonical_graph_when_not_ok(tmp_path: Path) -> None:
    import production_truth

    with mock.patch.object(
        production_truth,
        "audit_production_truth",
        return_value={
            "ok": False,
            "checks": {"canonical_graph": {"canonical": True}},
            "blockers": ["GRAPH_STALE"],
        },
    ):
        with pytest.raises(production_truth.ProductionTruthError, match="GRAPH_STALE"):
            production_truth.require_current_canonical_truth(tmp_path)


def test_require_allows_non_canonical_even_if_audit_red(tmp_path: Path) -> None:
    """Legacy / incomplete graph: audit may be red but not raise (compat path)."""
    import production_truth

    with mock.patch.object(
        production_truth,
        "audit_production_truth",
        return_value={
            "ok": False,
            "checks": {"canonical_graph": {"canonical": False}},
            "blockers": ["MANIFEST_TRUTH_INVALID"],
        },
    ):
        rep = production_truth.require_current_canonical_truth(tmp_path)
        assert rep["ok"] is False


def test_skip_env_documented_for_h3_native_only() -> None:
    """Contract: skip is escape hatch, not default for drama series lock."""
    help_blob = Path(SCRIPTS / "cli" / "cli_post.py").read_text(encoding="utf-8")
    assert "--skip-canonical-truth" in help_blob
    assert "AIFILM_SKIP_CANONICAL_TRUTH" in help_blob
