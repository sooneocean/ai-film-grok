#!/usr/bin/env python3
"""Eight-ring craft spine: idea → … → verified.

Orthogonal to tool-layer pipeline stages (agent/visual/voice/…).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spine.stage_model import CRAFT_EIGHT
from util import read_json
from util.spine_helpers import pilot_user_ok, present

# Single source: stage_model.CRAFT_EIGHT (C3 — do not re-list rings here).
CRAFT_STAGES: tuple[str, ...] = CRAFT_EIGHT

CRAFT_LABELS_ZH: dict[str, str] = {
    "idea": "1·Idea 命题",
    "story": "2·Story 故事",
    "beats": "3·Beats 叙事节点",
    "shots": "4·Shots 镜头包",
    "media": "5·Media 生成素材",
    "selects": "6·Selects 选片",
    "rough": "7·Rough Cut 初剪",
    "verified": "8·Verified 验证成片",
}

CRAFT_QUESTIONS: dict[str, str] = {
    "idea": "为何存在、给谁、多长、情绪落点？",
    "story": "谁要什么、状态怎么变？",
    "beats": "观众每步多懂什么、情绪怎么变？",
    "shots": "用哪些镜证明 Beat？Coverage 够吗？",
    "media": "哪条模型路径拿真素材？",
    "selects": "这段能否进时间线？",
    "rough": "顺序与节奏是否成立？",
    "verified": "能否声称可发布？",
}


def _director_intent_ok(spec: dict[str, Any]) -> bool:
    di = spec.get("director_intent")
    if not isinstance(di, dict):
        # fallback: logline/theme at top level or non-empty description
        logline = str(spec.get("logline") or "").strip()
        theme = str(spec.get("theme") or "").strip()
        desc = str(spec.get("description") or "").strip()
        return bool(logline or theme or len(desc) >= 20)
    logline = str(di.get("logline") or "").strip()
    theme = str(di.get("theme") or "").strip()
    return bool(logline or theme or str(di.get("premise") or "").strip())


def _beats_ok(spec: dict[str, Any]) -> bool:
    shots = spec.get("shots") if isinstance(spec.get("shots"), list) else []
    if not shots:
        return False
    funcs = 0
    for s in shots:
        if not isinstance(s, dict):
            continue
        if s.get("dramatic_function") or (s.get("dsl") or {}).get("story_beat"):
            funcs += 1
    return funcs >= max(1, len(shots) // 3)


def _spec_valid_flag(root: Path, gates: dict[str, Any] | None) -> bool:
    if gates and gates.get("spec"):
        return True
    # soft: film-spec exists and has shots
    spec = read_json(root / "film-spec.json") or {}
    shots = spec.get("shots") if isinstance(spec.get("shots"), list) else []
    return bool(shots)


def detect_craft_stage(
    root: Path,
    *,
    gates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Infer craft_stage from film-root artifacts."""
    root = Path(root).expanduser().resolve()
    gates = gates or {}
    book = read_json(root / "production-book.json") or {}
    if book.get("rigor") == "professional":
        from workflow_spine import STAGE_ORDER, build_workflow_status

        workflow = build_workflow_status(root, gates=gates)
        stage = str(workflow["craft_projection"])
        current = str(workflow["current_stage"])
        completed = set(workflow["completed"])
        craft_completion = {
            "idea": {"concept_lock"},
            "story": {"script_lock"},
            "beats": {"department_look_lock"},
            "shots": {"shot_animatic_lock", "pilot_approval"},
            "media": {"bulk"},
            "selects": {"dailies_review"},
            "rough": {"selects_rough_cut", "picture_lock", "post_locks"},
            "verified": {"master_lock"},
        }
        checklist = {
            ring: required.issubset(completed) for ring, required in craft_completion.items()
        }
        idx = CRAFT_STAGES.index(stage)
        return {
            "craft_stage": stage,
            "stage": stage,
            "stage_index": idx + 1,
            "stage_total": len(CRAFT_STAGES),
            "label_zh": CRAFT_LABELS_ZH[stage],
            "question": CRAFT_QUESTIONS[stage],
            "detail": "complete" if current == "complete" else current,
            "blockers": [] if current == "complete" else [f"stage_lock:{current}"],
            "checklist": checklist,
            "flags": {
                "professional": True,
                "director_stage": current,
                "ready_for_lock": workflow["ready_for_lock"],
            },
            "professional_stage_order": list(STAGE_ORDER),
            "spine": " → ".join(CRAFT_STAGES),
            "ref": "references/craft-spine.md",
            "rings": list(CRAFT_STAGES),
        }
    receipts = root / "receipts"
    spec = read_json(root / "film-spec.json") or {}
    man = read_json(root / "manifest.json") or {}
    outputs = man.get("outputs") if isinstance(man.get("outputs"), dict) else {}
    final_rec = outputs.get("final_film") if isinstance(outputs.get("final_film"), dict) else {}
    silent_rec = outputs.get("silent_film") if isinstance(outputs.get("silent_film"), dict) else {}

    has_brief = present(root / "brief.json") or present(receipts / "creative-brief.md")
    has_init = (
        has_brief
        or bool(gates.get("brief"))
        or root.is_dir()
        and ((root / "film-spec.json").is_file() or (root / "README.md").is_file())
    )
    story_ok = _director_intent_ok(spec) if spec else False
    if not story_ok and present(receipts / "directors-lens.md"):
        story_ok = True
    beats_ok = _beats_ok(spec) if spec else False
    if present(receipts / "beat-sheet.md"):
        beats_ok = True
    style_ok = bool(gates.get("style_locked"))
    if not style_ok:
        style = read_json(root / "style-bible.json") or {}
        style_ok = bool(style.get("locked"))
    spec_ok = _spec_valid_flag(root, gates)
    pilot_ok = pilot_user_ok(root)
    clips_ok = bool(gates.get("clips_complete"))
    if not clips_ok and isinstance(man.get("clips"), dict):
        approved = sum(
            1
            for c in man["clips"].values()
            if isinstance(c, dict) and c.get("status") == "approved"
        )
        planned = len(spec.get("shots") or []) if isinstance(spec.get("shots"), list) else 0
        clips_ok = planned > 0 and approved >= planned
    approved_n = 0
    if isinstance(man.get("clips"), dict):
        approved_n = sum(
            1
            for c in man["clips"].values()
            if isinstance(c, dict) and c.get("status") == "approved"
        )
    has_media_work = approved_n > 0 or present(receipts / "media-queue.json")
    rough_ok = present(receipts / "rough-cut.json") or bool(
        silent_rec and (silent_rec.get("path") or silent_rec.get("sha256"))
    )
    # plate without review still rough
    if final_rec and not gates.get("final_complete"):
        # technical final exists → at least past rough into verify pending
        pass
    final_complete = bool(gates.get("final_complete"))
    export_ok = bool(gates.get("desktop_exported"))
    final_review = (
        outputs.get("final_review") if isinstance(outputs.get("final_review"), dict) else {}
    )
    human_verified = bool(final_review.get("approved") is True) and final_complete

    flags = {
        "brief": has_brief or has_init,
        "story": story_ok,
        "beats": beats_ok,
        "style_locked": style_ok,
        "spec": spec_ok,
        "pilot_user_approved": pilot_ok,
        "has_media_work": has_media_work,
        "clips_complete": clips_ok,
        "approved_clips": approved_n,
        "rough": rough_ok or bool(final_rec),
        "final_film": bool(final_rec),
        "final_complete": final_complete,
        "human_review": bool(final_review.get("approved")),
        "desktop_exported": export_ok,
    }

    blockers: list[str] = []
    stage = "idea"
    detail = "brief"

    if not has_init and not has_brief:
        stage, detail = "idea", "init"
        blockers.append("project_missing")
    elif not story_ok and not spec_ok:
        # allow style-first paths: if only init, stay idea/story
        if not has_brief and not (root / "brief.json").is_file():
            stage, detail = "idea", "creative-brief"
            blockers.append("brief_thin")
        else:
            stage, detail = "story", "director_intent"
            blockers.append("story_incomplete")
    elif not style_ok and not pilot_ok and not clips_ok:
        # bible before bulk shots lock
        if not spec_ok:
            if not beats_ok:
                stage, detail = "beats", "beat_spine"
                blockers.append("beats_thin")
            else:
                stage, detail = "shots", "write-spec"
                blockers.append("spec_or_style")
        else:
            stage, detail = "shots", "lock-style-or-pilot"
            blockers.append("style_not_locked")
    elif not spec_ok:
        stage, detail = "shots", "write-spec"
        blockers.append("spec_invalid")
    elif not pilot_ok and not clips_ok:
        stage, detail = "shots", "pilot"
        blockers.append("pilot_not_user_approved")
    elif not clips_ok:
        stage, detail = "media" if has_media_work or pilot_ok else "media", "bulk-or-register"
        blockers.append("clips_incomplete")
        # if some approved but not all → still media; if all planned registered would be clips_ok
        if has_media_work and approved_n > 0:
            stage, detail = "media", "continue-media"
    elif clips_ok and not rough_ok and not final_rec:
        stage, detail = "selects", "register-complete"
        # selects complete when clips_ok — move to rough
        stage, detail = "rough", "assemble-or-preview"
        blockers.append("rough_cut_pending")
    elif final_complete and export_ok and human_verified:
        stage, detail = "verified", "complete"
    elif final_complete and export_ok:
        stage, detail = "verified", "export-done-review-check"
        if not human_verified:
            blockers.append("human_review_missing")
    elif final_complete and not export_ok:
        stage, detail = "verified", "export-desktop"
        blockers.append("desktop_not_exported")
    elif final_rec and not final_complete:
        stage, detail = "verified", "review-final"
        blockers.append("final_not_approved")
    elif clips_ok and (True):
        # clips complete → rough then voice/design then verified
        if not final_rec:
            stage, detail = "rough", "final-or-preview"
            blockers.append("no_final_yet")
        else:
            stage, detail = "verified", "review-final"
            blockers.append("final_not_approved")
    else:
        stage, detail = "media", "unknown"
        blockers.append("unclassified")

    # Refine: clips complete means selects done
    if clips_ok and stage == "selects":
        stage, detail = "rough", "assemble"

    # Wave 5: surface adult-max heat as craft blocker (scale before bulk/final)
    heat: dict[str, Any] | None = None
    try:
        from heat_check import heat_agent_status

        hs = heat_agent_status(root)
        if hs.get("active"):
            heat = {
                "active": True,
                "hard_fail": bool(hs.get("hard_fail")),
                "needs_boost": bool(hs.get("needs_boost")),
                "score": hs.get("score"),
                "grade": hs.get("grade"),
                "ecchi_score": hs.get("ecchi_score"),
                "next_cmd": hs.get("next_cmd"),
                "why": hs.get("why"),
            }
            if hs.get("hard_fail"):
                # Any stage with adult-max hard_fail must surface — not only media
                blockers.append("heat_agent_hard_fail")
                if stage in {"shots", "media", "selects", "rough", "verified"}:
                    detail = "heat-boost-before-bulk"
            elif hs.get("needs_boost") and stage in {"beats", "shots", "media"}:
                blockers.append("heat_needs_boost")
    except Exception:  # noqa: BLE001
        heat = None

    checklist = {
        "idea": bool(has_init or has_brief),
        "story": story_ok or spec_ok,
        "beats": beats_ok or spec_ok,
        "shots": bool(spec_ok and (pilot_ok or clips_ok)),
        "media": clips_ok or has_media_work,
        "selects": clips_ok,
        "rough": rough_ok or bool(final_rec) or final_complete,
        "verified": bool(final_complete and (human_verified or export_ok)),
    }

    idx = CRAFT_STAGES.index(stage) if stage in CRAFT_STAGES else 0
    return {
        "craft_stage": stage,
        "stage": stage,
        "stage_index": idx + 1,
        "stage_total": len(CRAFT_STAGES),
        "label_zh": CRAFT_LABELS_ZH.get(stage, stage),
        "question": CRAFT_QUESTIONS.get(stage, ""),
        "detail": detail,
        "blockers": blockers,
        "checklist": checklist,
        "flags": flags,
        "heat": heat,
        "spine": " → ".join(CRAFT_STAGES),
        "ref": "references/craft-spine.md",
        "rings": list(CRAFT_STAGES),
    }


def format_craft_line(craft: dict[str, Any], *, compact: bool = True) -> str:
    idx = craft.get("stage_index", "?")
    total = craft.get("stage_total", 8)
    label = craft.get("label_zh") or craft.get("craft_stage")
    if compact:
        return f"craft {idx}/{total} · {label}"
    q = craft.get("question") or ""
    return f"craft {idx}/{total} · {label} — {q}"


def craft_status_report(
    root: Path,
    *,
    gates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    craft = detect_craft_stage(root, gates=gates)
    root = Path(root).expanduser().resolve()
    next_hint = {
        "idea": "写 receipts/creative-brief.md 或确认 brief；aifilm init",
        "story": "Director’s Lens → director_intent.logline/theme",
        "beats": "补 dramatic_function / visible_change；可选 beat-sheet.md",
        "shots": "aifilm write-spec · pilot pick/score/approve",
        "media": "aifilm capability --root … · media-queue · register-clip",
        "selects": "aifilm selects report · 补 register approved",
        "rough": "assemble / compose-preview / Editor’s Cut；写 rough-cut 可选",
        "verified": "final · review-final 十一维 · export-desktop",
    }
    stage = craft.get("craft_stage") or "idea"
    hint = next_hint.get(str(stage), "aifilm next --root …")
    heat = craft.get("heat") if isinstance(craft.get("heat"), dict) else None
    if heat and (heat.get("hard_fail") or heat.get("needs_boost")) and heat.get("next_cmd"):
        hint = f"{heat['next_cmd']}  # adult max scale first — then {hint}"
    return {
        "ok": True,
        "root": str(root),
        "craft": craft,
        "line": format_craft_line(craft, compact=True),
        "line_full": format_craft_line(craft, compact=False),
        "next_hint": hint,
        "heat": heat,
        "usage": {
            "capability": "aifilm capability --root <film>",
            "audio_plan": "aifilm audio-plan --root <film>",
            "selects": "aifilm selects report --root <film>",
            "next": "aifilm next --root <film>",
        },
    }
