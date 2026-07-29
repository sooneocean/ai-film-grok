#!/usr/bin/env python3
"""State-index / keyframe continuity gate (check + regenerate plan).

Purpose (user 2026-07-21):
  Treat state photos + keyframes as a **checkpoint**, not only docs.
  If gaps exist, agent may regenerate at this stage so I2V / joins stay fluid
  (wardrobe no re-dress, promote last→first, smoother transitions).

CLI: aifilm state-index check|plan
Also hooked from preflight / dispatch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from util import read_json, utc_now

WARDROBE_RANK: dict[str, int] = {
    "full": 0,
    "armored": 1,
    "partial": 2,
    "undressed": 3,
    "bare": 4,
    "default": 0,
}

UNDRESS_STATES = frozenset({"partial", "undressed", "bare"})


def _shots_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        import copy

        from film_spec import validate_film_spec

        out = list(validate_film_spec(copy.deepcopy(spec), assign_missing_ids=False))
    except Exception:
        for scene in spec.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            for sh in scene.get("shots") or []:
                if isinstance(sh, dict):
                    out.append(sh)
    return out


def _wardrobe_of(shot: dict[str, Any]) -> str:
    w = shot.get("wardrobe_state") or (shot.get("dsl") or {}).get("wardrobe_state") or "full"
    return str(w).strip().lower() or "full"


def _wardrobe_state_id(shot: dict[str, Any]) -> str | None:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    value = shot.get("wardrobe_state_id") or dsl.get("wardrobe_state_id")
    return str(value).strip() if value else None


def _chain_mode(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return str(dsl.get("chain_mode") or "continue").strip().lower()


def _hero_ids(shot: dict[str, Any]) -> list[str]:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cast = dsl.get("cast") if isinstance(dsl.get("cast"), list) else []
    if cast:
        return [str(c) for c in cast if c]
    hids = shot.get("heroine_ids")
    if isinstance(hids, list) and hids:
        return [str(x) for x in hids if x]
    return ["hero"]


def _path_exists(root: Path, p: str | None) -> bool:
    if not p:
        return False
    path = Path(p)
    if not path.is_absolute():
        path = root / path
    return path.is_file()


def _find_keyframe(root: Path, shot_id: str) -> Path | None:
    # Prefer full-res geometry-ok still (lesson 2026-07-22 no-compress)
    try:
        from media_qa import pick_best_keyframe

        best = pick_best_keyframe(root, shot_id)
        if best is not None and best.is_file():
            return best
    except Exception:
        pass
    kf = root / "keyframes"
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = kf / f"{shot_id}{ext}"
        if p.is_file():
            return p
    return None


def _approved_clip(man: dict[str, Any], shot_id: str) -> dict[str, Any] | None:
    clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
    rec = clips.get(shot_id)
    if isinstance(rec, dict) and rec.get("status") == "approved":
        return rec
    return None


def run_state_index_check(root: Path) -> dict[str, Any]:
    """Return checkpoint report: ok / issues / generate_plan / fluency."""
    root = Path(root).expanduser().resolve()
    hard: list[dict[str, Any]] = []
    soft: list[dict[str, Any]] = []
    gen_plan: list[dict[str, Any]] = []

    spec = read_json(root / "film-spec.json") or {}
    bible = read_json(root / "style-bible.json") or {}
    man = read_json(root / "manifest.json") or {}
    heat = str(spec.get("heat_scale") or "").strip().lower()
    heat_maxish = heat in {"max", "hot"}

    shots = _shots_from_spec(spec) if spec else []
    shot_rows: list[dict[str, Any]] = []
    states_needed: set[str] = set()
    states_needed_by_hero: dict[str, set[str]] = {}
    exact_state_ids: dict[str, set[str]] = {}
    heroes: set[str] = set()

    for sh in shots:
        sid = str(sh.get("id") or "")
        w = _wardrobe_of(sh)
        states_needed.add(w)
        hids = _hero_ids(sh)
        for h in hids:
            heroes.add(h)
            states_needed_by_hero.setdefault(h, set()).add(w)
            if _wardrobe_state_id(sh):
                exact_state_ids.setdefault(h, set()).add(str(_wardrobe_state_id(sh)))
        kf = _find_keyframe(root, sid) if sid else None
        clip = _approved_clip(man, sid) if sid else None
        shot_rows.append(
            {
                "id": sid,
                "wardrobe_state": w,
                "wardrobe_state_id": _wardrobe_state_id(sh),
                "chain_mode": _chain_mode(sh),
                "hero_ids": hids,
                "keyframe": str(kf) if kf else None,
                "keyframe_ok": bool(kf),
                "clip_approved": bool(clip),
            }
        )

    # --- resolve state photos ---
    try:
        from visual_bible import migrate_to_v2, resolve_state_photo

        bible = migrate_to_v2(bible)
    except Exception:
        resolve_state_photo = None  # type: ignore

    csm = (
        bible.get("cast_state_masters") if isinstance(bible.get("cast_state_masters"), dict) else {}
    )
    missing_states: list[str] = []
    state_index: dict[str, Any] = {}

    # A gradual wardrobe story must own an explicit garment-by-garment ladder.
    # This is intentionally independent of heat_scale: it prevents a normal
    # dramatic costume change from silently falling back to the full cast image.
    ladder_hard: list[dict[str, Any]] = []
    ladder_plan: list[dict[str, Any]] = []
    ladder_active_heroes: set[str] = set()
    try:
        from wardrobe_ladder import (
            ladder_plan as build_ladder_plan,
        )
        from wardrobe_ladder import (
            needs_ladder,
            state_for_id,
        )

        if needs_ladder(states_needed):
            for hid in sorted(heroes) or ["hero"]:
                if not needs_ladder(states_needed_by_hero.get(hid, set())):
                    continue
                # A non-full character always repairs through the ladder.
                # If no ladder exists, ladder_plan emits the hard actionable
                # breakdown gap; never revive the legacy full-image edit task.
                ladder_active_heroes.add(hid)
                issues, steps = build_ladder_plan(bible, hid, root=root)
                for issue in issues:
                    ladder_hard.append(
                        {
                            "level": "hard",
                            "code": str(issue.get("code") or "WARDROBE_LADDER_INVALID"),
                            "message": f"wardrobe ladder invalid for {hid}: {issue.get('code')}",
                            "fix": "fill wardrobe_ladders garment list, approve full state, then complete serial state I2I",
                        }
                    )
                ladder_plan.extend(steps)
                for shot in shots:
                    if not isinstance(shot, dict) or hid not in _hero_ids(shot):
                        continue
                    if _wardrobe_of(shot) not in {
                        "full",
                        "default",
                        "armored",
                    } and not _wardrobe_state_id(shot):
                        ladder_hard.append(
                            {
                                "level": "hard",
                                "code": "WARDROBE_STATE_ID_REQUIRED",
                                "message": f"state-ladder character {hid} has a non-full shot without wardrobe_state_id",
                                "fix": "bind each non-full shot to one approved wardrobe_ladder state ID",
                            }
                        )
                for state_id in sorted(exact_state_ids.get(hid) or []):
                    state = state_for_id(bible, hid, state_id)
                    if not state or state.get("status") != "approved":
                        ladder_hard.append(
                            {
                                "level": "hard",
                                "code": "EXACT_WARDROBE_STATE_UNAVAILABLE",
                                "message": f"shot requests unapproved exact wardrobe state {hid}:{state_id}",
                                "fix": "complete and approve the requested wardrobe_ladder state before I2I/I2V",
                            }
                        )
                for shot in shots:
                    if not isinstance(shot, dict) or hid not in _hero_ids(shot):
                        continue
                    state_id = _wardrobe_state_id(shot)
                    if not state_id:
                        continue
                    state = state_for_id(bible, hid, state_id)
                    if state and str(state.get("wardrobe_state") or "").lower() != _wardrobe_of(
                        shot
                    ):
                        ladder_hard.append(
                            {
                                "level": "hard",
                                "code": "WARDROBE_STATE_ID_MISMATCH",
                                "message": f"shot wardrobe_state={_wardrobe_of(shot)} does not match {hid}:{state_id}",
                                "fix": "use the exact approved wardrobe_ladder state with the same wardrobe_state",
                            }
                        )
    except ImportError:
        pass
    hard.extend(ladder_hard)
    gen_plan.extend(ladder_plan)

    for hid in sorted(heroes) or ["hero"]:
        state_index[hid] = {}
        for st in sorted(
            states_needed_by_hero.get(hid, {"full"}), key=lambda s: WARDROBE_RANK.get(s, 0)
        ):
            path = None
            if resolve_state_photo is not None:
                path = resolve_state_photo(bible, hid, st, root=root)
            elif isinstance(csm.get(hid), dict):
                path = (csm.get(hid) or {}).get(st)
            exists = _path_exists(root, path) if path else False
            state_index[hid][st] = {"path": path, "exists": exists}
            # full may use cast master; missing file for non-full is a gap when heat maxish
            # The ladder is the only allowed repair plan for an active
            # gradual-undress character.  A legacy broad-state task would
            # invite re-editing from the full look and breaking lineage.
            if st in UNDRESS_STATES and not exists and hid not in ladder_active_heroes:
                missing_states.append(f"{hid}:{st}")
                gen_plan.append(
                    {
                        "action": "generate_state_photo",
                        "hero_id": hid,
                        "wardrobe_state": st,
                        "out": f"canonical/cast-states/{hid}/{st}.png",
                        "why": "missing state photo for wardrobe used in film-spec",
                        "agent_hint": (
                            f"image_edit from cast or lower-rank state → save "
                            f"canonical/cast-states/{hid}/{st}.png; "
                            f"write style-bible cast_state_masters.{hid}.{st}"
                        ),
                    }
                )

    # Dialogue-first scenes need a reviewed performance-state photo before a
    # talking close-up is generated.  Wardrobe state alone cannot preserve the
    # emotional expression, gaze, prop hand and body orientation that make a
    # dialogue cut look like the same performance.
    dialogue_state_index: dict[str, Any] = {}
    missing_dialogue_states: list[str] = []
    dialogue_mode = str(spec.get("vo_mode") or "").strip().lower() == "dialogue_drama"
    dialogue_i2i_route: dict[str, Any] | None = None
    if dialogue_mode:
        from performance_state import validate_performance_state

        try:
            from dialogue_i2i_route import route_dialogue_i2i

            dialogue_i2i_route = route_dialogue_i2i(
                frw_receipt=read_json(root / "receipts" / "frw-key-capability.json"),
            )
        except Exception:  # fail closed even when a plugin installation is partial
            dialogue_i2i_route = {
                "status": "local_preflight_required",
                "selected_provider": None,
                "reason": "dialogue i2i route unavailable; do not submit until capability preflight",
            }
        for shot in shots:
            if not isinstance(shot, dict) or shot.get("screen_mode") != "on_camera":
                continue
            sid = str(shot.get("id") or "")
            hero_id = str(shot.get("speaker") or "hero")
            state_id = str(shot.get("performance_state_id") or "").strip()
            if not state_id:
                missing_dialogue_states.append(f"{sid}:missing-performance-state-id")
                continue
            path = root / "canonical" / "performance-states" / hero_id / f"{state_id}.png"
            approval = validate_performance_state(
                root,
                speaker=hero_id,
                state_id=state_id,
            )
            exists = bool(approval.get("ok"))
            dialogue_state_index[sid] = {
                "hero_id": hero_id,
                "performance_state_id": state_id,
                "path": str(path),
                "exists": exists,
                "approval": approval,
            }
            if not exists:
                missing_dialogue_states.append(f"{sid}:{state_id}")
                gen_plan.append(
                    {
                        "action": "generate_dialogue_state_photo",
                        "shot_id": sid,
                        "hero_id": hero_id,
                        "performance_state_id": state_id,
                        "out": str(path.relative_to(root)),
                        "why": "talking close-up requires a state-locked i2i performance reference",
                        "i2i_route": dialogue_i2i_route,
                        "input_candidates": [
                            f"canonical/cast-states/{hero_id}/{_wardrobe_of(shot)}.png",
                            f"assets/characters/{hero_id}-canonical.png",
                        ],
                        "generation_receipt_out": (
                            f"receipts/generation/performance-states/{hero_id}/{state_id}.json"
                        ),
                        "generation_receipt_contract": {
                            "operation": "image_edit",
                            "required": ["input_sha256", "output_sha256", "model"],
                            "output_sha256_must_match": str(path.relative_to(root)),
                        },
                        "approval_receipt_out": (
                            f"receipts/performance-states/{hero_id}/{state_id}.json"
                        ),
                        "approval_command": (
                            "aifilm approve-performance-state --speaker "
                            f"{hero_id} --state-id {state_id} --image {path.relative_to(root)} "
                            "--generation-receipt <generation_receipt_out> "
                            "--reviewer <reviewer> --review-note <note>"
                        ),
                        "agent_hint": (
                            "Follow i2i_route: FRW only when exact img2image capability is proven; "
                            "otherwise run local capacity preflight and wait if occupied. From the "
                            "matching wardrobe state preserve face/outfit, then set emotion, gaze, "
                            "hand/prop and camera-facing pose before lipsync. Save the provider's "
                            "real image_edit receipt before human approval; never backfill lineage "
                            "for an old still."
                        ),
                    }
                )
    if missing_dialogue_states:
        issue = {
            "level": "hard" if spec.get("dialogue_state_strict") is not False else "soft",
            "code": "MISSING_DIALOGUE_PERFORMANCE_STATE",
            "message": "talking shots missing i2i performance state photos: "
            + ", ".join(missing_dialogue_states[:12]),
            "fix": "generate canonical/performance-states/<speaker>/<state>.png before talking I2V",
        }
        (hard if issue["level"] == "hard" else soft).append(issue)

    # undress-anchor when any undressed/bare shot
    needs_anchor = any(_wardrobe_of(s) in {"undressed", "bare"} for s in shots)
    anchor = root / "canonical" / "wardrobe" / "undress-anchor.png"
    if not anchor.is_file():
        for alt in ("undress-anchor.jpg", "undress-anchor.webp"):
            a2 = root / "canonical" / "wardrobe" / alt
            if a2.is_file():
                anchor = a2
                break
    anchor_ok = anchor.is_file()
    if needs_anchor and not anchor_ok and heat_maxish:
        # P0 · 2026-07-29: undress-anchor hard on max/hot (was soft)
        hard.append(
            {
                "level": "hard",
                "code": "MISSING_UNDRESS_ANCHOR",
                "message": "undressed/bare shots present but no canonical/wardrobe/undress-anchor.*",
                "fix": "cp peak undress keyframe → canonical/wardrobe/undress-anchor.png",
            }
        )
        gen_plan.append(
            {
                "action": "set_undress_anchor",
                "out": "canonical/wardrobe/undress-anchor.png",
                "why": "peak undress pixel truth for no-redress + fluid joins",
                "agent_hint": "After undress-peak still approved: cp keyframes/<peak>.png canonical/wardrobe/undress-anchor.png",
            }
        )

    if missing_states and needs_ladder(states_needed):
        hard.append(
            {
                "level": "hard",
                "code": "MISSING_REQUIRED_STATE_PHOTOS",
                "message": "story uses non-full wardrobe states but canonical state photos are missing: "
                + ", ".join(missing_states[:12]),
                "fix": "complete the wardrobe_ladder serial I2I plan before still/I2V generation",
            }
        )
    elif missing_states and heat_maxish:
        # bare/undressed state photos hard on max; partial stays soft
        meat_missing = [
            m for m in missing_states if m.endswith(":bare") or m.endswith(":undressed")
        ]
        if meat_missing:
            hard.append(
                {
                    "level": "hard",
                    "code": "MISSING_MEAT_STATE_PHOTOS",
                    "message": (
                        "missing undressed/bare state photos for max film: "
                        + ", ".join(meat_missing[:12])
                    ),
                    "fix": (
                        "generate cast-states undressed+bare before bulk I2V; "
                        "aifilm state-index plan --root …"
                    ),
                }
            )
        other_missing = [m for m in missing_states if m not in meat_missing]
        if other_missing:
            soft.append(
                {
                    "level": "soft",
                    "code": "MISSING_STATE_PHOTOS",
                    "message": f"missing state photos for used wardrobe: {', '.join(other_missing[:12])}",
                    "fix": "aifilm state-index plan --root … then generate cast-states; or fill cast_state_masters",
                }
            )
    elif missing_states:
        soft.append(
            {
                "level": "soft",
                "code": "MISSING_STATE_PHOTOS",
                "message": f"optional state photos missing: {', '.join(missing_states[:8])}",
                "fix": "recommended for keyframe-first fluency",
            }
        )

    # max: flag missing detail/union insert coverage (write-spec also hard-fails SEX_DETAIL_CU)
    if heat == "max":
        detail_ids: list[str] = []
        for s in shots:
            if not isinstance(s, dict):
                continue
            cr = str(
                s.get("coverage_role") or (s.get("dsl") or {}).get("coverage_role") or ""
            ).lower()
            size = str(
                s.get("shot_size")
                or s.get("shotSize")
                or ((s.get("dsl") or {}).get("camera") or {}).get("shot_size")
                or ""
            ).lower()
            framing = str(s.get("framing") or (s.get("dsl") or {}).get("framing") or "").lower()
            if (
                cr == "detail"
                or "insert" in size
                or framing in {"union_closeup", "genital_lock"}
                or "close-up insert" in size
            ):
                detail_ids.append(str(s.get("id") or "?"))
        if any(_wardrobe_of(s) in {"undressed", "bare"} for s in shots) and not detail_ids:
            soft.append(
                {
                    "level": "soft",
                    "code": "MISSING_DETAIL_CU_COVERAGE",
                    "message": "max meat block has no detail/union insert shot planned",
                    "fix": "add coverage_role=detail or close-up insert for 定器特写 before bulk",
                }
            )
            gen_plan.append(
                {
                    "action": "plan_detail_cu_shot",
                    "why": "定器特写 required for mute-frame coitus readability",
                    "agent_hint": (
                        "Add or retarget one act shot: coverage_role=detail, "
                        "framing=union_closeup, shot_size close-up insert"
                    ),
                }
            )

    # --- keyframes for shots ---
    missing_kf = [r["id"] for r in shot_rows if r["id"] and not r["keyframe_ok"]]
    # only flag if production has started (any still registered or pilot)
    stills = man.get("stills") if isinstance(man.get("stills"), dict) else {}
    has_any_still = bool(stills) or any(r["keyframe_ok"] for r in shot_rows)
    if has_any_still and missing_kf:
        soft.append(
            {
                "level": "soft",
                "code": "MISSING_KEYFRAMES",
                "message": f"shots without keyframe file: {', '.join(missing_kf[:12])}",
                "fix": "generate keyframe from state photo / promote last frame before I2V",
            }
        )
        for sid in missing_kf:
            row = next((r for r in shot_rows if r["id"] == sid), {})
            gen_plan.append(
                {
                    "action": "generate_keyframe",
                    "shot_id": sid,
                    "wardrobe_state": row.get("wardrobe_state"),
                    "out": f"keyframes/{sid}.png",
                    "why": "I2V needs keyframe as frame-1; missing still breaks fluency",
                    "agent_hint": (
                        f"image_edit(state photo for {row.get('wardrobe_state')}) → "
                        f"keyframes/{sid}.png; never full cast if undressed"
                    ),
                }
            )

    # --- join fluency: continue pairs ---
    fluency_issues: list[dict[str, Any]] = []
    for i in range(len(shot_rows) - 1):
        a, b = shot_rows[i], shot_rows[i + 1]
        if not a["id"] or not b["id"]:
            continue
        # wardrobe re-dress rank drop (pixel-risk even if write-spec clamped)
        ra = WARDROBE_RANK.get(str(a["wardrobe_state"]), 0)
        rb = WARDROBE_RANK.get(str(b["wardrobe_state"]), 0)
        if rb < ra and a["wardrobe_state"] in UNDRESS_STATES:
            fluency_issues.append(
                {
                    "code": "WARDROBE_RANK_DROP",
                    "from": a["id"],
                    "to": b["id"],
                    "message": f"{a['id']} {a['wardrobe_state']} → {b['id']} {b['wardrobe_state']} re-dress risk",
                }
            )
            hard.append(
                {
                    "level": "hard" if heat_maxish else "soft",
                    "code": "STATE_INDEX_RE_DRESS",
                    "message": f"join {a['id']}→{b['id']}: wardrobe rank drops (re-dress)",
                    "fix": "clamp next wardrobe_state ≥ prev; rebuild next keyframe from undress-anchor",
                }
            )

        mode_b = b.get("chain_mode") or "continue"
        if mode_b in {"continue", "hold", "soft"} and a.get("clip_approved"):
            # next keyframe should exist for fluid I2V; prefer promote
            if not b.get("keyframe_ok"):
                fluency_issues.append(
                    {
                        "code": "PROMOTE_OR_KEYFRAME_NEEDED",
                        "from": a["id"],
                        "to": b["id"],
                        "message": f"{a['id']} has clip but {b['id']} has no keyframe — promote last frame",
                    }
                )
                gen_plan.append(
                    {
                        "action": "promote_last_to_keyframe",
                        "from_shot": a["id"],
                        "to_shot": b["id"],
                        "why": "continue join needs last frame of prev as first of next for fluid motion",
                        "cmd": (
                            f'aifilm extract-frame --root "{root}" --shot-id {a["id"]} '
                            f"--which last --promote-keyframe {b['id']}"
                        ),
                        "agent_hint": "register-clip auto_promote if enabled; else extract-frame --promote-keyframe",
                    }
                )
            elif a.get("clip_approved") and b.get("clip_approved") is False:
                # have keyframe, waiting I2V — soft ok
                pass

    # frame-chain receipt
    fc = read_json(root / "receipts" / "frame-chain.json") or {}
    if (
        heat_maxish
        and len(shot_rows) >= 3
        and not fc
        and any(r.get("clip_approved") for r in shot_rows)
    ):
        soft.append(
            {
                "level": "soft",
                "code": "FRAME_CHAIN_RECEIPT_THIN",
                "message": "clips exist but receipts/frame-chain.json empty/thin — joins may not be byte-promoted",
                "fix": "serial register-clip with auto_promote_next; or extract-frame --promote-keyframe",
            }
        )

    # de-dupe gen_plan by (action, shot_id/out)
    seen: set[str] = set()
    uniq_plan: list[dict[str, Any]] = []
    for g in gen_plan:
        key = f"{g.get('action')}:{g.get('shot_id') or g.get('to_shot') or g.get('out')}:{g.get('wardrobe_state')}"
        if key in seen:
            continue
        seen.add(key)
        uniq_plan.append(g)

    hard_n = sum(1 for x in hard if x.get("level") == "hard")
    # soft-level items mistakenly in hard list
    hard_only = [x for x in hard if x.get("level") == "hard"]
    soft.extend([x for x in hard if x.get("level") != "hard"])
    soft.extend(
        [
            {
                "level": "soft",
                "code": fi.get("code") or "FLUENCY",
                "message": fi.get("message") or "",
                "fix": "state-index plan / promote / rebuild keyframe from state photo",
            }
            for fi in fluency_issues
            if fi.get("code") != "WARDROBE_RANK_DROP"  # already in hard/soft
        ]
    )

    ok = hard_n == 0
    report = {
        "ok": ok,
        "kind": "state-index-gate",
        "schema_version": 1,
        "at": utc_now(),
        "root": str(root),
        "heat_scale": heat or None,
        "checkpoint": "state_index",
        "purpose": "check state photos + keyframes + join promote so I2V transitions stay fluid; regenerate gaps here",
        "shot_count": len(shot_rows),
        "states_needed": sorted(states_needed, key=lambda s: WARDROBE_RANK.get(s, 0)),
        "exact_state_ids": {key: sorted(value) for key, value in exact_state_ids.items()},
        "heroes": sorted(heroes),
        "state_index": state_index,
        "dialogue_state_index": dialogue_state_index,
        "dialogue_i2i_route": dialogue_i2i_route,
        "missing_dialogue_performance_states": missing_dialogue_states,
        "undress_anchor": {"path": str(anchor), "exists": anchor_ok, "required": needs_anchor},
        "shots": shot_rows,
        "missing_state_photos": missing_states,
        "missing_keyframes": missing_kf,
        "fluency_issues": fluency_issues,
        "hard": hard_only,
        "soft": soft,
        "generate_plan": uniq_plan,
        "next_if_gap": (f'aifilm state-index plan --root "{root}"' if uniq_plan else None),
        "agent_do": _agent_do(uniq_plan, ok),
        "ref": "references/keyframe-first-state-index.md · lessons-2026-07-21-wardrobe-no-redress-still.md",
    }
    return report


def _agent_do(plan: list[dict[str, Any]], ok: bool) -> list[str]:
    if ok and not plan:
        return [
            "state-index checkpoint PASS — proceed I2V serial; promote last→next keyframe on register",
        ]
    lines = [
        "state-index checkpoint: FIX gaps before bulk/final for fluid transitions",
        "order: (1) state photos (2) undress-anchor (3) missing keyframes from state photo (4) promote continue joins",
    ]
    for g in plan[:8]:
        lines.append(f"- [{g.get('action')}] {g.get('agent_hint') or g.get('cmd') or g.get('out')}")
    if len(plan) > 8:
        lines.append(f"- … +{len(plan) - 8} more (see generate_plan)")
    return lines


def write_state_index_receipt(root: Path, report: dict[str, Any]) -> Path:
    root = Path(root)
    rec_dir = root / "receipts"
    rec_dir.mkdir(parents=True, exist_ok=True)
    path = rec_dir / "state-index.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
