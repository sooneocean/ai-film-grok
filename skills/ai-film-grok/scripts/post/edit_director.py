#!/usr/bin/env python3
"""Edit Director desk — orchestrate final cut + engine route (no second director system).

Single source of truth: ``post/edit-director-plan.json``.

Mirrors music_director verbs: draft / normalize / set / apply / run / status.

- FFmpeg always owns plate / timeline / mix / SRT truth.
- One designed-post owner per episode: hyperframes (default) or remotion (explicit).
- Does not re-implement render_final; run only composes flags + optional final_stages.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from util import read_json, sha256_file, utc_now, write_json
from util.errors import FilmError

SCHEMA = "aifilm-edit-director-plan-v1"
PLAN_REL = Path("post") / "edit-director-plan.json"
APPLY_RECEIPT_REL = Path("receipts") / "edit-director-apply.json"
RUN_RECEIPT_REL = Path("receipts") / "edit-director-run.json"
AUDIT_RECEIPT_REL = Path("receipts") / "edit-director-audit.json"
CUTS_DIR_REL = Path("post") / "cuts"
ACTIVE_CUT_REL = Path("post") / "cuts" / "active.json"

FinalRunner = Callable[[list[str]], dict[str, Any]]

CUT_STATES = (
    "assembly",
    "rough",
    "fine",
    "director",
    "picture_lock",
    "master",
)
DESIGN_OWNERS = frozenset({"hyperframes", "remotion", "none"})
CAPTION_PATHS = frozenset({"master_hf", "ship_hardburn"})
_CUT_RANK = {name: i for i, name in enumerate(CUT_STATES)}


class EditDirectorError(FilmError):
    """Plan / apply failures for the edit director desk."""


def plan_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / PLAN_REL


def apply_receipt_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / APPLY_RECEIPT_REL


def run_receipt_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / RUN_RECEIPT_REL


def audit_receipt_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / AUDIT_RECEIPT_REL


def cuts_dir(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / CUTS_DIR_REL


def active_cut_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / ACTIVE_CUT_REL


def _flatten_shot_ids(spec: dict[str, Any] | None) -> list[str]:
    out: list[str] = []
    if not isinstance(spec, dict):
        return out
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            sid = str(shot.get("id") or "").strip()
            if sid:
                out.append(sid)
    return out


def _clips_map(root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json(root / "manifest.json") or {}
    clips = manifest.get("clips")
    return clips if isinstance(clips, dict) else {}


def _approved_clip_ok(clip: dict[str, Any] | None) -> bool:
    if not isinstance(clip, dict):
        return False
    path = Path(str(clip.get("path") or ""))
    if not path.is_file():
        return False
    if clip.get("status") != "approved":
        return False
    state = clip.get("state")
    return state in {None, "active"}


def _resolve_design(
    *,
    explicit_design: str | None,
    post_plan_owner: str | None,
    prefer_ship: bool,
) -> str:
    if prefer_ship:
        return "none"
    raw = str(explicit_design or post_plan_owner or "hyperframes").strip().lower()
    if raw in {"ffmpeg", "none", "off"}:
        return "none"
    if raw == "remotion":
        return "remotion"
    if raw == "hyperframes":
        return "hyperframes"
    raise EditDirectorError(
        f"design owner must be hyperframes|remotion|none (got {explicit_design!r})"
    )


def _engine_route_for_design(design: str) -> dict[str, Any]:
    if design == "none":
        return {
            "plate": "ffmpeg",
            "design": "none",
            "post_engine": "ffmpeg",
            "caption_path": "ship_hardburn",
            "plate_subs": "burn",
            "plate_cards": "text",
        }
    # designed post: plate blank + subs off; HF/Remotion owns glyphs
    return {
        "plate": "ffmpeg",
        "design": design,
        "post_engine": design,
        "caption_path": "master_hf",
        "plate_subs": "off",
        "plate_cards": "blank",
    }


def _audio_handoff(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    md_rel = Path("audio") / "music-director-plan.json"
    md_path = root / md_rel
    apply_path = root / "receipts" / "music-director-apply.json"
    prefer = bool(spec.get("prefer_native")) or str(
        (spec.get("audio") or {}).get("prefer_native") or ""
    ).lower() in {"1", "true", "yes"}
    # also common: dialogue_audio_lane / native flags on post
    post = spec.get("post") if isinstance(spec.get("post"), dict) else {}
    if post.get("prefer_native") is True:
        prefer = True
    sha = sha256_file(md_path) if md_path.is_file() else None
    return {
        "music_director_plan": str(md_rel) if md_path.is_file() else None,
        "music_director_plan_sha256": sha,
        "music_director_apply_present": apply_path.is_file(),
        "prefer_native": prefer,
    }


def _join_policy(spec: dict[str, Any]) -> dict[str, Any]:
    es = spec.get("edit_strategy") if isinstance(spec.get("edit_strategy"), dict) else {}
    mode = str(es.get("mode") or "auto").strip().lower()
    if mode not in {"off", "auto", "voice_coupled", "punchy", "silk"}:
        mode = "auto"
    return {
        "mode": mode,
        "continue_join": "hard",
        "soft_style_rotate": True,
    }


def _infer_cut_state(
    *,
    shot_ids: list[str],
    missing: list[str],
    unapproved: list[str],
    root: Path,
) -> str:
    if not shot_ids or missing or unapproved:
        return "assembly"
    pl = read_json(root / "receipts" / "picture-lock.json") or {}
    if pl.get("ok") is True or pl.get("locked") is True:
        final = root / "out" / "film_final.mp4"
        if final.is_file() and (root / "receipts" / "final-delivery.json").is_file():
            return "master"
        return "picture_lock"
    editor = read_json(root / "receipts" / "editor-cut.json") or {}
    if editor.get("ok") is True:
        return "rough"
    return "rough"


def draft_plan(
    root: Path | str,
    *,
    design: str | None = None,
    prefer_ship: bool = False,
    force_cut_state: str | None = None,
) -> dict[str, Any]:
    """Build edit-director plan from film-spec + manifest clips + post-plan owner."""
    base = Path(root).expanduser().resolve()
    spec = read_json(base / "film-spec.json") or {}
    if not isinstance(spec, dict):
        spec = {}
    post_plan = read_json(base / "post-plan.json") or {}
    owner = None
    if isinstance(post_plan, dict):
        owner = str(post_plan.get("post_owner") or post_plan.get("render", {}).get("engine") or "")
        owner = owner or None

    design_owner = _resolve_design(
        explicit_design=design,
        post_plan_owner=owner,
        prefer_ship=prefer_ship,
    )
    engine_route = _engine_route_for_design(design_owner)

    shot_ids = _flatten_shot_ids(spec)
    clips = _clips_map(base)
    missing: list[str] = []
    unapproved: list[str] = []
    for sid in shot_ids:
        clip = clips.get(sid) if isinstance(clips.get(sid), dict) else None
        if clip is None or not Path(str(clip.get("path") or "")).is_file():
            missing.append(sid)
        elif not _approved_clip_ok(clip):
            unapproved.append(sid)

    errors: list[dict[str, Any]] = []
    for sid in missing:
        errors.append(
            {
                "code": "EDIT_CLIP_MISSING",
                "shot_id": sid,
                "message": "registered clip file missing",
            }
        )
    for sid in unapproved:
        errors.append(
            {
                "code": "EDIT_CLIP_NOT_APPROVED",
                "shot_id": sid,
                "message": "clip not approved active take",
            }
        )

    cut_state = force_cut_state or _infer_cut_state(
        shot_ids=shot_ids,
        missing=missing,
        unapproved=unapproved,
        root=base,
    )
    if cut_state not in CUT_STATES:
        raise EditDirectorError(f"invalid cut_state {cut_state!r}")

    notes: list[str] = [
        "continue joins always hard (no designed dissolve on byte-identical seams)",
        "edit-director orchestrates; does not re-implement render_final",
    ]
    if design_owner == "remotion":
        notes.append("remotion is explicit design owner for this episode")
    if design_owner == "none":
        notes.append("design=none → ship_hardburn plate path")

    plan: dict[str, Any] = {
        "schema": SCHEMA,
        "kind": "edit-director-plan",
        "version": 1,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "source": "draft",
        "cut_state": cut_state,
        "shot_ids": shot_ids,
        "engine_route": engine_route,
        "join_policy": _join_policy(spec),
        "recovery": {
            "caption_fallback": "pil_hardburn",
            "on_gate_red": "PARTIAL",
        },
        "audio_handoff": _audio_handoff(base, spec),
        "errors": errors,
        "notes": notes,
        "stats": {
            "shot_count": len(shot_ids),
            "missing_count": len(missing),
            "unapproved_count": len(unapproved),
            "ready_count": len(shot_ids) - len(missing) - len(unapproved),
        },
    }
    return normalize_plan(plan, root=base)


def normalize_plan(plan: dict[str, Any], *, root: Path | str | None = None) -> dict[str, Any]:
    """Validate and normalize plan; fail-closed on illegal engine combos."""
    if not isinstance(plan, dict):
        raise EditDirectorError("plan must be a JSON object")
    out = deepcopy(plan)
    out["schema"] = SCHEMA
    out["kind"] = "edit-director-plan"
    out["version"] = int(out.get("version") or 1)
    out["updated_at"] = utc_now()

    cut = str(out.get("cut_state") or "assembly").strip().lower()
    if cut not in CUT_STATES:
        raise EditDirectorError(f"cut_state must be one of {list(CUT_STATES)}")
    out["cut_state"] = cut

    shots = out.get("shot_ids")
    if not isinstance(shots, list):
        raise EditDirectorError("shot_ids must be a list")
    norm_shots: list[str] = []
    seen: set[str] = set()
    for item in shots:
        sid = str(item or "").strip()
        if not sid:
            raise EditDirectorError("shot_ids must be non-empty strings")
        if sid in seen:
            raise EditDirectorError(f"duplicate shot_id {sid!r}")
        seen.add(sid)
        norm_shots.append(sid)
    out["shot_ids"] = norm_shots

    route = out.get("engine_route")
    if not isinstance(route, dict):
        raise EditDirectorError("engine_route required")
    design = str(route.get("design") or "hyperframes").strip().lower()
    if design not in DESIGN_OWNERS:
        raise EditDirectorError(f"engine_route.design must be one of {sorted(DESIGN_OWNERS)}")
    # Re-derive plate/caption invariants from design (author may only pick design/caption overrides carefully)
    derived = _engine_route_for_design(design)
    caption = str(route.get("caption_path") or derived["caption_path"]).strip().lower()
    if caption not in CAPTION_PATHS:
        raise EditDirectorError(f"caption_path must be one of {sorted(CAPTION_PATHS)}")
    # Illegal: designed engine + ship_hardburn without explicit recovery intent is allowed but note
    # Illegal: remotion + hyperframes both as design — design is single enum so OK
    if design in {"hyperframes", "remotion"} and caption == "master_hf":
        derived["caption_path"] = "master_hf"
        derived["plate_subs"] = "off"
        derived["plate_cards"] = "blank"
    elif caption == "ship_hardburn":
        derived = {
            "plate": "ffmpeg",
            "design": design if design != "none" else "none",
            "post_engine": design if design in {"hyperframes", "remotion"} else "ffmpeg",
            "caption_path": "ship_hardburn",
            "plate_subs": "burn",
            "plate_cards": "text",
        }
        if design in {"hyperframes", "remotion"}:
            # ship path with designed engine = burned underlay; allow_burned_underlay
            derived["allow_burned_underlay"] = True
    else:
        derived["caption_path"] = caption
    # plate always ffmpeg
    derived["plate"] = "ffmpeg"
    derived["design"] = design
    if design == "none":
        derived["post_engine"] = "ffmpeg"
    elif "post_engine" not in derived or derived.get("post_engine") not in {
        "ffmpeg",
        "hyperframes",
        "remotion",
    }:
        derived["post_engine"] = design if design in {"hyperframes", "remotion"} else "ffmpeg"
    out["engine_route"] = derived

    recovery = out.get("recovery") if isinstance(out.get("recovery"), dict) else {}
    out["recovery"] = {
        "caption_fallback": str(recovery.get("caption_fallback") or "pil_hardburn"),
        "on_gate_red": str(recovery.get("on_gate_red") or "PARTIAL"),
    }
    if out["recovery"]["caption_fallback"] not in {"pil_hardburn", "none"}:
        raise EditDirectorError("recovery.caption_fallback must be pil_hardburn|none")
    if out["recovery"]["on_gate_red"] not in {"PARTIAL", "block"}:
        raise EditDirectorError("recovery.on_gate_red must be PARTIAL|block")

    join = out.get("join_policy") if isinstance(out.get("join_policy"), dict) else {}
    mode = str(join.get("mode") or "auto").strip().lower()
    if mode not in {"off", "auto", "voice_coupled", "punchy", "silk"}:
        mode = "auto"
    out["join_policy"] = {
        "mode": mode,
        "continue_join": "hard",
        "soft_style_rotate": bool(join.get("soft_style_rotate", True)),
    }

    if root is not None:
        base = Path(root).expanduser().resolve()
        spec = read_json(base / "film-spec.json") or {}
        if not isinstance(out.get("audio_handoff"), dict) or not out["audio_handoff"]:
            out["audio_handoff"] = _audio_handoff(base, spec if isinstance(spec, dict) else {})
        else:
            # refresh apply presence / sha if plan file exists
            hand = dict(out["audio_handoff"])
            md_path = base / "audio" / "music-director-plan.json"
            if md_path.is_file():
                hand["music_director_plan"] = "audio/music-director-plan.json"
                hand["music_director_plan_sha256"] = sha256_file(md_path)
            hand["music_director_apply_present"] = (
                base / "receipts" / "music-director-apply.json"
            ).is_file()
            out["audio_handoff"] = hand
    elif not isinstance(out.get("audio_handoff"), dict):
        out["audio_handoff"] = {
            "music_director_plan": None,
            "music_director_plan_sha256": None,
            "music_director_apply_present": False,
            "prefer_native": False,
        }

    if not isinstance(out.get("errors"), list):
        out["errors"] = []
    if not isinstance(out.get("notes"), list):
        out["notes"] = []
    return out


def load_plan(root: Path | str, *, required: bool = False) -> dict[str, Any] | None:
    path = plan_path(root)
    data = read_json(path)
    if data is None:
        if required:
            raise EditDirectorError(
                f"no plan at {path}; run: aifilm edit-director draft --root …"
            )
        return None
    if not isinstance(data, dict):
        raise EditDirectorError(f"corrupt plan at {path}")
    return normalize_plan(data, root=root)


def save_plan(root: Path | str, plan: dict[str, Any], *, force: bool = True) -> Path:
    base = Path(root).expanduser().resolve()
    path = plan_path(base)
    if path.is_file() and not force:
        raise EditDirectorError(f"plan exists at {path}; pass force=True to overwrite")
    normalized = normalize_plan(plan, root=base)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, normalized)
    return path


def draft_and_save(
    root: Path | str,
    *,
    design: str | None = None,
    prefer_ship: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    path = plan_path(base)
    if path.is_file() and not force:
        raise EditDirectorError(
            f"plan exists at {path}; use --force to overwrite or edit-director set"
        )
    plan = draft_plan(base, design=design, prefer_ship=prefer_ship)
    save_plan(base, plan, force=True)
    return plan


def set_plan_fields(
    root: Path | str,
    *,
    cut_state: str | None = None,
    design: str | None = None,
    caption_path: str | None = None,
    prefer_ship: bool | None = None,
) -> dict[str, Any]:
    """Human edits on plan; re-normalize invariants."""
    base = Path(root).expanduser().resolve()
    plan = load_plan(base, required=True)
    assert plan is not None
    if cut_state is not None:
        cs = str(cut_state).strip().lower()
        if cs not in CUT_STATES:
            raise EditDirectorError(f"cut_state must be one of {list(CUT_STATES)}")
        plan["cut_state"] = cs
    if prefer_ship is True:
        plan["engine_route"] = _engine_route_for_design("none")
    elif design is not None:
        d = _resolve_design(explicit_design=design, post_plan_owner=None, prefer_ship=False)
        plan["engine_route"] = _engine_route_for_design(d)
    if caption_path is not None:
        cp = str(caption_path).strip().lower().replace("-", "_")
        aliases = {
            "hf": "master_hf",
            "master": "master_hf",
            "ship": "ship_hardburn",
            "hardburn": "ship_hardburn",
        }
        cp = aliases.get(cp, cp)
        if cp not in CAPTION_PATHS:
            raise EditDirectorError(f"caption_path must be one of {sorted(CAPTION_PATHS)}")
        route = dict(plan.get("engine_route") or {})
        route["caption_path"] = cp
        plan["engine_route"] = route
    plan["source"] = "set"
    plan = normalize_plan(plan, root=base)
    save_plan(base, plan, force=True)
    return plan


def apply_plan(root: Path | str, *, write_route: bool = True) -> dict[str, Any]:
    """Regenerate editor_cut, optionally lock post_route from plan; write apply receipt.

    Does not render media. Draft take → cut stays assembly / errors fail soft on status.
    """
    base = Path(root).expanduser().resolve()
    plan = load_plan(base, required=True)
    assert plan is not None
    # Refresh readiness errors from live clips
    refreshed = draft_plan(
        base,
        design=str((plan.get("engine_route") or {}).get("design") or "hyperframes"),
        prefer_ship=str((plan.get("engine_route") or {}).get("design")) == "none",
    )
    # Preserve human cut_state if advanced past assembly and still ready
    if plan.get("cut_state") in CUT_STATES and _CUT_RANK[str(plan["cut_state"])] > _CUT_RANK[
        "assembly"
    ]:
        if not refreshed.get("errors"):
            refreshed["cut_state"] = plan["cut_state"]
        else:
            refreshed["cut_state"] = "assembly"
    else:
        # keep inferred from draft unless human set master etc. with no errors
        pass
    # Keep human join/recovery overrides
    if isinstance(plan.get("join_policy"), dict):
        refreshed["join_policy"] = plan["join_policy"]
    if isinstance(plan.get("recovery"), dict):
        refreshed["recovery"] = plan["recovery"]
    # Preserve design if human set remotion
    human_design = str((plan.get("engine_route") or {}).get("design") or "")
    if human_design in DESIGN_OWNERS:
        refreshed["engine_route"] = _engine_route_for_design(human_design)
        # re-apply caption override if ship
        cap = str((plan.get("engine_route") or {}).get("caption_path") or "")
        if cap in CAPTION_PATHS and cap != refreshed["engine_route"]["caption_path"]:
            refreshed["engine_route"]["caption_path"] = cap
            refreshed = normalize_plan(refreshed, root=base)

    refreshed = normalize_plan(refreshed, root=base)
    save_plan(base, refreshed, force=True)

    editor_report: dict[str, Any] | None = None
    try:
        from editor_cut import build_editor_cut_report

        editor_report = build_editor_cut_report(base, write=True)
    except Exception as exc:  # noqa: BLE001 — soft; apply still records
        editor_report = {"ok": False, "error": str(exc)[:200]}

    route_receipt: dict[str, Any] | None = None
    if write_route:
        try:
            from post_route import resolve_caption_path, write_post_route

            er = refreshed["engine_route"]
            route = resolve_caption_path(
                base,
                post_engine=str(er.get("post_engine") or "ffmpeg"),
                explicit=str(er.get("caption_path")),
            )
            # force plan caption into route
            route["caption_path"] = er["caption_path"]
            route["post_engine"] = er.get("post_engine") or route.get("post_engine")
            route["source"] = "edit-director-plan"
            route["plate_subs"] = er.get("plate_subs")
            route["plate_cards"] = er.get("plate_cards")
            route_receipt = write_post_route(base, route)
        except Exception as exc:  # noqa: BLE001
            route_receipt = {"ok": False, "error": str(exc)[:200]}

    receipt = {
        "schema": "aifilm-edit-director-apply-v1",
        "kind": "edit-director-apply",
        "at": utc_now(),
        "cut_state": refreshed.get("cut_state"),
        "shot_count": len(refreshed.get("shot_ids") or []),
        "errors": refreshed.get("errors") or [],
        "engine_route": refreshed.get("engine_route"),
        "editor_cut_ok": bool((editor_report or {}).get("ok")),
        "editor_cut": {
            "ok": (editor_report or {}).get("ok"),
            "shot_count": (editor_report or {}).get("shot_count"),
            "error": (editor_report or {}).get("error"),
        },
        "post_route": route_receipt,
        "plan_path": str(PLAN_REL),
        "ok": not bool(refreshed.get("errors"))
        and bool((editor_report or {}).get("ok"))
        and (route_receipt is None or route_receipt.get("ok") is not False),
    }
    # route write_json returns path dict without ok sometimes
    if isinstance(route_receipt, dict) and "path" in route_receipt and "error" not in route_receipt:
        receipt["ok"] = not bool(refreshed.get("errors")) and bool(
            (editor_report or {}).get("ok")
        )
        receipt["post_route_ok"] = True
    elif isinstance(route_receipt, dict) and route_receipt.get("error"):
        receipt["ok"] = False
        receipt["post_route_ok"] = False
    else:
        receipt["post_route_ok"] = write_route

    ap = apply_receipt_path(base)
    ap.parent.mkdir(parents=True, exist_ok=True)
    write_json(ap, receipt)
    receipt["path"] = str(ap)
    return receipt


def resolve_final_defaults(
    root: Path | str,
    *,
    post_engine: str | None = None,
    caption_path: str | None = None,
    argv: list[str] | None = None,
) -> dict[str, Any]:
    """Prefer edit-director plan for final routing when CLI did not set flags.

    Returns resolved post_engine / caption_path / plate flags + provenance.
    """
    base = Path(root).expanduser().resolve()
    args = list(argv if argv is not None else sys.argv)
    user_pe = any(a == "--post-engine" or a.startswith("--post-engine=") for a in args)
    user_cp = any(
        a == "--caption-path"
        or a.startswith("--caption-path=")
        or a == "--ship-hardburn"
        for a in args
    )
    pe = str(post_engine or "hyperframes").strip().lower()
    cp = str(caption_path or "").strip().lower() or None
    source = "cli" if (user_pe or user_cp) else "default"
    plan = load_plan(base, required=False)
    notes: list[str] = []
    if plan and not user_pe:
        er = plan.get("engine_route") if isinstance(plan.get("engine_route"), dict) else {}
        plan_pe = str(er.get("post_engine") or "").strip().lower()
        if plan_pe in {"ffmpeg", "hyperframes", "remotion"}:
            pe = plan_pe
            source = "edit-director-plan"
            notes.append(f"post_engine from edit-director ({pe})")
    if plan and not user_cp:
        er = plan.get("engine_route") if isinstance(plan.get("engine_route"), dict) else {}
        plan_cp = str(er.get("caption_path") or "").strip().lower()
        if plan_cp in CAPTION_PATHS:
            cp = plan_cp
            if source != "edit-director-plan":
                source = "edit-director-plan"
            notes.append(f"caption_path from edit-director ({cp})")
    if not cp:
        cp = "master_hf" if pe in {"hyperframes", "remotion"} else "ship_hardburn"
    return {
        "post_engine": pe,
        "caption_path": cp,
        "source": source,
        "notes": notes,
        "plan_present": plan is not None,
        "cut_state": (plan or {}).get("cut_state"),
    }


def build_final_argv(root: Path, plan: dict[str, Any]) -> list[str]:
    """Argv for aifilm_grok final — reuses existing final path (no re-impl)."""
    er = plan.get("engine_route") or {}
    design = str(er.get("design") or "hyperframes")
    post_engine = str(er.get("post_engine") or ("ffmpeg" if design == "none" else design))
    caption_path = str(er.get("caption_path") or "master_hf")
    scripts_dir = Path(__file__).resolve().parents[1]
    aifilm_py = scripts_dir / "aifilm_grok.py"
    argv = [
        sys.executable,
        str(aifilm_py),
        "final",
        "--root",
        str(root),
        "--post-engine",
        post_engine,
        "--music-mood",
        "rnb",
        "--tts-backend",
        "edge",
        "--lipsync",
        "off",
    ]
    if caption_path == "ship_hardburn":
        argv.append("--ship-hardburn")
    elif caption_path == "master_hf":
        argv.extend(["--caption-path", "master_hf"])
    return argv


def build_final_cli_string(root: Path, plan: dict[str, Any]) -> str:
    er = plan.get("engine_route") or {}
    design = str(er.get("design") or "hyperframes")
    post_engine = str(er.get("post_engine") or ("ffmpeg" if design == "none" else design))
    caption_path = str(er.get("caption_path") or "master_hf")
    base = (
        f'aifilm final --root "{root}" --post-engine {post_engine} '
        f"--music-mood rnb --tts-backend edge --lipsync off"
    )
    if caption_path == "ship_hardburn":
        return base + " --ship-hardburn"
    if caption_path == "master_hf":
        return base + " --caption-path master_hf"
    return base


def _run_final_subprocess(argv: list[str], *, timeout_sec: int = 7200) -> dict[str, Any]:
    from security_policy import minimal_subprocess_env

    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
        env=minimal_subprocess_env(),
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
        "stub": False,
    }


def _maybe_caption_verify(root: Path, plan: dict[str, Any]) -> dict[str, Any] | None:
    """After final: named caption gate when master_hf; does not silently burn."""
    er = plan.get("engine_route") or {}
    if str(er.get("caption_path") or "") != "master_hf":
        return None
    final = root / "out" / "film_final.mp4"
    if not final.is_file():
        # common alt names
        for name in ("film_hyperframes.mp4", "final.mp4"):
            alt = root / "out" / name
            if alt.is_file():
                final = alt
                break
    if not final.is_file():
        return {"ok": False, "error": "final mp4 missing after execute", "skipped": True}
    try:
        from final_stages import ensure_captions_after_hf

        return ensure_captions_after_hf(root, final_mp4=final)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def build_run_plan(
    root: Path | str,
    *,
    execute: bool = False,
    apply_first: bool = True,
    final_runner: FinalRunner | None = None,
    timeout_sec: int = 7200,
) -> dict[str, Any]:
    """Compose final stages/flags; optionally apply + shell ``aifilm final``.

    Default dry-run (execute=False): write run receipt only.
    execute=True: apply plan → post_route → invoke existing final CLI (not re-impl).
    Tests may inject ``final_runner``; CI may set AIFILM_EDIT_DIRECTOR_EXECUTE_STUB=1.
    """
    base = Path(root).expanduser().resolve()
    plan = load_plan(base, required=True)
    assert plan is not None
    er = plan.get("engine_route") or {}
    design = str(er.get("design") or "hyperframes")
    post_engine = str(er.get("post_engine") or ("ffmpeg" if design == "none" else design))
    caption_path = str(er.get("caption_path") or "master_hf")
    plate_subs = str(er.get("plate_subs") or ("off" if caption_path == "master_hf" else "burn"))
    plate_cards = str(er.get("plate_cards") or ("blank" if plate_subs == "off" else "text"))

    blocked_by: list[str] = []
    if plan.get("errors"):
        blocked_by.append("edit_plan_errors")
    if plan.get("cut_state") == "assembly":
        blocked_by.append("cut_state_assembly")
    hand = plan.get("audio_handoff") or {}
    warnings: list[str] = []
    if hand.get("prefer_native") and not hand.get("music_director_plan"):
        warnings.append(
            "prefer_native but no music-director plan; run: aifilm music-director draft"
        )
    if hand.get("prefer_native") and hand.get("music_director_plan") and not hand.get(
        "music_director_apply_present"
    ):
        warnings.append(
            "music-director plan present but apply receipt missing; consider music-director apply"
        )

    stages = [
        {
            "id": "plate",
            "engine": "ffmpeg",
            "flags": {
                "subs": plate_subs,
                "plate_cards": plate_cards,
                "post_engine": post_engine,
            },
            "note": "VO/BGM/clips; designed path keeps subs off + blank cards",
        }
    ]
    if design in {"hyperframes", "remotion"} and caption_path == "master_hf":
        stages.append(
            {
                "id": "design",
                "engine": design,
                "flags": {"layout": "underlay", "owner": design},
                "note": "single designed-post owner; no dual final",
            }
        )
        stages.append(
            {
                "id": "caption_verify",
                "engine": "final_stages",
                "flags": {
                    "fallback": (plan.get("recovery") or {}).get("caption_fallback"),
                },
                "note": "pixel/export check; named PIL recovery if needed",
            }
        )
    elif caption_path == "ship_hardburn":
        stages.append(
            {
                "id": "caption_ship",
                "engine": "pil_or_ffmpeg_burn",
                "flags": {"caption_path": "ship_hardburn"},
                "note": "ship path burns Chinese on plate",
            }
        )
    stages.append(
        {
            "id": "deliver",
            "engine": "register",
            "flags": {"post_engine": post_engine},
            "note": "final-stages receipt + gates still own final_complete",
        }
    )

    final_cmd = build_final_cli_string(base, plan)
    final_argv = build_final_argv(base, plan)

    payload: dict[str, Any] = {
        "schema": "aifilm-edit-director-run-v1",
        "kind": "edit-director-run",
        "at": utc_now(),
        "execute": bool(execute),
        "dry_run": not bool(execute),
        "ok": not blocked_by,
        "blocked_by": blocked_by,
        "warnings": warnings,
        "cut_state": plan.get("cut_state"),
        "engine_route": er,
        "join_policy": plan.get("join_policy"),
        "recovery": plan.get("recovery"),
        "stages": stages,
        "final_argv": final_argv,
        "next_cmd": final_cmd if not blocked_by else None,
        "next_steps": (
            [
                "1. aifilm edit-director apply --root …  # refresh editor_cut + post_route",
                f"2. {final_cmd}",
                "3. aifilm gate-auto --root … && aifilm review-final --root …",
            ]
            if not blocked_by
            else [
                "fix edit_plan_errors / assembly clips before run",
                "aifilm edit-director status --root …",
            ]
        ),
    }

    if execute:
        if blocked_by:
            payload["executed"] = False
            payload["ok"] = False
            payload["execute_note"] = "blocked; will not shell final"
        else:
            apply_receipt: dict[str, Any] | None = None
            if apply_first:
                apply_receipt = apply_plan(base)
                payload["apply"] = {
                    "ok": apply_receipt.get("ok"),
                    "path": apply_receipt.get("path"),
                    "editor_cut_ok": apply_receipt.get("editor_cut_ok"),
                    "post_route_ok": apply_receipt.get("post_route_ok"),
                }
                # reload plan after apply
                plan = load_plan(base, required=True) or plan
                final_argv = build_final_argv(base, plan)
                final_cmd = build_final_cli_string(base, plan)
                payload["final_argv"] = final_argv
                payload["next_cmd"] = final_cmd

            stub = str(os.environ.get("AIFILM_EDIT_DIRECTOR_EXECUTE_STUB") or "").strip() in {
                "1",
                "true",
                "yes",
            }
            if final_runner is not None:
                result = final_runner(final_argv)
            elif stub:
                result = {
                    "ok": True,
                    "returncode": 0,
                    "stub": True,
                    "note": "AIFILM_EDIT_DIRECTOR_EXECUTE_STUB=1",
                }
            else:
                result = _run_final_subprocess(final_argv, timeout_sec=timeout_sec)

            payload["final_result"] = result
            payload["executed"] = True
            payload["ok"] = bool(result.get("ok"))
            payload["execute_note"] = (
                "invoked existing aifilm final CLI (orchestrate only)"
                if not result.get("stub")
                else "stub execute (no media render)"
            )
            if result.get("ok"):
                cap = _maybe_caption_verify(base, plan)
                if cap is not None:
                    payload["caption_verify"] = cap
                    if cap.get("ok") is False and not cap.get("skipped"):
                        payload["warnings"] = list(payload.get("warnings") or []) + [
                            "caption_verify failed after final; repair HF captions or ship path"
                        ]
                # advance cut_state toward fine when final produced file
                final_mp4 = base / "out" / "film_final.mp4"
                if final_mp4.is_file() or result.get("stub"):
                    try:
                        p2 = load_plan(base, required=True)
                        if p2 and _CUT_RANK.get(str(p2.get("cut_state")), 0) < _CUT_RANK["fine"]:
                            if not p2.get("errors"):
                                p2["cut_state"] = "fine"
                                p2["source"] = "run-execute"
                                save_plan(base, p2, force=True)
                                payload["cut_state"] = "fine"
                    except EditDirectorError:
                        pass

    rp = run_receipt_path(base)
    rp.parent.mkdir(parents=True, exist_ok=True)
    write_json(rp, payload)
    payload["path"] = str(rp)
    return payload


def snapshot_cut(root: Path | str, name: str) -> dict[str, Any]:
    """Snapshot current plan as a named cut under post/cuts/."""
    base = Path(root).expanduser().resolve()
    plan = load_plan(base, required=True)
    assert plan is not None
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(name).strip())
    if not safe:
        raise EditDirectorError("cut snapshot name required")
    cdir = cuts_dir(base)
    cdir.mkdir(parents=True, exist_ok=True)
    snap_path = cdir / f"{safe}.json"
    snap = {
        "schema": "aifilm-edit-director-cut-snapshot-v1",
        "name": safe,
        "at": utc_now(),
        "plan": plan,
    }
    write_json(snap_path, snap)
    pointer = {
        "schema": "aifilm-edit-director-active-cut-v1",
        "name": safe,
        "path": str(snap_path.relative_to(base)),
        "at": utc_now(),
    }
    write_json(active_cut_path(base), pointer)
    return {"ok": True, "name": safe, "path": str(snap_path), "active": pointer}


def list_cuts(root: Path | str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    cdir = cuts_dir(base)
    names: list[str] = []
    if cdir.is_dir():
        names = sorted(p.stem for p in cdir.glob("*.json") if p.name != "active.json")
    active = read_json(active_cut_path(base)) or {}
    return {
        "ok": True,
        "cuts": names,
        "active": active.get("name"),
        "active_path": active.get("path"),
    }


def activate_cut(root: Path | str, name: str) -> dict[str, Any]:
    """Restore named cut snapshot into live plan (marks post stale if picture-locked)."""
    base = Path(root).expanduser().resolve()
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(name).strip())
    snap_path = cuts_dir(base) / f"{safe}.json"
    data = read_json(snap_path)
    if not isinstance(data, dict) or not isinstance(data.get("plan"), dict):
        raise EditDirectorError(f"cut snapshot missing: {snap_path}")
    plan = normalize_plan(data["plan"], root=base)
    plan["source"] = f"activate:{safe}"
    save_plan(base, plan, force=True)
    pointer = {
        "schema": "aifilm-edit-director-active-cut-v1",
        "name": safe,
        "path": str(snap_path.relative_to(base)),
        "at": utc_now(),
    }
    write_json(active_cut_path(base), pointer)
    stale = False
    pl = read_json(base / "receipts" / "picture-lock.json") or {}
    if pl.get("ok") is True or pl.get("locked") is True:
        stale_path = base / "receipts" / "post-lock-staleness.json"
        write_json(
            stale_path,
            {
                "schema": "aifilm-post-lock-staleness-v1",
                "reason": "edit_director_activate_cut",
                "cut": safe,
                "at": utc_now(),
                "stale": True,
            },
        )
        stale = True
    return {"ok": True, "name": safe, "plan_path": str(PLAN_REL), "post_stale": stale}


def audit_desk(root: Path | str, *, write: bool = True) -> dict[str, Any]:
    """Single checklist: status + optional final-editorial + transition soft."""
    base = Path(root).expanduser().resolve()
    st = status(base)
    issues: list[dict[str, Any]] = []
    for code in st.get("blocked_by") or []:
        if code:
            issues.append({"code": str(code).upper(), "message": f"edit-director blocked: {code}"})
    for err in st.get("errors") or []:
        if isinstance(err, dict):
            issues.append(err)

    editorial: dict[str, Any] | None = None
    final_mp4 = base / "out" / "film_final.mp4"
    if final_mp4.is_file():
        try:
            from final_editorial_review import audit as editorial_audit

            editorial = editorial_audit(base, write=False)
            for item in editorial.get("issues") or []:
                if isinstance(item, dict):
                    issues.append(item)
        except Exception as exc:  # noqa: BLE001
            editorial = {"ok": False, "error": str(exc)[:160]}
            issues.append({"code": "EDITORIAL_AUDIT_ERROR", "message": str(exc)[:160]})

    transition: dict[str, Any] | None = None
    try:
        from transition_frame_audit import build_transition_frame_audit

        transition = build_transition_frame_audit(base)
    except Exception as exc:  # noqa: BLE001
        transition = {"ok": None, "error": str(exc)[:120]}

    if isinstance(transition, dict) and transition.get("ok") is False:
        for item in transition.get("issues") or transition.get("errors") or []:
            if isinstance(item, dict):
                issues.append(item)
            else:
                issues.append({"code": "TRANSITION_AUDIT", "message": str(item)[:160]})

    report = {
        "schema": "aifilm-edit-director-audit-v1",
        "kind": "edit-director-audit",
        "at": utc_now(),
        "ok": len(issues) == 0 and bool(st.get("ok")),
        "status": st,
        "editorial": editorial,
        "transition": transition,
        "issues": issues,
        "partial": bool(issues) and final_mp4.is_file(),
    }
    if write:
        path = audit_receipt_path(base)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, report)
        report["path"] = str(path)
    return report


def status(root: Path | str) -> dict[str, Any]:
    """Machine-readable progress for dispatch / agents."""
    base = Path(root).expanduser().resolve()
    plan = load_plan(base, required=False)
    if plan is None:
        return {
            "ok": False,
            "blocked_by": ["no_edit_director_plan"],
            "next_cmd": f'aifilm edit-director draft --root "{base}"',
            "plan_path": str(plan_path(base)),
        }
    errors = plan.get("errors") or []
    cut = str(plan.get("cut_state") or "assembly")
    er = plan.get("engine_route") or {}
    hand = plan.get("audio_handoff") or {}
    blocked: list[str] = []
    if errors:
        blocked.append("edit_plan_errors")
    if cut == "assembly":
        blocked.append("cut_state_assembly")
    apply_rec = read_json(apply_receipt_path(base)) or {}
    run_rec = read_json(run_receipt_path(base)) or {}
    post_route = read_json(base / "receipts" / "post-route.json") or {}
    route_mismatch = False
    if post_route.get("caption_path") and er.get("caption_path"):
        if str(post_route.get("caption_path")) != str(er.get("caption_path")):
            route_mismatch = True
            blocked.append("post_route_mismatch")

    active = read_json(active_cut_path(base)) or {}
    next_cmd: str
    if not apply_rec:
        next_cmd = f'aifilm edit-director apply --root "{base}"'
    elif blocked:
        next_cmd = f'aifilm edit-director status --root "{base}"'
    else:
        next_cmd = f'aifilm edit-director run --root "{base}"'

    return {
        "ok": not blocked,
        "blocked_by": blocked or None,
        "cut_state": cut,
        "shot_count": len(plan.get("shot_ids") or []),
        "stats": plan.get("stats"),
        "errors": errors,
        "engine_route": er,
        "audio_handoff": hand,
        "apply_present": bool(apply_rec),
        "apply_ok": apply_rec.get("ok") if apply_rec else None,
        "last_run_dry": run_rec.get("dry_run") if run_rec else None,
        "last_executed": run_rec.get("executed") if run_rec else None,
        "post_route_caption": post_route.get("caption_path"),
        "post_route_mismatch": route_mismatch,
        "active_cut": active.get("name"),
        "final_cmd": build_final_cli_string(base, plan) if not blocked else None,
        "plan_path": str(PLAN_REL),
        "next_cmd": next_cmd,
    }
