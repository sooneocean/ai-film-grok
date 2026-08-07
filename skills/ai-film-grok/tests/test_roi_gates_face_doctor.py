"""ROI follow-up: gates fail-closed (face still) + doctor F5 face probe + heat smoke."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_still_face_lock_resolve_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from gates import still_face_lock_bind as m

    root = tmp_path
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scenes": [
                    {
                        "shots": [
                            {
                                "id": "s01",
                                "dramatic_function": "dialogue",
                                "cast": ["hero"],
                            }
                        ]
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "receipts").mkdir(parents=True, exist_ok=True)

    import media.still_source as ss

    def boom(*_a, **_k):
        raise RuntimeError("resolve exploded")

    monkeypatch.setattr(ss, "resolve_still_source", boom)
    rep = m.audit_film_still_face_lock_bind(root, write_receipt=False)
    assert rep.get("ok") is False
    assert "STILL_SOURCE_RESOLVE_FAILED" in (rep.get("codes") or [])
    hard = rep.get("hard") or []
    assert any("STILL_SOURCE_RESOLVE_FAILED" in str(h) for h in hard)


def test_still_provenance_manifest_read_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gates import still_provenance as sp
    import util

    def bad_read(_path):
        raise OSError("disk gone")

    monkeypatch.setattr(util, "read_json", bad_read)
    rep = sp.audit_film_still_provenance(tmp_path)
    assert rep.get("ok") is False
    assert "STILL_PROVENANCE_MANIFEST_READ_FAILED" in (rep.get("codes") or [])


def test_doctor_face_f5_probe_logic(tmp_path: Path) -> None:
    """Unit the face probe contract without full doctor stack."""
    root = tmp_path / "film"
    root.mkdir()
    (root / "film-spec.json").write_text(
        json.dumps({"schema_version": 1, "cast_voices": {"hero": "zh-CN-XiaoyiNeural"}}),
        encoding="utf-8",
    )
    (root / "style-bible.json").write_text(
        json.dumps({"characters": [{"id": "hero", "name": "H", "is_lead": True}]}),
        encoding="utf-8",
    )
    (root / "receipts").mkdir()
    (root / "receipts" / "face-identity.json").write_text(
        json.dumps({"enrolled": {}}),
        encoding="utf-8",
    )

    from util import read_json

    try:
        from assets.face_identity import load_receipt
    except ImportError:
        from face_identity import load_receipt  # type: ignore

    receipt = load_receipt(root)
    enrolled = receipt.get("enrolled") if isinstance(receipt.get("enrolled"), dict) else {}
    bible = read_json(root / "style-bible.json") or {}
    lead_ids = []
    for c in bible.get("characters") or []:
        if isinstance(c, dict) and c.get("is_lead") and c.get("id"):
            lead_ids.append(str(c["id"]))
    missing = [cid for cid in lead_ids if cid not in enrolled]
    assert missing == ["hero"]
    next_cmd = f'aifilm face-identity enroll-bible --root "{root}"'
    assert "enroll-bible" in next_cmd

    # source contract: doctor embeds this probe when --root set
    src = (SCRIPTS / "cli" / "cli_status.py").read_text(encoding="utf-8")
    assert "face-identity-doctor" in src
    assert "FACE_IDENTITY_ENROLL_GAP" in src
    assert "FACE_IDENTITY_VERIFIED_FALSE" in src


def test_heat_plot_driven_smoke_tmp_root(tmp_path: Path) -> None:
    """Synthetic film smoke: plot-driven brief is not max-pinned."""
    from story_plan import build_planned_graph, normalize_story, project_graph_to_film_spec
    from narrative.heat_check import heat_check, _is_explicit_max_spec

    norm = normalize_story("雨夜出租车里的一次对话，两人靠近说话。", title_hint="雨夜冒烟")
    assert norm["heat_signals"]["heat_scale"] == "hot"
    assert norm["heat_signals"]["pinned_by"] == "plot_driven"
    graph = build_planned_graph(norm, target_duration=40.0)
    spec = project_graph_to_film_spec(graph, normalized=norm)
    assert spec.get("heat_scale") == "hot"
    assert spec.get("heat_pinned_by") == "plot_driven"
    assert not _is_explicit_max_spec(spec)
    assert spec.get("challenge_max_scale") is not True

    root = tmp_path / "smoke"
    root.mkdir()
    (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    rep = heat_check(root)
    assert rep.get("explicit_max") is False
    assert rep.get("hard_relevant_codes") == []
    (root / "receipts").mkdir(exist_ok=True)
    smoke = {
        "ok": True,
        "heat_scale": spec.get("heat_scale"),
        "heat_pinned_by": spec.get("heat_pinned_by"),
        "explicit_max": False,
        "heat_check_ok": rep.get("ok"),
    }
    (root / "receipts" / "heat-plot-driven-smoke.json").write_text(
        json.dumps(smoke, indent=2), encoding="utf-8"
    )
    assert smoke["ok"] is True
