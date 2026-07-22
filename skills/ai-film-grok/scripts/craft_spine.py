#!/usr/bin/env python3
"""Eight-ring craft spine: idea → … → verified.

Orthogonal to tool-layer pipeline stages (agent/visual/voice/…).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json

CRAFT_STAGES: tuple[str, ...] = (
    "idea",
    "story",
    "beats",
    "shots",
    "media",
    "selects",
    "rough",
    "verified",
)

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


def _present(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 2


def _pilot_user_ok(root: Path) -> bool:
    try:
        from production_gates import load_pilot_approval, pilot_is_user_approved

        return pilot_is_user_approved(load_pilot_approval(root))
    except Exception:
        pilot = read_json(root / "receipts" / "pilot-approval.json") or {}
        return bool(
            str(pilot.get("approved_by") or "").lower() == "user"
            and str(pilot.get("user_phrase") or "").strip()
        )


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
    receipts = root / "receipts"
    spec = read_json(root / "film-spec.json") or {}
    man = read_json(root / "manifest.json") or {}
    outputs = man.get("outputs") if isinstance(man.get("outputs"), dict) else {}
    final_rec = outputs.get("final_film") if isinstance(outputs.get("final_film"), dict) else {}
    silent_rec = outputs.get("silent_film") if isinstance(outputs.get("silent_film"), dict) else {}

    has_brief = _present(root / "brief.json") or _present(receipts / "creative-brief.md")
    has_init = (
        has_brief
        or bool(gates.get("brief"))
        or root.is_dir()
        and ((root / "film-spec.json").is_file() or (root / "README.md").is_file())
    )
    story_ok = _director_intent_ok(spec) if spec else False
    if not story_ok and _present(receipts / "directors-lens.md"):
        story_ok = True
    beats_ok = _beats_ok(spec) if spec else False
    if _present(receipts / "beat-sheet.md"):
        beats_ok = True
    style_ok = bool(gates.get("style_locked"))
    if not style_ok:
        style = read_json(root / "style-bible.json") or {}
        style_ok = bool(style.get("locked"))
    spec_ok = _spec_valid_flag(root, gates)
    pilot_ok = _pilot_user_ok(root)
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
    has_media_work = approved_n > 0 or _present(receipts / "media-queue.json")
    rough_ok = _present(receipts / "rough-cut.json") or bool(
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
        "verified": "final · review-final 七维 · export-desktop",
    }
    stage = craft.get("craft_stage") or "idea"
    return {
        "ok": True,
        "root": str(root),
        "craft": craft,
        "line": format_craft_line(craft, compact=True),
        "line_full": format_craft_line(craft, compact=False),
        "next_hint": next_hint.get(str(stage), "aifilm next --root …"),
        "usage": {
            "capability": "aifilm capability --root <film>",
            "audio_plan": "aifilm audio-plan --root <film>",
            "selects": "aifilm selects report --root <film>",
            "next": "aifilm next --root <film>",
        },
    }
