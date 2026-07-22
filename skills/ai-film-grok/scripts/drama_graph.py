#!/usr/bin/env python3
"""Vertical Drama Graph v0 — derive / validate / status from film-spec.

Phase 1: film-spec remains the executable source of truth.
drama-graph.json is a read-only structural projection for Agent planning.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from util import read_json, write_json

GRAPH_NAME = "drama-graph.json"
SCHEMA_VERSION = 1
KIND = "vertical-drama-graph"

# dramatic_function → beat bucket (v0 grouping)
_BEAT_BUCKETS: list[tuple[str, frozenset[str], str]] = [
    ("hook", frozenset({"hook"}), "climax"),
    ("approach", frozenset({"approach", "bridge"}), "supporting"),
    ("sensory", frozenset({"sensory", "action"}), "important"),
    ("reaction", frozenset({"reaction", "afterglow"}), "supporting"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def graph_path(root: Path) -> Path:
    return Path(root).expanduser().resolve() / GRAPH_NAME


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", (text or "").strip())[:48].strip("_")
    return s or fallback


def _load_spec(root: Path) -> dict[str, Any]:
    data = read_json(root / "film-spec.json") or {}
    return data if isinstance(data, dict) else {}


def _load_bible(root: Path) -> dict[str, Any]:
    data = read_json(root / "style-bible.json") or {}
    return data if isinstance(data, dict) else {}


def _iter_scenes(spec: dict[str, Any]) -> list[dict[str, Any]]:
    scenes = spec.get("scenes")
    if isinstance(scenes, list) and scenes:
        out: list[dict[str, Any]] = []
        for sc in scenes:
            if isinstance(sc, dict):
                out.append(sc)
        if out:
            return out
    # flat shots legacy
    shots = spec.get("shots")
    if isinstance(shots, list) and shots:
        return [{"title": "main", "summary": "", "shots": [s for s in shots if isinstance(s, dict)]}]
    return []


def _shot_list(scene: dict[str, Any]) -> list[dict[str, Any]]:
    shots = scene.get("shots") or []
    return [s for s in shots if isinstance(s, dict) and s.get("id")]


def _infer_production_mode(shot: dict[str, Any]) -> str:
    role = str(shot.get("shot_role") or "hero").strip().lower()
    if role in {"env", "bridge", "insert"}:
        return "text-to-video"
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    chain = str(dsl.get("chain_mode") or "continue").lower()
    # first-last when continue chain implies frame handoff
    if chain == "continue":
        return "single-keyframe-i2v"
    motion = str(dsl.get("motion") or shot.get("motion") or "").lower()
    if any(k in motion for k in ("static", "hold", "parallax", "ken burns", "push-in only")):
        return "panel-animation"
    return "single-keyframe-i2v"


def _infer_vertical_composition(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    size = str(cam.get("shot_size") or dsl.get("shot_size") or "").lower()
    if "ecu" in size or "extreme close" in size or "close" in size:
        return "center-subject"
    if "wide" in size or "establishing" in size:
        return "three-layer-depth"
    vp = str(dsl.get("viewpoint") or "").lower()
    if vp in {"dual", "ots"}:
        return "two-character-stack"
    return "center-subject"


def _beat_key(shot: dict[str, Any]) -> tuple[str, str, str]:
    """Return (bucket_id, objective, importance)."""
    df = str(shot.get("dramatic_function") or "action").strip().lower()
    for bid, funcs, importance in _BEAT_BUCKETS:
        if df in funcs:
            return bid, df, importance
    story = str((shot.get("dsl") or {}).get("story_beat") or df)
    return f"beat_{_slug(df, 'action')}", story or df, "supporting"


def _asset_hints(root: Path, shot_id: str) -> dict[str, Any]:
    kf_candidates = [
        root / "keyframes" / f"{shot_id}.png",
        root / "keyframes" / f"{shot_id}.jpg",
        root / "keyframes" / f"{shot_id}.webp",
    ]
    kf = next((p for p in kf_candidates if p.is_file()), None)
    prompt = root / "prompts" / f"{shot_id}.txt"
    clips_dir = root / "clips"
    clip = None
    if clips_dir.is_dir():
        for p in sorted(clips_dir.glob(f"{shot_id}*")):
            if p.suffix.lower() in {".mp4", ".mov", ".webm"} and p.is_file():
                clip = p
                break
    return {
        "keyframePath": str(kf) if kf else None,
        "clipPath": str(clip) if clip else None,
        "promptPath": str(prompt) if prompt.is_file() else None,
        "hasKeyframe": kf is not None,
        "hasClip": clip is not None,
        "hasPrompt": prompt.is_file(),
    }


def _panel_from_shot(shot: dict[str, Any], shot_id: str, prompt_path: str | None) -> dict[str, Any]:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    return {
        "id": f"panel_{shot_id}_01",
        "order": 1,
        "subject": str(dsl.get("subject") or shot.get("title") or shot_id),
        "action": str(dsl.get("action") or dsl.get("motion") or ""),
        "expression": str(dsl.get("expression") or ""),
        "location": str(dsl.get("location") or ""),
        "verticalComposition": _infer_vertical_composition(shot),
        "cameraAngle": str(cam.get("angle") or dsl.get("angle") or ""),
        "lighting": str(dsl.get("lighting") or ""),
        "style": str(dsl.get("style") or ""),
        "continuityConstraints": [
            c
            for c in [
                f"wardrobe_state={shot.get('wardrobe_state') or dsl.get('wardrobe_state') or ''}",
                f"chain_mode={dsl.get('chain_mode') or ''}",
            ]
            if c and not c.endswith("=")
        ],
        "negativeConstraints": [],
        "referenceAssetIds": [],
        "sourcePromptPath": prompt_path,
    }


def _characters_from_bible(bible: dict[str, Any]) -> list[dict[str, Any]]:
    chars = bible.get("characters")
    if not isinstance(chars, dict):
        return []
    out: list[dict[str, Any]] = []
    for cid, body in chars.items():
        if not isinstance(body, dict):
            out.append({"id": str(cid), "identity": str(body)})
            continue
        out.append(
            {
                "id": str(cid),
                "identity": str(body.get("identity") or ""),
                "defaultWardrobe": str(body.get("default_wardrobe") or ""),
                "castMaster": body.get("cast_master"),
            }
        )
    return out


def _locations_from_bible(bible: dict[str, Any]) -> list[dict[str, Any]]:
    locs = bible.get("locations")
    if not isinstance(locs, dict):
        return []
    out: list[dict[str, Any]] = []
    for k, v in locs.items():
        if isinstance(v, dict):
            out.append(
                {
                    "id": str(k),
                    "description": str(v.get("description") or v.get("name") or k),
                    "structure": str(v.get("structure") or ""),
                    "timeOfDay": str(v.get("timeOfDay") or v.get("time_of_day") or ""),
                    "lighting": str(v.get("lighting") or ""),
                    "immutableRules": list(v.get("immutableRules") or v.get("immutable_rules") or []),
                }
            )
        else:
            out.append({"id": str(k), "description": str(v)})
    return out


def _props_from_bible(bible: dict[str, Any]) -> list[dict[str, Any]]:
    props = bible.get("props")
    if not isinstance(props, dict):
        return []
    out: list[dict[str, Any]] = []
    for k, v in props.items():
        if isinstance(v, dict):
            out.append(
                {
                    "id": str(k),
                    "description": str(v.get("description") or v.get("name") or k),
                    "ownerId": v.get("ownerId") or v.get("owner_id"),
                    "condition": str(v.get("condition") or "intact"),
                    "storyFunction": str(v.get("storyFunction") or v.get("story_function") or ""),
                    "firstShotId": v.get("firstShotId") or v.get("first_shot_id"),
                    "lastShotId": v.get("lastShotId") or v.get("last_shot_id"),
                }
            )
        else:
            out.append({"id": str(k), "description": str(v)})
    return out


def derive_graph(root: Path, *, write: bool = True) -> dict[str, Any]:
    """Derive Vertical Drama Graph from film-spec (+ optional style-bible, assets)."""
    root = Path(root).expanduser().resolve()
    spec = _load_spec(root)
    bible = _load_bible(root)
    warnings: list[str] = []

    if not spec:
        warnings.append("film-spec.json missing or empty")

    title = str(spec.get("title") or root.name)
    aspect = str(spec.get("aspect_ratio") or "9:16")
    if aspect != "9:16":
        warnings.append(f"aspect_ratio={aspect} (vertical drama target is 9:16)")

    di = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    emotional = di.get("emotional_arc") if isinstance(di.get("emotional_arc"), list) else []

    scenes_out: list[dict[str, Any]] = []
    total_duration = 0.0
    global_shot_order = 0

    for si, scene in enumerate(_iter_scenes(spec), start=1):
        scene_id = f"sc{si:02d}_{_slug(str(scene.get('title') or 'scene'), f'sc{si}')}"
        shots_raw = _shot_list(scene)
        if not shots_raw:
            warnings.append(f"scene {si} has no shots")

        # Group consecutive shots into beats by dramatic_function bucket
        beat_groups: list[tuple[str, str, str, list[dict[str, Any]]]] = []
        for sh in shots_raw:
            bkey, objective, importance = _beat_key(sh)
            if beat_groups and beat_groups[-1][0] == bkey:
                beat_groups[-1][3].append(sh)
            else:
                beat_groups.append((bkey, objective, importance, [sh]))

        beats_out: list[dict[str, Any]] = []
        scene_dur = 0.0
        for bi, (bkey, objective, importance, group) in enumerate(beat_groups, start=1):
            beat_id = f"{scene_id}_bt{bi:02d}_{_slug(bkey, 'beat')}"
            shots_out: list[dict[str, Any]] = []
            beat_dur = 0.0
            for sh in group:
                global_shot_order += 1
                sid = str(sh.get("id"))
                dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
                dur = float(sh.get("duration_sec") or 0) or 0.0
                beat_dur += dur
                scene_dur += dur
                hints = _asset_hints(root, sid)
                panel = _panel_from_shot(sh, sid, hints.get("promptPath"))
                prod = _infer_production_mode(sh)
                cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
                shots_out.append(
                    {
                        "id": sid,
                        "order": global_shot_order,
                        "filmSpecShotId": sid,
                        "beat_id": str(sh.get("beat_id") or sh.get("beatId") or ""),
                        "source_refs": list(sh.get("source_refs") or []),
                        "narrativePurpose": str(
                            sh.get("title") or dsl.get("story_beat") or sh.get("dramatic_function") or ""
                        ),
                        "dramaticFunction": str(sh.get("dramatic_function") or ""),
                        "shotSize": str(cam.get("shot_size") or dsl.get("shot_size") or ""),
                        "verticalComposition": _infer_vertical_composition(sh),
                        "cameraMovement": str(dsl.get("camera_axis") or dsl.get("motion") or ""),
                        "productionMode": prod,
                        "targetDuration": dur or None,
                        "characterIds": list(
                            (dsl.get("cast") if isinstance(dsl.get("cast"), list) else None)
                            or sh.get("heroine_ids")
                            or []
                        ),
                        "locationId": None,
                        "wardrobeState": str(
                            sh.get("wardrobe_state") or dsl.get("wardrobe_state") or ""
                        ),
                        "heatPhase": str(sh.get("heat_phase") or ""),
                        "chainMode": str(dsl.get("chain_mode") or ""),
                        "coverage_role": str(sh.get("coverage_role") or ""),
                        "must_show": str(sh.get("must_show") or ""),
                        "visible_change": str(sh.get("visible_change") or ""),
                        "start_state": str(sh.get("start_state") or ""),
                        "end_state": str(sh.get("end_state") or ""),
                        "nar": str(sh.get("nar") or ""),
                        "panelIds": [panel["id"]],
                        "keyframeIds": [f"kf_{sid}"] if hints.get("hasKeyframe") else [],
                        "motionClipIds": [f"mc_{sid}"] if hints.get("hasClip") else [],
                        "dialogueLineIds": [f"dlg_{sid}"] if sh.get("nar") else [],
                        "panels": [panel],
                        "assetHints": hints,
                    }
                )
            beats_out.append(
                {
                    "id": beat_id,
                    "order": bi,
                    "objective": objective,
                    "action": objective,
                    "outcome": "",
                    "emotionalShift": {"from": "", "to": ""},
                    "importance": importance,
                    "targetDuration": beat_dur or None,
                    "shots": shots_out,
                }
            )

        # scene production mode: hybrid if mixed
        modes = {
            sh.get("productionMode")
            for bt in beats_out
            for sh in bt.get("shots") or []
            if isinstance(sh, dict)
        }
        if not modes:
            sc_mode = "unknown"
        elif len(modes) == 1:
            m = next(iter(modes))
            sc_mode = (
                "image-to-video"
                if m in {"single-keyframe-i2v", "first-last-frame-i2v"}
                else "static-motion-comic"
                if m == "panel-animation"
                else "video-generation"
                if m == "text-to-video"
                else "hybrid"
            )
        else:
            sc_mode = "hybrid"

        scenes_out.append(
            {
                "id": scene_id,
                "order": si,
                "title": str(scene.get("title") or f"Scene {si}"),
                "synopsis": str(scene.get("summary") or scene.get("synopsis") or ""),
                "locationId": None,
                "characterIds": [],
                "targetDuration": scene_dur or None,
                "productionMode": sc_mode,
                "status": "planned" if shots_raw else "parsed",
                "beats": beats_out,
            }
        )
        total_duration += scene_dur

    # episode hooks from director_intent / first-last dramatic functions
    opening = ""
    climax = ""
    ending = ""
    if emotional:
        opening = str(emotional[0])
        climax = str(emotional[len(emotional) // 2]) if len(emotional) > 1 else str(emotional[0])
        ending = str(emotional[-1])
    if di.get("logline"):
        opening = opening or str(di.get("logline"))

    episode = {
        "id": "ep01",
        "episodeNumber": 1,
        "title": title,
        "targetDuration": total_duration or None,
        "openingHook": opening,
        "centralConflict": str(di.get("theme") or di.get("tone") or ""),
        "climax": climax,
        "endingHook": ending,
        "aspectRatio": "9:16" if aspect == "9:16" else aspect,
        "status": "planning",
        "scenes": scenes_out,
    }

    # fps / resolution from timeline if present
    timeline = read_json(root / "timeline.json") or {}
    fps = int(timeline.get("fps") or 30)
    tw = int(timeline.get("width") or 720)
    th = int(timeline.get("height") or 1280)
    # export target preference
    target_res = "1080x1920" if aspect == "9:16" else f"{tw}x{th}"

    graph: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "derived_from": {
            "film_spec": str(root / "film-spec.json"),
            "style_bible": str(root / "style-bible.json") if (root / "style-bible.json").is_file() else None,
            "at": utc_now(),
            "mode": "derive",
        },
        "project": {
            "id": _slug(root.name, "project"),
            "title": title,
            "aspectRatio": aspect,
            "targetResolution": target_res,
            "targetFps": fps,
            "root": str(root),
        },
        "episodes": [episode],
        "characters": _characters_from_bible(bible),
        "locations": _locations_from_bible(bible),
        "props": _props_from_bible(bible),
        "warnings": warnings,
    }

    if write:
        write_json(graph_path(root), graph)
        # receipt
        write_json(
            root / "receipts" / "drama-graph.json",
            {
                "ok": True,
                "at": graph["derived_from"]["at"],
                "path": str(graph_path(root)),
                "shot_count": global_shot_order,
                "scene_count": len(scenes_out),
                "warnings": warnings,
            },
        )
    return graph


def validate_graph(graph: dict[str, Any] | None = None, root: Path | None = None) -> dict[str, Any]:
    """Structural validate (no jsonschema dependency required)."""
    errors: list[str] = []
    warnings: list[str] = []

    if graph is None:
        if root is None:
            return {"ok": False, "errors": ["root or graph required"], "warnings": []}
        root = Path(root).expanduser().resolve()
        graph = read_json(graph_path(root))
        if not graph:
            return {
                "ok": False,
                "errors": [f"missing {GRAPH_NAME} — run: aifilm graph derive --root …"],
                "warnings": [],
            }

    if not isinstance(graph, dict):
        return {"ok": False, "errors": ["graph is not an object"], "warnings": []}

    if graph.get("schema_version") not in {SCHEMA_VERSION, 2}:
        errors.append(f"schema_version must be {SCHEMA_VERSION} or 2")
    if graph.get("kind") not in (None, KIND):
        warnings.append(f"unexpected kind={graph.get('kind')}")

    project = graph.get("project")
    if not isinstance(project, dict) or not project.get("id") or not project.get("title"):
        errors.append("project.id and project.title required")

    shot_ids: set[str] = set()
    episodes = graph.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        errors.append("episodes must be non-empty")
    else:
        for ei, ep in enumerate(episodes):
            if not isinstance(ep, dict):
                errors.append(f"episodes[{ei}] not object")
                continue
            if not ep.get("id"):
                errors.append(f"episodes[{ei}].id missing")
            scenes = ep.get("scenes")
            if not isinstance(scenes, list) or not scenes:
                errors.append(f"episode {ep.get('id')} has no scenes")
                continue
            for si, sc in enumerate(scenes):
                if not isinstance(sc, dict):
                    errors.append(f"scene[{si}] not object")
                    continue
                beats = sc.get("beats")
                if not isinstance(beats, list) or not beats:
                    errors.append(f"scene {sc.get('id')} has no beats")
                    continue
                for bi, bt in enumerate(beats):
                    if not isinstance(bt, dict):
                        errors.append(f"beat[{bi}] not object")
                        continue
                    shots = bt.get("shots")
                    if not isinstance(shots, list) or not shots:
                        errors.append(f"beat {bt.get('id')} has no shots")
                        continue
                    for sh in shots:
                        if not isinstance(sh, dict) or not sh.get("id"):
                            errors.append("shot missing id")
                            continue
                        sid = str(sh["id"])
                        if sid in shot_ids:
                            errors.append(f"duplicate shot id {sid}")
                        shot_ids.add(sid)
                        panels = sh.get("panels")
                        if panels is not None and not isinstance(panels, list):
                            errors.append(f"shot {sid} panels must be array")
                        elif isinstance(panels, list):
                            for p in panels:
                                if isinstance(p, dict) and not p.get("id"):
                                    errors.append(f"shot {sid} panel missing id")
                                # panel must not be only free text — require subject or action
                                if isinstance(p, dict) and not (p.get("subject") or p.get("action")):
                                    warnings.append(f"shot {sid} panel has empty subject/action")

        if not shot_ids:
            errors.append("no shots in graph")

    for w in graph.get("warnings") or []:
        if isinstance(w, str):
            warnings.append(f"derive: {w}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "shot_count": len(shot_ids),
    }


def _count_tree(graph: dict[str, Any]) -> dict[str, int]:
    scenes = beats = shots = panels = 0
    with_kf = with_clip = 0
    for ep in graph.get("episodes") or []:
        if not isinstance(ep, dict):
            continue
        for sc in ep.get("scenes") or []:
            if not isinstance(sc, dict):
                continue
            scenes += 1
            for bt in sc.get("beats") or []:
                if not isinstance(bt, dict):
                    continue
                beats += 1
                for sh in bt.get("shots") or []:
                    if not isinstance(sh, dict):
                        continue
                    shots += 1
                    panels += len(sh.get("panels") or [])
                    hints = sh.get("assetHints") or {}
                    if hints.get("hasKeyframe"):
                        with_kf += 1
                    if hints.get("hasClip"):
                        with_clip += 1
    return {
        "episodes": len(graph.get("episodes") or []),
        "scenes": scenes,
        "beats": beats,
        "shots": shots,
        "panels": panels,
        "shots_with_keyframe": with_kf,
        "shots_with_clip": with_clip,
    }


def graph_status(root: Path, *, auto_derive: bool = True) -> dict[str, Any]:
    """Summary for agents / HUD."""
    root = Path(root).expanduser().resolve()
    path = graph_path(root)
    graph = read_json(path)
    derived = False
    if not graph and auto_derive and (root / "film-spec.json").is_file():
        graph = derive_graph(root, write=True)
        derived = True
    if not graph:
        return {
            "ok": False,
            "root": str(root),
            "path": str(path),
            "exists": False,
            "error": "no drama-graph and no film-spec to derive",
        }
    v = validate_graph(graph)
    counts = _count_tree(graph)
    return {
        "ok": bool(v.get("ok")),
        "root": str(root),
        "path": str(path),
        "exists": path.is_file(),
        "derived_now": derived,
        "schema_version": graph.get("schema_version"),
        "project": graph.get("project"),
        "counts": counts,
        "validate": v,
        "warnings": (graph.get("warnings") or []) + (v.get("warnings") or []),
        "line": (
            f"graph ep={counts['episodes']} sc={counts['scenes']} "
            f"bt={counts['beats']} sh={counts['shots']} "
            f"kf={counts['shots_with_keyframe']}/{counts['shots']} "
            f"clip={counts['shots_with_clip']}/{counts['shots']}"
        ),
    }


def iter_shots(graph: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
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
                    if isinstance(sh, dict):
                        out.append(sh)
    return out


def build_jobs_summary(root: Path, *, craft_stage: str | None = None) -> dict[str, Any]:
    """Execution Graph v0: linear jobs from graph asset gaps + craft stage.

    Not a full DAG runner — surface for Agent + dispatch packet.
    """
    root = Path(root).expanduser().resolve()
    st = graph_status(root, auto_derive=True)
    graph = read_json(graph_path(root)) or {}
    jobs: list[dict[str, Any]] = []

    def add(
        jid: str,
        skill_id: str,
        node_ref: str,
        status: str,
        depends_on: list[str] | None = None,
        cli: str | None = None,
        why: str = "",
        ) -> None:
        jobs.append(
            {
                "id": jid,
                "skillId": skill_id,
                "nodeRef": node_ref,
                "status": status,
                "dependsOn": depends_on or [],
                "cli": cli,
                "why": why,
            }
        )

    narrative = None
    narrative_gate_ids: list[str] = []
    try:
        from narrative_control import control_status

        narrative = control_status(root)
    except Exception as exc:  # pragma: no cover - defensive status path
        narrative = {"canonical": False, "error": str(exc)[:160]}
    if narrative and narrative.get("canonical"):
        semantic = narrative.get("semantic") or {}
        projection = narrative.get("projection") or {}
        semantic_ok = bool(semantic.get("ok"))
        locked = set(narrative.get("locked_scopes") or [])
        add(
            "job_story_validate",
            "story.validate",
            "story",
            "done" if semantic_ok else "ready",
            cli=None if semantic_ok else f'aifilm plan validate --root "{root}" --strict',
            why="story/beat/shot semantic contract" if semantic_ok else "missing story or shot semantics",
        )
        narrative_gate_ids.append("job_story_validate")
        add(
            "job_beat_validate",
            "beat.validate",
            "episode:ep01",
            "done" if semantic_ok else "blocked",
            depends_on=["job_story_validate"],
            why="beat outcomes and state deltas" if semantic_ok else "blocked by narrative validation",
        )
        narrative_gate_ids.append("job_beat_validate")
        add(
            "job_shot_plan",
            "shot.plan",
            "episode:ep01",
            "done" if semantic_ok else "blocked",
            depends_on=["job_beat_validate"],
            why="stable shot ids and distinct coverage" if semantic_ok else "blocked by beat validation",
        )
        narrative_gate_ids.append("job_shot_plan")
        add(
            "job_panel_layout",
            "panel.layout",
            "episode:ep01",
            "done" if semantic_ok else "blocked",
            depends_on=["job_shot_plan"],
            why="structured panels" if semantic_ok else "blocked by shot planning",
        )
        narrative_gate_ids.append("job_panel_layout")
        projection_ok = bool(projection.get("ok"))
        all_locked = all(scope in locked for scope in ("story", "beats", "shots", "panels"))
        project_status = "done" if semantic_ok and all_locked and projection_ok else "ready" if semantic_ok and all_locked else "blocked"
        add(
            "job_graph_project",
            "graph.project",
            "project",
            project_status,
            depends_on=["job_panel_layout"],
            cli=None if project_status == "done" else f'aifilm graph project --root "{root}" --force',
            why="graph → film-spec projection" if project_status != "done" else "projection current",
        )
        narrative_gate_ids.append("job_graph_project")
        add(
            "job_projection_verify",
            "projection.verify",
            "project",
            "done" if projection_ok else "blocked",
            depends_on=["job_graph_project"],
            why="source revision/hash binding" if projection_ok else "film-spec projection missing or stale",
        )
        narrative_gate_ids.append("job_projection_verify")

    # Bible / style
    if not (root / "style-bible.json").is_file():
        add(
            "job_bible_init",
            "character.bible.build",
            "project",
            "ready",
            cli=f'aifilm bible init --root "{root}"',
            why="missing style-bible",
        )
    else:
        bible = read_json(root / "style-bible.json") or {}
        locked = bool(bible.get("locked")) or str(bible.get("state") or "").lower() == "approved"
        add(
            "job_bible_lock",
            "character.bible.build",
            "project",
            "done" if locked else "ready",
            cli=None if locked else f'aifilm bible lock --root "{root}"',
            why="style locked" if locked else "lock style bible before bulk",
        )

    # Spec
    if not (root / "film-spec.json").is_file():
        status = "blocked" if narrative and narrative.get("canonical") else "ready"
        add(
            "job_write_spec",
            "shot.plan",
            "project",
            status,
            depends_on=["job_bible_lock"] + narrative_gate_ids[-2:],
            cli=f'aifilm write-spec --root "{root}"',
            why="missing film-spec",
        )
    else:
        status = "blocked" if narrative and narrative.get("canonical") and not narrative.get("ready_for_media") else "done"
        add(
            "job_write_spec",
            "shot.plan",
            "project",
            status,
            depends_on=["job_bible_lock"] + narrative_gate_ids[-2:],
            why="film-spec present",
        )

    # Graph derive always available
    add(
        "job_graph_derive",
        "scene.segment",
        "project",
        "done" if st.get("exists") or st.get("derived_now") else "ready",
        depends_on=["job_write_spec"],
        cli=f'aifilm graph derive --root "{root}"',
        why="Vertical Drama Graph projection",
    )

    for sh in iter_shots(graph):
        sid = str(sh.get("id"))
        hints = sh.get("assetHints") or {}
        mode = str(sh.get("productionMode") or "single-keyframe-i2v")
        # panel
        add(
            f"job_panel_{sid}",
            "panel.layout",
            f"shot:{sid}",
            "done" if sh.get("panels") else "ready",
            depends_on=["job_graph_derive"],
            why="panel from dsl/prompt",
        )
        # keyframe
        kf_status = "done" if hints.get("hasKeyframe") else "ready"
        add(
            f"job_kf_{sid}",
            "keyframe.generate",
            f"shot:{sid}",
            kf_status,
            depends_on=[f"job_panel_{sid}"],
            cli=None
            if hints.get("hasKeyframe")
            else f'# image_edit/gen → keyframes/{sid}.png → register-still',
            why="need keyframe" if kf_status == "ready" else "keyframe present",
        )
        # motion
        if mode == "panel-animation":
            skill = "camera.motion.plan"
        elif mode == "text-to-video":
            skill = "image.animate"
        else:
            skill = "image.animate"
        clip_status = "done" if hints.get("hasClip") else "ready"
        add(
            f"job_motion_{sid}",
            skill,
            f"shot:{sid}",
            clip_status,
            depends_on=[f"job_kf_{sid}"],
            cli=None
            if hints.get("hasClip")
            else f'aifilm media-queue / image_to_video → register-clip --shot-id {sid}',
            why=f"productionMode={mode}",
        )
        # voice if nar
        if sh.get("nar"):
            # VO often at final; mark ready until tts rehearsal exists
            tts_ok = (root / "receipts" / "tts-rehearsal.json").is_file()
            add(
                f"job_vo_{sid}",
                "voice.synthesize",
                f"shot:{sid}",
                "done" if tts_ok else "ready",
                depends_on=[f"job_motion_{sid}"],
                cli=None if tts_ok else f'aifilm tts-rehearse --root "{root}" --backend edge',
                why="nar present",
            )

    # assemble / render
    final_mp4 = list(root.glob("**/final*.mp4")) + list((root / "exports").glob("*.mp4") if (root / "exports").is_dir() else [])
    # also common path
    for cand in [root / "final.mp4", root / "deliverables" / "final.mp4"]:
        if cand.is_file():
            final_mp4.append(cand)
    has_final = any(p.is_file() for p in final_mp4)
    add(
        "job_render",
        "video.render",
        "episode:ep01",
        "done" if has_final else "blocked" if craft_stage in {"idea", "story", "beats"} else "ready",
        depends_on=["job_write_spec"],
        cli=f'aifilm final --root "{root}" --post-engine hyperframes',
        why="final mp4" if has_final else "await media then final",
    )
    add(
        "job_qa",
        "quality.inspect",
        "episode:ep01",
        "ready" if has_final else "blocked",
        depends_on=["job_render"],
        cli=f'aifilm review-final --root "{root}"',
        why="seven-dimension scorecard",
    )

    by_status: dict[str, int] = {}
    for j in jobs:
        stt = str(j.get("status") or "unknown")
        by_status[stt] = by_status.get(stt, 0) + 1

    ready = [j for j in jobs if j.get("status") == "ready"]
    primary = ready[0] if ready else None

    return {
        "schema_version": 1,
        "kind": "execution-jobs-summary",
        "at": utc_now(),
        "root": str(root),
        "craft_stage": craft_stage,
        "graph_line": st.get("line"),
        "counts_by_status": by_status,
        "ready_count": len(ready),
        "done_count": by_status.get("done", 0),
        "blocked_count": by_status.get("blocked", 0),
        "total": len(jobs),
        "primary_job": primary,
        "jobs": jobs,
        "jobs_preview": jobs[:24],
    }
