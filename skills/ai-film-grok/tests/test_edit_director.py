"""edit_director — cut plan + engine route desk (no second director system)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_director import (  # noqa: E402
    EditDirectorError,
    apply_plan,
    build_run_plan,
    draft_and_save,
    draft_plan,
    normalize_plan,
    plan_path,
    set_plan_fields,
    status,
)


def _mini_spec(*shot_ids: str) -> dict:
    return {
        "scenes": [
            {
                "id": "s1",
                "shots": [{"id": sid, "duration_sec": 5} for sid in shot_ids],
            }
        ]
    }


def test_draft_assembly_when_no_clips(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01", "sh02")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    plan = draft_plan(tmp_path)
    assert plan["schema"] == "aifilm-edit-director-plan-v1"
    assert plan["cut_state"] == "assembly"
    assert plan["engine_route"]["design"] == "hyperframes"
    assert plan["engine_route"]["caption_path"] == "master_hf"
    assert plan["engine_route"]["plate_subs"] == "off"
    assert plan["engine_route"]["plate_cards"] == "blank"
    assert plan["join_policy"]["continue_join"] == "hard"
    assert len(plan["errors"]) == 2
    assert plan["stats"]["missing_count"] == 2


def test_draft_remotion_explicit(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    plan = draft_plan(tmp_path, design="remotion")
    assert plan["engine_route"]["design"] == "remotion"
    assert plan["engine_route"]["post_engine"] == "remotion"
    assert plan["engine_route"]["caption_path"] == "master_hf"


def test_prefer_ship_none_design(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    plan = draft_plan(tmp_path, prefer_ship=True)
    assert plan["engine_route"]["design"] == "none"
    assert plan["engine_route"]["post_engine"] == "ffmpeg"
    assert plan["engine_route"]["caption_path"] == "ship_hardburn"
    assert plan["engine_route"]["plate_subs"] == "burn"


def test_rough_when_approved_clips(tmp_path: Path) -> None:
    clip = tmp_path / "takes" / "sh01.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"fake")
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "clips": {
                    "sh01": {
                        "path": str(clip),
                        "status": "approved",
                        "state": "active",
                        "duration_sec": 5.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    plan = draft_plan(tmp_path)
    assert plan["cut_state"] == "rough"
    assert not plan["errors"]
    assert plan["stats"]["ready_count"] == 1


def test_normalize_rejects_bad_cut(tmp_path: Path) -> None:
    with pytest.raises(EditDirectorError, match="cut_state"):
        normalize_plan({"cut_state": "magic", "shot_ids": [], "engine_route": {}})


def test_draft_and_save_refuse_overwrite(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text("{}", encoding="utf-8")
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    draft_and_save(tmp_path)
    assert plan_path(tmp_path).is_file()
    with pytest.raises(EditDirectorError, match="exists"):
        draft_and_save(tmp_path, force=False)


def test_set_design_and_status(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    draft_and_save(tmp_path, force=True)
    plan = set_plan_fields(tmp_path, design="remotion", cut_state="fine")
    assert plan["engine_route"]["design"] == "remotion"
    assert plan["cut_state"] == "fine"
    st = status(tmp_path)
    assert st["blocked_by"]  # still missing clips
    assert st["engine_route"]["design"] == "remotion"


def test_run_dry_run_stages(tmp_path: Path) -> None:
    clip = tmp_path / "takes" / "sh01.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"fake")
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "clips": {
                    "sh01": {
                        "path": str(clip),
                        "status": "approved",
                        "state": "active",
                        "duration_sec": 4.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    draft_and_save(tmp_path, force=True)
    report = build_run_plan(tmp_path, execute=False)
    assert report["dry_run"] is True
    assert report["ok"] is True
    ids = [s["id"] for s in report["stages"]]
    assert "plate" in ids
    assert "design" in ids
    assert report["next_cmd"] and "hyperframes" in report["next_cmd"]
    assert (tmp_path / "receipts" / "edit-director-run.json").is_file()


def test_apply_writes_post_route(tmp_path: Path) -> None:
    clip = tmp_path / "takes" / "sh01.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"fake")
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "clips": {
                    "sh01": {
                        "path": str(clip),
                        "status": "approved",
                        "state": "active",
                        "duration_sec": 4.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    draft_and_save(tmp_path, force=True)
    receipt = apply_plan(tmp_path)
    assert (tmp_path / "receipts" / "edit-director-apply.json").is_file()
    route = json.loads(
        (tmp_path / "receipts" / "post-route.json").read_text(encoding="utf-8")
    )
    assert route["caption_path"] == "master_hf"
    assert route.get("source") == "edit-director-plan" or receipt.get("post_route_ok")


def test_post_plan_owner_inherited(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("a")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "post-plan.json").write_text(
        json.dumps({"post_owner": "remotion", "version": 1}), encoding="utf-8"
    )
    plan = draft_plan(tmp_path)
    assert plan["engine_route"]["design"] == "remotion"


def test_execute_with_injected_runner(tmp_path: Path) -> None:
    from edit_director import build_run_plan

    clip = tmp_path / "takes" / "sh01.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"fake")
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "clips": {
                    "sh01": {
                        "path": str(clip),
                        "status": "approved",
                        "state": "active",
                        "duration_sec": 4.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    draft_and_save(tmp_path, force=True)
    seen: list[list[str]] = []

    def runner(argv: list[str]) -> dict:
        seen.append(argv)
        return {"ok": True, "returncode": 0, "stub": True}

    report = build_run_plan(tmp_path, execute=True, final_runner=runner)
    assert report["executed"] is True
    assert report["ok"] is True
    assert seen and "final" in seen[0]
    assert "--post-engine" in seen[0]
    assert (tmp_path / "receipts" / "edit-director-run.json").is_file()
    assert (tmp_path / "receipts" / "post-route.json").is_file()


def test_snapshot_activate_and_audit(tmp_path: Path) -> None:
    from edit_director import (
        activate_cut,
        audit_desk,
        list_cuts,
        load_plan,
        snapshot_cut,
    )

    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    draft_and_save(tmp_path, force=True, design="hyperframes")
    snap = snapshot_cut(tmp_path, "rough-v1")
    assert snap["ok"] is True
    set_plan_fields(tmp_path, design="remotion")
    assert load_plan(tmp_path, required=True)["engine_route"]["design"] == "remotion"
    act = activate_cut(tmp_path, "rough-v1")
    assert act["ok"] is True
    assert load_plan(tmp_path, required=True)["engine_route"]["design"] == "hyperframes"
    listed = list_cuts(tmp_path)
    assert "rough-v1" in listed["cuts"]
    assert listed["active"] == "rough-v1"
    report = audit_desk(tmp_path, write=True)
    assert "issues" in report
    assert (tmp_path / "receipts" / "edit-director-audit.json").is_file()


def test_sync_post_plan_on_apply(tmp_path: Path) -> None:
    from edit_director import apply_plan, draft_and_save

    clip = tmp_path / "takes" / "sh01.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"fake")
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "clips": {
                    "sh01": {
                        "path": str(clip),
                        "status": "approved",
                        "state": "active",
                        "duration_sec": 4.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    draft_and_save(tmp_path, force=True, design="hyperframes")
    assert not (tmp_path / "post-plan.json").is_file()
    receipt = apply_plan(tmp_path)
    assert receipt.get("post_plan_sync", {}).get("ok") is True
    assert (tmp_path / "post-plan.json").is_file()
    pp = json.loads((tmp_path / "post-plan.json").read_text(encoding="utf-8"))
    assert pp.get("post_owner") == "hyperframes"
    # redesign → remotion realigns post-plan owner
    from edit_director import set_plan_fields

    set_plan_fields(tmp_path, design="remotion")
    receipt2 = apply_plan(tmp_path)
    assert receipt2.get("post_plan_sync", {}).get("ok") is True
    pp2 = json.loads((tmp_path / "post-plan.json").read_text(encoding="utf-8"))
    assert pp2.get("post_owner") == "remotion"


def test_editorial_edl_and_trims(tmp_path: Path) -> None:
    from edit_director import draft_plan, export_checklist, normalize_plan, save_plan

    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    edl_dir = tmp_path / "edit"
    edl_dir.mkdir()
    (edl_dir / "edl.json").write_text(
        json.dumps(
            {
                "ranges": [
                    {"shot_id": "sh01", "in": 0.5, "out": 3.2, "source_type": "real"}
                ]
            }
        ),
        encoding="utf-8",
    )
    plan = draft_plan(tmp_path)
    assert plan["editorial"]["edl"] == "edit/edl.json"
    assert "real_footage" in plan["editorial"]["source_types"]
    assert plan["editorial"]["trims"]
    assert plan["editorial"]["trims"][0]["in_sec"] == 0.5
    # bad trim fails closed
    bad = dict(plan)
    bad["editorial"] = {
        "edl": "edit/edl.json",
        "source_types": ["generated_clip"],
        "trims": [{"shot_id": "x", "in_sec": 5, "out_sec": 1}],
    }
    with pytest.raises(EditDirectorError, match="in_sec"):
        normalize_plan(bad, root=tmp_path)
    save_plan(tmp_path, plan, force=True)
    cl = export_checklist(tmp_path, write=True)
    assert (tmp_path / "receipts" / "edit-director-checklist.md").is_file()
    assert cl.get("steps")


def test_resolve_final_defaults_from_plan(tmp_path: Path) -> None:
    from edit_director import resolve_final_defaults

    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    draft_and_save(tmp_path, force=True, design="remotion")
    # No CLI flags → plan wins
    resolved = resolve_final_defaults(
        tmp_path,
        post_engine="hyperframes",
        caption_path=None,
        argv=["aifilm", "final", "--root", str(tmp_path)],
    )
    assert resolved["post_engine"] == "remotion"
    assert resolved["caption_path"] == "master_hf"
    assert resolved["source"] == "edit-director-plan"
    # Explicit CLI wins
    resolved2 = resolve_final_defaults(
        tmp_path,
        post_engine="ffmpeg",
        caption_path="ship_hardburn",
        argv=[
            "aifilm",
            "final",
            "--root",
            str(tmp_path),
            "--post-engine",
            "ffmpeg",
            "--caption-path",
            "ship_hardburn",
        ],
    )
    assert resolved2["post_engine"] == "ffmpeg"
    assert resolved2["caption_path"] == "ship_hardburn"
    assert resolved2["source"] == "cli"


def test_post_doctor_edit_director_section(tmp_path: Path) -> None:
    from post_doctor import run_post_doctor

    (tmp_path / "film-spec.json").write_text("{}", encoding="utf-8")
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    rep = run_post_doctor(tmp_path, write=False)
    soft_codes = [i.get("code") for i in rep.get("soft") or []]
    assert "EDIT_DIRECTOR_UNSET" in soft_codes
    draft_and_save(tmp_path, force=True)
    (tmp_path / "receipts").mkdir(exist_ok=True)
    (tmp_path / "receipts" / "post-route.json").write_text(
        json.dumps(
            {
                "kind": "post-route",
                "caption_path": "ship_hardburn",
                "plate_subs": "burn",
            }
        ),
        encoding="utf-8",
    )
    rep2 = run_post_doctor(tmp_path, write=False)
    hard_codes = [i.get("code") for i in rep2.get("hard") or []]
    soft_codes2 = [i.get("code") for i in rep2.get("soft") or []]
    assert "EDIT_DIRECTOR_PLAN" in soft_codes2
    assert "EDIT_DIRECTOR_ROUTE_MISMATCH" in hard_codes


def test_closeout_prefers_edit_director_cmd(tmp_path: Path) -> None:
    from closeout import _final_next_cmd

    clip = tmp_path / "takes" / "sh01.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"x")
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "clips": {
                    "sh01": {
                        "path": str(clip),
                        "status": "approved",
                        "state": "active",
                        "duration_sec": 4.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    draft_and_save(tmp_path, force=True, design="hyperframes")
    cmd = _final_next_cmd(tmp_path)
    assert "edit-director" in cmd or "hyperframes" in cmd


def test_next_actions_suggests_edit_director(tmp_path: Path) -> None:
    from next_actions import build_next_actions

    clip = tmp_path / "takes" / "sh01.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"x")
    (tmp_path / "brief.json").write_text(
        json.dumps({"title": "ed", "theme": "test"}), encoding="utf-8"
    )
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_mini_spec("sh01")), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "gates": {
                    "brief": True,
                    "style_locked": True,
                    "spec": True,
                    "clips_complete": True,
                    "final_complete": False,
                },
                "clips": {
                    "sh01": {
                        "path": str(clip),
                        "status": "approved",
                        "state": "active",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    rec = tmp_path / "receipts"
    rec.mkdir(parents=True)
    (rec / "pilot-approval.json").write_text(
        json.dumps(
            {
                "approved": True,
                "approved_by": "user",
                "user_phrase": "pilot 过",
                "shots": ["sh01"],
            }
        ),
        encoding="utf-8",
    )
    # debrief optional: many trees skip if no story text — if required, skip gate
    gates = {
        "brief": True,
        "style_locked": True,
        "spec": True,
        "clips_complete": True,
        "final_complete": False,
        "desktop_exported": False,
    }
    actions = build_next_actions(tmp_path, gates=gates)
    ids = [a.get("id") for a in actions]
    assert "edit-director-draft" in ids
