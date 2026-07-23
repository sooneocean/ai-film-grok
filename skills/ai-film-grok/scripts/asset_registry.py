#!/usr/bin/env python3
"""Phase 4: structured Character / Location / Prop + CharacterState timeline.

Aligns style-bible, drama-graph, and state-index (wardrobe ladder / cast-states).
Does not invent pixels — only registry slots, variants, and consistency reports.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from util import read_json, write_json

REGISTRY_NAME = "assets-registry.json"
SCHEMA_VERSION = 1
KIND = "asset-registry"

WARDROBE_RANK: dict[str, int] = {
    "full": 0,
    "armored": 1,
    "partial": 2,
    "undressed": 3,
    "bare": 4,
    "default": 0,
}
WARDROBE_LADDER = ("full", "armored", "partial", "undressed", "bare")
DEFAULT_VARIANT_BLURBS = {
    "full": "full clothing / default outfit",
    "armored": "outer layer / coat / armor still on",
    "partial": "partial undress — top or bottom open/off",
    "undressed": "mostly undressed — peak undress state",
    "bare": "bare / minimal coverage",
    "default": "default wardrobe",
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def registry_path(root: Path) -> Path:
    return Path(root).expanduser().resolve() / REGISTRY_NAME


def _slug(text: str, fallback: str = "x") -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", (text or "").strip())[:40].strip("_")
    return s or fallback


def _loc_desc(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("description") or value.get("synopsis") or value.get("name") or "")
    return str(value or "")


def _loc_object(lid: str, value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        out = {
            "id": lid,
            "description": str(value.get("description") or value.get("name") or lid),
            "structure": str(value.get("structure") or ""),
            "timeOfDay": str(value.get("timeOfDay") or value.get("time_of_day") or ""),
            "lighting": str(value.get("lighting") or ""),
            "palette": str(value.get("palette") or ""),
            "immutableRules": list(
                value.get("immutableRules") or value.get("immutable_rules") or []
            ),
            "recurringObjects": list(
                value.get("recurringObjects") or value.get("recurring_objects") or []
            ),
            "primaryAngles": list(value.get("primaryAngles") or value.get("primary_angles") or []),
        }
        return out
    return {
        "id": lid,
        "description": str(value or lid),
        "structure": "",
        "timeOfDay": "",
        "lighting": "",
        "palette": "",
        "immutableRules": [],
        "recurringObjects": [],
        "primaryAngles": [],
    }


def _prop_object(pid: str, value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "id": pid,
            "description": str(value.get("description") or value.get("name") or pid),
            "ownerId": value.get("ownerId") or value.get("owner_id"),
            "locationId": value.get("locationId") or value.get("location_id"),
            "condition": str(value.get("condition") or "intact"),
            "storyFunction": str(value.get("storyFunction") or value.get("story_function") or ""),
            "firstShotId": value.get("firstShotId") or value.get("first_shot_id"),
            "lastShotId": value.get("lastShotId") or value.get("last_shot_id"),
        }
    return {
        "id": pid,
        "description": str(value or pid),
        "ownerId": None,
        "locationId": None,
        "condition": "intact",
        "storyFunction": "",
        "firstShotId": None,
        "lastShotId": None,
    }


def _shots_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict) and sh.get("id"):
                out.append(sh)
    if not out and isinstance(spec.get("shots"), list):
        out = [s for s in spec["shots"] if isinstance(s, dict) and s.get("id")]
    return out


def _wardrobe_of(shot: dict[str, Any]) -> str:
    w = shot.get("wardrobe_state") or (shot.get("dsl") or {}).get("wardrobe_state") or "full"
    w = str(w).strip().lower() or "full"
    if w not in WARDROBE_RANK:
        w = "full"
    return w


def _hero_ids(shot: dict[str, Any], fallback: list[str] | None = None) -> list[str]:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cast = dsl.get("cast") if isinstance(dsl.get("cast"), list) else []
    if cast:
        return [str(c) for c in cast if c]
    hids = shot.get("heroine_ids")
    if isinstance(hids, list) and hids:
        return [str(x) for x in hids if x]
    return list(fallback or ["hero"])


def _ensure_wardrobe_variants(
    bible: dict[str, Any],
    character_id: str,
    states_used: set[str],
    *,
    force: bool = False,
) -> dict[str, str]:
    wv = bible.setdefault("wardrobe_variants", {})
    if not isinstance(wv, dict):
        wv = {}
        bible["wardrobe_variants"] = wv
    block = wv.get(character_id)
    if not isinstance(block, dict):
        block = {}
    # always ensure full + any used states + undress ladder tips if any undress used
    needed = set(states_used) | {"full", "default"}
    if states_used & {"partial", "undressed", "bare"}:
        needed |= {"partial", "undressed", "bare"}
    for st in needed:
        key = st if st != "default" else "full"
        if key not in block or force:
            if key not in block:
                block[key] = DEFAULT_VARIANT_BLURBS.get(key, key)
    # keep default alias
    if "default" not in block:
        block["default"] = block.get("full") or DEFAULT_VARIANT_BLURBS["default"]
    wv[character_id] = block
    return block


def _ensure_cast_state_slots(
    root: Path,
    bible: dict[str, Any],
    character_id: str,
    states_used: set[str],
) -> dict[str, Any]:
    """Register expected paths in cast_state_masters; create dirs (no pixel gen)."""
    csm = bible.setdefault("cast_state_masters", {})
    if not isinstance(csm, dict):
        csm = {}
        bible["cast_state_masters"] = csm
    block = csm.get(character_id)
    if not isinstance(block, dict):
        block = {}
    states_dir = root / "canonical" / "cast-states" / character_id
    states_dir.mkdir(parents=True, exist_ok=True)
    (root / "canonical" / "wardrobe").mkdir(parents=True, exist_ok=True)

    needed = set(states_used) | {"full"}
    if states_used & {"partial", "undressed", "bare"}:
        needed |= {"partial", "undressed", "bare"}

    slots: dict[str, Any] = {}
    for st in sorted(needed, key=lambda s: WARDROBE_RANK.get(s, 0)):
        rel = f"canonical/cast-states/{character_id}/{st}.png"
        # prefer existing registered path
        existing = block.get(st)
        path_str = str(existing) if existing else rel
        abs_p = Path(path_str)
        if not abs_p.is_absolute():
            abs_p = root / path_str
        # discover any extension on disk
        exists = abs_p.is_file()
        if not exists:
            for ext in (".png", ".jpg", ".jpeg", ".webp"):
                cand = root / "canonical" / "cast-states" / character_id / f"{st}{ext}"
                if cand.is_file():
                    try:
                        path_str = str(cand.relative_to(root))
                    except ValueError:
                        path_str = str(cand)
                    exists = True
                    abs_p = cand
                    break
        if st not in block or not block.get(st):
            block[st] = path_str

        final_path = str(block.get(st) or path_str)
        fp = Path(final_path)
        if not fp.is_absolute():
            fp = root / final_path
        slots[st] = {
            "path": final_path,
            "exists": fp.is_file() or exists,
            "rank": WARDROBE_RANK.get(st, 0),
        }
    # full may fall back to cast_master
    cm = bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
    if "full" in slots and not slots["full"].get("exists"):
        master = cm.get(character_id) or cm.get("hero")
        if master:
            mp = Path(str(master))
            if not mp.is_absolute():
                mp = root / master
            if mp.is_file():
                slots["full"]["path"] = str(master)
                slots["full"]["exists"] = True
                if not block.get("full"):
                    block["full"] = str(master)

    csm[character_id] = block
    # also mirror cast_master on character if present
    chars = bible.get("characters") if isinstance(bible.get("characters"), dict) else {}
    if character_id in chars and isinstance(chars[character_id], dict):
        if cm.get(character_id) and not chars[character_id].get("cast_master"):
            chars[character_id]["cast_master"] = cm[character_id]
    return slots


def _structure_locations(bible: dict[str, Any], *, force: bool = False) -> list[dict[str, Any]]:
    locs = bible.get("locations")
    if not isinstance(locs, dict):
        return []
    out: list[dict[str, Any]] = []
    new_map: dict[str, Any] = {}
    for lid, val in locs.items():
        obj = _loc_object(str(lid), val)
        out.append(obj)
        # store structured form in bible (object), keep description accessible
        if force or not isinstance(val, dict):
            new_map[str(lid)] = {
                "description": obj["description"],
                "structure": obj["structure"],
                "timeOfDay": obj["timeOfDay"],
                "lighting": obj["lighting"],
                "palette": obj["palette"],
                "immutableRules": obj["immutableRules"],
                "recurringObjects": obj["recurringObjects"],
                "primaryAngles": obj["primaryAngles"],
            }
        else:
            new_map[str(lid)] = val if isinstance(val, dict) else obj
    bible["locations"] = new_map
    return out


def _structure_props(
    bible: dict[str, Any],
    shots: list[dict[str, Any]],
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    props = bible.get("props")
    if not isinstance(props, dict):
        props = {}
    # harvest props from shot dsl
    for sh in shots:
        dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
        raw = dsl.get("props") or dsl.get("prop")
        names: list[str] = []
        if isinstance(raw, list):
            names = [str(x) for x in raw if x]
        elif isinstance(raw, str) and raw.strip():
            names = [raw.strip()]
        for name in names:
            pid = _slug(name, "prop")
            if pid not in props:
                props[pid] = {
                    "description": name,
                    "firstShotId": sh.get("id"),
                    "lastShotId": sh.get("id"),
                    "storyFunction": "scene prop",
                }
            elif isinstance(props[pid], dict):
                props[pid]["lastShotId"] = sh.get("id")
                if not props[pid].get("firstShotId"):
                    props[pid]["firstShotId"] = sh.get("id")

    out: list[dict[str, Any]] = []
    new_map: dict[str, Any] = {}
    for pid, val in props.items():
        obj = _prop_object(str(pid), val)
        out.append(obj)
        if force or not isinstance(val, dict):
            new_map[str(pid)] = {
                "description": obj["description"],
                "ownerId": obj["ownerId"],
                "locationId": obj["locationId"],
                "condition": obj["condition"],
                "storyFunction": obj["storyFunction"],
                "firstShotId": obj["firstShotId"],
                "lastShotId": obj["lastShotId"],
            }
        else:
            new_map[str(pid)] = val
    bible["props"] = new_map
    return out


def _build_state_timeline(
    shots: list[dict[str, Any]],
    character_ids: list[str],
) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    prev_rank: dict[str, int] = {c: 0 for c in character_ids}
    for sh in shots:
        sid = str(sh.get("id"))
        w = _wardrobe_of(sh)
        hids = _hero_ids(sh, fallback=character_ids[:1] or ["hero"])
        for hid in hids:
            rank = WARDROBE_RANK.get(w, 0)
            prev = prev_rank.get(hid, 0)
            re_dress = rank < prev
            timeline.append(
                {
                    "shotId": sid,
                    "characterId": hid,
                    "wardrobeState": w,
                    "rank": rank,
                    "reDressRisk": re_dress,
                    "heatPhase": str(sh.get("heat_phase") or ""),
                    "emotion": str((sh.get("dsl") or {}).get("expression") or ""),
                }
            )
            if not re_dress:
                prev_rank[hid] = max(prev, rank)
            # if re-dress, still record but don't lower peak tracking for gate
            else:
                pass
    return timeline


def _align_with_state_index(root: Path, registry: dict[str, Any]) -> dict[str, Any]:
    """Compare registry state slots with state_index_gate output."""
    try:
        from state_index_gate import run_state_index_check

        si = run_state_index_check(root)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc)[:200],
            "aligned": False,
            "issues": [f"state_index_check failed: {exc}"],
        }

    issues: list[str] = []
    reg_states = registry.get("characters") or []
    # missing exists in registry that state-index also flags
    for ch in reg_states:
        if not isinstance(ch, dict):
            continue
        hid = ch.get("id")
        for st, slot in (ch.get("states") or {}).items():
            if not isinstance(slot, dict):
                continue
            if st in {"partial", "undressed", "bare"} and not slot.get("exists"):
                # only issue if used in timeline
                used = any(
                    t.get("characterId") == hid and t.get("wardrobeState") == st
                    for t in (registry.get("characterStatesTimeline") or [])
                )
                if used:
                    issues.append(f"missing_state_photo:{hid}:{st}")

    re_dress = [
        t
        for t in (registry.get("characterStatesTimeline") or [])
        if isinstance(t, dict) and t.get("reDressRisk")
    ]
    for t in re_dress:
        issues.append(
            f"re_dress_risk:{t.get('characterId')}:{t.get('shotId')}:{t.get('wardrobeState')}"
        )

    gen_plan = si.get("generate_plan") or []
    return {
        "ok": len(issues) == 0,
        "aligned": len(issues) == 0,
        "issues": issues,
        "state_index_ok": bool(si.get("ok")),
        "state_index_soft": len(si.get("soft") or []),
        "state_index_hard": len(si.get("hard") or []),
        "generate_plan_count": len(gen_plan),
        "generate_plan_preview": gen_plan[:8],
        "fluency": si.get("fluency"),
    }


def sync_assets(
    root: Path,
    *,
    write: bool = True,
    force: bool = False,
    update_graph: bool = True,
) -> dict[str, Any]:
    """character.bible / location.bible / prop.track / character.state.update shell."""
    root = Path(root).expanduser().resolve()
    from visual_bible import load_bible, migrate_to_v2, save_bible

    bible = migrate_to_v2(load_bible(root))
    locked = bool(bible.get("locked")) or str(bible.get("state") or "").lower() == "approved"
    if locked and force:
        # still allow filling empty slots only — never wipe identity
        pass

    spec = read_json(root / "film-spec.json") or {}
    shots = _shots_from_spec(spec)

    # character ids from bible + shots
    chars_map = bible.get("characters") if isinstance(bible.get("characters"), dict) else {}
    char_ids: list[str] = [str(k) for k in chars_map]
    for sh in shots:
        for hid in _hero_ids(sh, fallback=[]):
            if hid not in char_ids:
                char_ids.append(hid)
                if hid not in chars_map:
                    chars_map[hid] = {
                        "identity": hid,
                        "default_wardrobe": "",
                        "cast_master": "",
                    }
    if not char_ids:
        char_ids = ["hero"]
        chars_map.setdefault(
            "hero",
            {"identity": "主角", "default_wardrobe": "", "cast_master": ""},
        )
    bible["characters"] = chars_map

    # states used per character
    used_by_char: dict[str, set[str]] = {c: set() for c in char_ids}
    for sh in shots:
        w = _wardrobe_of(sh)
        for hid in _hero_ids(sh, fallback=char_ids[:1]):
            used_by_char.setdefault(hid, set()).add(w)

    characters_out: list[dict[str, Any]] = []
    for cid in char_ids:
        body = (
            chars_map.get(cid)
            if isinstance(chars_map.get(cid), dict)
            else {"identity": str(chars_map.get(cid) or cid)}
        )
        used = used_by_char.get(cid) or {"full"}
        variants = _ensure_wardrobe_variants(bible, cid, used, force=False)
        slots = _ensure_cast_state_slots(root, bible, cid, used)
        # forbid drift defaults
        forbid = (
            body.get("forbid_drift")
            or body.get("forbidDrift")
            or [
                "face identity",
                "hair color",
                "age band",
            ]
        )
        characters_out.append(
            {
                "id": cid,
                "identity": str(body.get("identity") or cid),
                "defaultWardrobe": str(body.get("default_wardrobe") or variants.get("full") or ""),
                "castMaster": body.get("cast_master") or (bible.get("cast_masters") or {}).get(cid),
                "states": slots,
                "wardrobeVariants": variants,
                "forbidDrift": list(forbid) if isinstance(forbid, list) else [str(forbid)],
                "statesUsed": sorted(used, key=lambda s: WARDROBE_RANK.get(s, 0)),
            }
        )

    locations_out = _structure_locations(bible, force=force)
    props_out = _structure_props(bible, shots, force=force)
    timeline = _build_state_timeline(shots, char_ids)

    # continuity_states summary
    cont = bible.setdefault("continuity_states", {})
    if not isinstance(cont, dict):
        cont = {}
        bible["continuity_states"] = cont
    for cid in char_ids:
        peak = "full"
        peak_rank = 0
        for t in timeline:
            if t.get("characterId") == cid and not t.get("reDressRisk"):
                if int(t.get("rank") or 0) >= peak_rank:
                    peak_rank = int(t.get("rank") or 0)
                    peak = str(t.get("wardrobeState") or "full")
        cont[f"{cid}_wardrobe_peak"] = peak

    registry: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "at": utc_now(),
        "root": str(root),
        "bible_locked": locked,
        "characters": characters_out,
        "locations": locations_out,
        "props": props_out,
        "characterStatesTimeline": timeline,
        "counts": {
            "characters": len(characters_out),
            "locations": len(locations_out),
            "props": len(props_out),
            "state_events": len(timeline),
            "re_dress_risks": sum(1 for t in timeline if t.get("reDressRisk")),
        },
    }
    alignment = _align_with_state_index(root, registry)
    registry["consistency"] = alignment

    if write:
        save_bible(root, bible)
        write_json(registry_path(root), registry)
        write_json(
            root / "receipts" / "assets-sync.json",
            {
                "ok": bool(alignment.get("aligned")),
                "at": registry["at"],
                "counts": registry["counts"],
                "consistency": alignment,
                "path": str(registry_path(root)),
            },
        )
        if update_graph:
            _sync_graph_assets(root, registry)

    return {
        "ok": True,
        "path": str(registry_path(root)),
        "counts": registry["counts"],
        "consistency": alignment,
        "bible_locked": locked,
        "characters": [c["id"] for c in characters_out],
        "locations": [x["id"] for x in locations_out],
        "props": [p["id"] for p in props_out],
        "line": (
            f"assets char={len(characters_out)} loc={len(locations_out)} "
            f"prop={len(props_out)} states={len(timeline)} "
            f"re_dress={registry['counts']['re_dress_risks']} "
            f"aligned={alignment.get('aligned')}"
        ),
        "next": [
            f'aifilm state-index check --root "{root}"',
            f'aifilm assets status --root "{root}"',
        ],
    }


def _sync_graph_assets(root: Path, registry: dict[str, Any]) -> None:
    """Write characters/locations/props/characterStates into drama-graph if present."""
    from drama_graph import GRAPH_NAME

    gpath = root / GRAPH_NAME
    graph = read_json(gpath)
    if not graph:
        return
    graph["characters"] = [
        {
            "id": c["id"],
            "identity": c.get("identity"),
            "defaultWardrobe": c.get("defaultWardrobe"),
            "castMaster": c.get("castMaster"),
            "states": c.get("states"),
            "statesUsed": c.get("statesUsed"),
            "forbidDrift": c.get("forbidDrift"),
        }
        for c in (registry.get("characters") or [])
        if isinstance(c, dict)
    ]
    graph["locations"] = list(registry.get("locations") or [])
    graph["props"] = list(registry.get("props") or [])
    graph["characterStates"] = list(registry.get("characterStatesTimeline") or [])
    graph["assetRegistry"] = {
        "path": str(registry_path(root)),
        "at": registry.get("at"),
        "counts": registry.get("counts"),
        "consistencyAligned": (registry.get("consistency") or {}).get("aligned"),
    }
    # patch shot wardrobe from timeline for consistency
    by_shot: dict[str, list[dict[str, Any]]] = {}
    for t in registry.get("characterStatesTimeline") or []:
        if isinstance(t, dict) and t.get("shotId"):
            by_shot.setdefault(str(t["shotId"]), []).append(t)
    for ep in graph.get("episodes") or []:
        if not isinstance(ep, dict):
            continue
        for sc in ep.get("scenes") or []:
            if not isinstance(sc, dict):
                continue
            for bt in sc.get("beats") or []:
                if not isinstance(bt, dict):
                    continue
                for sh in bt.get("shots") or []:
                    if not isinstance(sh, dict):
                        continue
                    sid = str(sh.get("id") or "")
                    events = by_shot.get(sid) or []
                    if events:
                        # primary hero first event
                        sh["wardrobeState"] = events[0].get("wardrobeState") or sh.get(
                            "wardrobeState"
                        )
                        sh["characterStateRefs"] = [
                            f"{e.get('characterId')}:{e.get('wardrobeState')}" for e in events
                        ]
    write_json(gpath, graph)


def assets_status(root: Path, *, auto_sync: bool = False) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    path = registry_path(root)
    reg = read_json(path)
    if not reg and auto_sync:
        return sync_assets(root, write=True)
    if not reg:
        return {
            "ok": False,
            "exists": False,
            "path": str(path),
            "error": "missing assets-registry.json — run: aifilm assets sync --root …",
        }
    return {
        "ok": True,
        "exists": True,
        "path": str(path),
        "counts": reg.get("counts"),
        "consistency": reg.get("consistency"),
        "characters": [c.get("id") for c in (reg.get("characters") or []) if isinstance(c, dict)],
        "line": (
            f"assets char={reg.get('counts', {}).get('characters')} "
            f"loc={reg.get('counts', {}).get('locations')} "
            f"prop={reg.get('counts', {}).get('props')} "
            f"aligned={(reg.get('consistency') or {}).get('aligned')}"
        ),
        "at": reg.get("at"),
    }


def assets_check(root: Path, *, sync_first: bool = True) -> dict[str, Any]:
    """Consistency check: registry ↔ state-index ↔ wardrobe monotonicity."""
    root = Path(root).expanduser().resolve()
    if sync_first or not registry_path(root).is_file():
        sync_rep = sync_assets(root, write=True)
    else:
        sync_rep = assets_status(root)
        reg = read_json(registry_path(root)) or {}
        sync_rep = {
            "ok": True,
            "consistency": reg.get("consistency"),
            "counts": reg.get("counts"),
            "line": assets_status(root).get("line"),
        }
    cons = sync_rep.get("consistency") or {}
    re_dress = int((sync_rep.get("counts") or {}).get("re_dress_risks") or 0)
    ok = bool(cons.get("aligned")) and re_dress == 0
    return {
        "ok": ok,
        "aligned": bool(cons.get("aligned")),
        "re_dress_risks": re_dress,
        "issues": list(cons.get("issues") or []),
        "generate_plan_preview": cons.get("generate_plan_preview") or [],
        "consistency": (sync_rep.get("consistency") or {}),
        "counts": sync_rep.get("counts"),
        "line": sync_rep.get("line"),
        "path": str(registry_path(root)),
        "hard_fail_redress": re_dress > 0,
        "hint": (
            "ok"
            if ok
            else "fix re_dress in film-spec wardrobe_state; generate missing cast-states via state-index plan"
        ),
    }


CHARACTER_STATE_AXES = {
    "wardrobe": ["full", "loosened", "partial", "undressed", "bare"],
    "hair": ["neat", "slightly_moussed", "disheveled", "sweat_moistened_strands"],
    "skin": ["normal", "flushed", "glistening_sweat", "afterglow_blush"],
    "arousal": ["calm", "intrigued", "heavy_breathing", "climax_ecstasy"],
    "expression": [
        "calm",
        "flushed_anticipation",
        "lip_bite_gasp",
        "ecstasy_eyes_closed",
        "gentle_smile_tear",
    ],
}


def derive_character_state_timeline(
    shots: list[dict[str, Any]], heroine_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Derive monotonic multi-axis character states for shots within a scene."""
    if not shots:
        return []

    curr_states: dict[str, int] = {
        "wardrobe": 0,
        "hair": 0,
        "skin": 0,
        "arousal": 0,
        "expression": 0,
    }

    timeline = []
    for shot in shots:
        hp = (
            str(
                shot.get("heat_phase")
                or (shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}).get("heat_phase")
                or ""
            )
            .strip()
            .lower()
        )

        # Map heat phase to target minimum state levels
        if hp in {"act", "climax"}:
            target = {"wardrobe": 3, "hair": 2, "skin": 2, "arousal": 3, "expression": 3}
        elif hp == "foreplay":
            target = {"wardrobe": 2, "hair": 1, "skin": 1, "arousal": 2, "expression": 2}
        elif hp == "teaser":
            target = {"wardrobe": 1, "hair": 1, "skin": 1, "arousal": 1, "expression": 1}
        elif hp == "afterglow":
            target = {"wardrobe": 3, "hair": 3, "skin": 3, "arousal": 1, "expression": 4}
        else:
            target = {"wardrobe": 0, "hair": 0, "skin": 0, "arousal": 0, "expression": 0}

        # Monotonic non-regression: state level cannot decrease within scene
        for axis, target_idx in target.items():
            curr_states[axis] = max(curr_states[axis], target_idx)

        shot_states = {
            axis: CHARACTER_STATE_AXES[axis][curr_states[axis]] for axis in CHARACTER_STATE_AXES
        }
        timeline.append(
            {
                "shot_id": str(shot.get("id")),
                "heat_phase": hp,
                "character_states": shot_states,
            }
        )

    return timeline
