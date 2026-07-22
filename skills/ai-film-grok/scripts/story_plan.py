#!/usr/bin/env python3
"""Phase 3: story.normalize → episode/scene/beat/shot planning.

Deterministic structure planner for vertical (9:16) drama.
Does NOT call external LLMs — Agent may refine nar/dsl after plan run.
Produces drama-graph.json (planned) + optional film-spec seed.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from util import read_json, write_json
from narrative_control import (
    GRAPH_SCHEMA_VERSION,
    bump_graph_revision,
    ensure_graph_controls,
    draft_director_board,
    graph_content_sha256,
    validate_narrative_graph,
)

# film-spec dramatic_function enum
DRAMATIC_FUNCS = (
    "hook",
    "approach",
    "sensory",
    "reaction",
    "action",
    "afterglow",
    "bridge",
)

# Default vertical short-form beat spine (hook → ending hook)
DEFAULT_BEAT_SPINE: list[dict[str, Any]] = [
    {
        "key": "hook",
        "dramatic_function": "hook",
        "importance": "climax",
        "objective": "开场钩子：异常/欲望/冲突入口",
        "weight": 0.12,
        "shots_n": 1,
    },
    {
        "key": "setup",
        "dramatic_function": "approach",
        "importance": "supporting",
        "objective": "建立人物关系与空间",
        "weight": 0.18,
        "shots_n": 1,
    },
    {
        "key": "escalate",
        "dramatic_function": "sensory",
        "importance": "important",
        "objective": "情绪/信息升级",
        "weight": 0.22,
        "shots_n": 2,
    },
    {
        "key": "peak",
        "dramatic_function": "action",
        "importance": "climax",
        "objective": "高潮或关键决定",
        "weight": 0.28,
        "shots_n": 2,
    },
    {
        "key": "button",
        "dramatic_function": "afterglow",
        "importance": "supporting",
        "objective": "余韵与下一集钩子",
        "weight": 0.20,
        "shots_n": 1,
    },
]

_SCENE_HDR = re.compile(
    r"^(?:#{1,3}\s*|场景\s*[:：]?\s*|Scene\s*\d*\s*[:：]?\s*|第[一二三四五六七八九十\d]+场\s*[:：]?\s*)(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_CHAR_LINE = re.compile(
    r"(?:角色|人物|女主|男主|主角|配角)\s*[:：]\s*(.+)$",
    re.MULTILINE,
)
_DIALOGUE = re.compile(r"^[\s]*([^\s:：]{1,12})\s*[:：]\s*(.+)$", re.MULTILINE)
_NAME_CAND = re.compile(r"[\u4e00-\u9fff]{2,4}")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(text: str, fallback: str = "x") -> str:
    s = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff-]+", "_", (text or "").strip())[:40].strip("_")
    # film-spec shot ids must be ascii-ish for validate_identifier — keep latin
    s2 = re.sub(r"[^A-Za-z0-9_-]+", "_", s)[:32].strip("_")
    return s2 or fallback


def _clip_nar(text: str, max_chars: int = 55) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return "……"
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _est_vo_sec(nar: str) -> float:
    """Match film_spec.estimate_nar_vo_sec (zh ≈ 4 chars/s)."""
    t = (nar or "").strip()
    if not t:
        return 0.0
    return max(1.0, round(len(t) / 4.0, 2))


def _duration_for_nar(nar: str, floor: float = 3.0) -> float:
    """Ensure write-spec vo_pacing: est_vo ≤ duration + 0.5."""
    need = _est_vo_sec(nar) + 0.5 + 0.05
    return max(float(floor), round(need, 1))


def _split_paragraphs(raw: str) -> list[str]:
    parts = re.split(r"\n\s*\n+", (raw or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _extract_title(raw: str, title_hint: str | None) -> str:
    if title_hint and title_hint.strip():
        return title_hint.strip()[:80]
    lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    if not lines:
        return "untitled-drama"
    first = lines[0]
    if first.startswith("#"):
        return first.lstrip("#").strip()[:80] or "untitled-drama"
    if len(first) <= 24:
        return first
    # one-liner idea → short title from first 12 chars
    return first[:12].rstrip("，。,. ") + ("…" if len(first) > 12 else "")


def _character_candidates(raw: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(name: str, role: str = "supporting") -> None:
        n = name.strip().strip("、，, ")
        if not n or n in seen or len(n) > 12:
            return
        seen.add(n)
        cid = _slug(n, f"char{len(found)+1}")
        # force ascii id
        if not re.match(r"^[A-Za-z]", cid):
            cid = f"c{len(found)+1}_{cid}" if cid else f"char{len(found)+1}"
            cid = re.sub(r"[^A-Za-z0-9_-]", "", cid) or f"char{len(found)+1}"
        found.append({"id": cid, "name": n, "role": role, "source": "extract"})

    for m in _CHAR_LINE.finditer(raw or ""):
        for part in re.split(r"[、,，/|]", m.group(1)):
            add(part, "lead")

    for m in _DIALOGUE.finditer(raw or ""):
        speaker = m.group(1).strip()
        if speaker not in {"旁白", "OS", "VO", "内心"}:
            add(speaker, "speaking")

    # keyword roles
    if re.search(r"女主|她|姑娘|司机", raw or ""):
        if "hero" not in {c["id"] for c in found}:
            found.insert(0, {"id": "hero", "name": "女主", "role": "lead", "source": "default"})
    if re.search(r"男主|他|乘客|对方", raw or ""):
        if "partner" not in {c["id"] for c in found}:
            found.append({"id": "partner", "name": "男主", "role": "lead", "source": "default"})

    if not found:
        found = [
            {"id": "hero", "name": "主角", "role": "lead", "source": "default"},
        ]
    return found[:8]


def _location_candidates(raw: str) -> list[dict[str, Any]]:
    locs: list[dict[str, Any]] = []
    patterns = [
        (r"雨夜|出租车|后座|车内", "cab_rain", "雨夜出租车内"),
        (r"卧室|床上|房间", "bedroom", "室内卧室"),
        (r"酒吧|夜店", "bar", "酒吧"),
        (r"街道|巷|路边", "street", "街道"),
        (r"办公室|工位", "office", "办公室"),
        (r"学校|教室", "school", "学校"),
        (r"咖啡", "cafe", "咖啡馆"),
    ]
    for pat, lid, desc in patterns:
        if re.search(pat, raw or ""):
            locs.append({"id": lid, "description": desc, "source": "extract"})
    if not locs:
        locs.append({"id": "loc_main", "description": "主场景（待定）", "source": "default"})
    return locs[:6]


def _dialogue_blocks(raw: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for i, m in enumerate(_DIALOGUE.finditer(raw or ""), start=1):
        blocks.append(
            {
                "id": f"dlg_{i:02d}",
                "speaker": m.group(1).strip(),
                "text": m.group(2).strip()[:120],
            }
        )
    return blocks[:40]


def _scene_chunks(raw: str) -> list[dict[str, str]]:
    """Split source into scene-sized text chunks."""
    text = (raw or "").strip()
    if not text:
        return [{"title": "main", "body": ""}]

    # Explicit scene headers
    matches = list(_SCENE_HDR.finditer(text))
    if matches:
        chunks: list[dict[str, str]] = []
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            title = m.group(1).strip()[:40] if m.lastindex else f"Scene {i+1}"
            chunks.append({"title": title or f"Scene {i+1}", "body": body or title})
        if chunks:
            return chunks

    paras = _split_paragraphs(text)
    if len(paras) == 1:
        # one-liner or single block → one scene
        return [{"title": "Main", "body": paras[0]}]
    if len(paras) <= 4:
        return [{"title": f"S{i+1}", "body": p} for i, p in enumerate(paras)]
    # merge into ~3 scenes
    n = 3
    size = max(1, (len(paras) + n - 1) // n)
    chunks = []
    for i in range(0, len(paras), size):
        group = paras[i : i + size]
        chunks.append({"title": f"S{len(chunks)+1}", "body": "\n\n".join(group)})
    return chunks[:6]


def normalize_story(
    raw: str,
    *,
    title_hint: str | None = None,
    source_path: str | None = None,
) -> dict[str, Any]:
    """story.normalize — structured story package (no LLM)."""
    raw = (raw or "").strip()
    title = _extract_title(raw, title_hint)
    chars = _character_candidates(raw)
    locs = _location_candidates(raw)
    dialogues = _dialogue_blocks(raw)
    chunks = _scene_chunks(raw)
    logline = _clip_nar(raw.replace("\n", " "), 80)
    if len(raw) > 80:
        # prefer first sentence
        first = re.split(r"[。！？\n]", raw)[0].strip()
        if first:
            logline = _clip_nar(first, 80)

    warnings: list[str] = []
    if len(raw) < 8:
        warnings.append("source very short — planner will use vertical beat template")
    if not dialogues:
        warnings.append("no dialogue lines detected — default storyteller VO")

    return {
        "schema_version": 1,
        "kind": "normalized-story",
        "at": utc_now(),
        "title": title,
        "logline": logline,
        "raw_excerpt": raw[:2000],
        "source_path": source_path,
        "source_chars": len(raw),
        "character_candidates": chars,
        "location_candidates": locs,
        "dialogue_blocks": dialogues,
        "scene_chunks": chunks,
        "vo_mode_suggest": "character" if dialogues else "storyteller",
        "warnings": warnings,
        "source_map": {
            "method": "deterministic_v1",
            "note": "Agent may refine; this is structure-only normalize",
        },
    }


def _draft_story_contract(normalized: dict[str, Any]) -> dict[str, Any]:
    """Create an honest story contract; unknown intent stays blank/draft."""
    logline = str(normalized.get("logline") or "")
    return {
        "premise": logline,
        "logline": logline,
        "theme": "",
        "protagonist_ids": [
            str(c.get("id"))
            for c in (normalized.get("character_candidates") or [])
            if isinstance(c, dict) and c.get("id")
        ][:2],
        "protagonist_goal": "",
        "opposition": "",
        "stakes": "",
        "climax_choice": "",
        "ending_hook": "",
        "emotional_arc": [],
        "pace_chart": [],
        "constraints": [],
        "status": "needs_authoring",
    }


def structure_episode(
    normalized: dict[str, Any],
    *,
    target_duration: float = 45.0,
    episode_number: int = 1,
) -> dict[str, Any]:
    """episode.structure — single vertical short episode."""
    target_duration = max(12.0, min(180.0, float(target_duration or 45)))
    title = str(normalized.get("title") or "ep")
    logline = str(normalized.get("logline") or "")
    return {
        "id": f"ep{episode_number:02d}",
        "episodeNumber": episode_number,
        "title": title,
        "targetDuration": target_duration,
        "openingHook": logline,
        "centralConflict": "",
        "climax": "",
        "endingHook": "",
        "aspectRatio": "9:16",
        "status": "planning",
        "vo_mode": normalized.get("vo_mode_suggest") or "storyteller",
    }


def _sentences(body: str) -> list[str]:
    body = (body or "").strip()
    if not body:
        return []
    parts = re.split(r"(?<=[。！？!?])\s*|\n+", body)
    return [p.strip() for p in parts if p.strip()]


def segment_scenes(
    normalized: dict[str, Any],
    episode: dict[str, Any],
) -> list[dict[str, Any]]:
    """scene.segment"""
    chunks = normalized.get("scene_chunks") or [{"title": "Main", "body": normalized.get("raw_excerpt") or ""}]
    locs = normalized.get("location_candidates") or []
    loc_id = locs[0]["id"] if locs else None
    char_ids = [c["id"] for c in (normalized.get("character_candidates") or []) if c.get("id")]

    scenes: list[dict[str, Any]] = []
    for i, ch in enumerate(chunks, start=1):
        if not isinstance(ch, dict):
            continue
        body = str(ch.get("body") or "")
        scenes.append(
            {
                "id": f"sc{i:02d}_{_slug(str(ch.get('title') or f's{i}'), f'sc{i}')}",
                "order": i,
                "title": str(ch.get("title") or f"Scene {i}")[:60],
                "synopsis": _clip_nar(body, 100),
                "body": body,
                "locationId": loc_id,
                "characterIds": char_ids[:4],
                "dramaticPurpose": "advance story",
                "purpose": "",
                "conflict": "",
                "entry_state": "",
                "exit_state": "",
                "emotionalStart": "",
                "emotionalEnd": "",
                "productionMode": "hybrid",
                "status": "planned",
                "targetDuration": None,  # filled after beats
            }
        )
    if not scenes:
        scenes.append(
            {
                "id": "sc01_main",
                "order": 1,
                "title": "Main",
                "synopsis": str(episode.get("openingHook") or ""),
                "body": str(normalized.get("raw_excerpt") or ""),
                "locationId": loc_id,
                "characterIds": char_ids[:4],
                "productionMode": "hybrid",
                "status": "planned",
            }
        )
    return scenes


def extract_beats(
    scene: dict[str, Any],
    *,
    scene_budget_sec: float,
    is_only_scene: bool,
) -> list[dict[str, Any]]:
    """beat.extract — map scene body onto vertical beat spine."""
    body = str(scene.get("body") or scene.get("synopsis") or "")
    sents = _sentences(body)
    spine = list(DEFAULT_BEAT_SPINE)
    # short scene: fewer beats
    if not is_only_scene and len(sents) <= 2:
        spine = [spine[0], spine[2], spine[3], spine[4]]
    elif len(sents) == 1 and is_only_scene:
        spine = list(DEFAULT_BEAT_SPINE)  # full spine even for one-liner

    # distribute sentences across beats
    if not sents:
        sents = [str(scene.get("synopsis") or scene.get("title") or "画面推进")]

    beats: list[dict[str, Any]] = []
    n = len(spine)
    for bi, sp in enumerate(spine):
        # assign sentence slice
        if n == 1:
            chunk_sents = sents
        else:
            start = int(round(bi * len(sents) / n))
            end = int(round((bi + 1) * len(sents) / n))
            chunk_sents = sents[start:end] or [sents[min(bi, len(sents) - 1)]]
        action_text = " ".join(chunk_sents)
        dur = max(2.0, round(float(scene_budget_sec) * float(sp["weight"]), 1))
        beat_id = f"{scene['id']}_bt{bi+1:02d}_{sp['key']}"
        beats.append(
            {
                "id": beat_id,
                "order": bi + 1,
                "key": sp["key"],
                "objective": sp["objective"],
                "action": _clip_nar(action_text, 120),
                "outcome": "",
                "emotionalShift": {"from": "", "to": ""},
                "importance": sp["importance"],
                "dramatic_function": sp["dramatic_function"],
                "targetDuration": dur,
                "shots_n": int(sp["shots_n"]),
                "source_text": action_text,
            }
        )
    return beats


def _vertical_composition(order: int, df: str) -> str:
    if df in {"hook", "action"}:
        return "center-subject"
    if df == "sensory":
        return "three-layer-depth" if order % 2 == 0 else "foreground-background"
    if df == "approach":
        return "two-character-stack" if order % 2 == 0 else "center-subject"
    return "center-subject"


def _camera_axis(df: str, idx: int) -> str:
    axes = {
        "hook": "dolly_in",
        "approach": "pan_with",
        "sensory": "low_lean",
        "reaction": "ecu_hold",
        "action": "dolly_in",
        "afterglow": "pull_back",
        "bridge": "locked",
    }
    base = axes.get(df, "dolly_in")
    if idx % 3 == 1 and base == "dolly_in":
        return "ecu_hold"
    return base


def _production_mode(df: str, shot_role: str) -> str:
    if shot_role == "env":
        return "text-to-video"
    if df in {"bridge", "afterglow"}:
        return "panel-animation"
    if df in {"action", "sensory", "hook"}:
        return "single-keyframe-i2v"
    return "single-keyframe-i2v"


def plan_shots(
    beat: dict[str, Any],
    *,
    scene: dict[str, Any],
    shot_counter_start: int,
    character_ids: list[str],
    location_id: str | None,
    chain_continue: bool = True,
) -> list[dict[str, Any]]:
    """shot.plan — expand beat into 1–N vertical shots."""
    n = max(1, min(3, int(beat.get("shots_n") or 1)))
    budget = float(beat.get("targetDuration") or 6)
    per_floor = max(3.0, round(budget / n, 1))
    df = str(beat.get("dramatic_function") or "action")
    if df not in DRAMATIC_FUNCS:
        df = "action"
    source = str(beat.get("source_text") or beat.get("action") or "")
    sents = _sentences(source) or [source]

    shots: list[dict[str, Any]] = []
    coverage_roles = ["establish", "reveal", "reaction", "action", "consequence"]
    for i in range(n):
        idx = shot_counter_start + i
        scene_order = int(scene.get("order") or 1)
        beat_order = int(beat.get("order") or 1)
        sid = f"ep01_sc{scene_order:02d}_bt{beat_order:02d}_sh{i + 1:02d}"
        piece = sents[i] if i < len(sents) else sents[-1]
        # Prefer snappy ≤28 so write-spec vo_pacing passes on short plates
        nar = _clip_nar(piece, 28)
        per = _duration_for_nar(nar, floor=per_floor)
        # second shot in beat: reaction / insert flavor
        local_df = df
        if n > 1 and i == n - 1 and df in {"sensory", "action"}:
            local_df = "reaction"
        shot_role = "hero"
        if local_df == "bridge":
            shot_role = "env"
        chain = "continue" if chain_continue and idx > 1 else ("continue" if idx > 1 else "cut")
        if i == 0 and idx == 1:
            chain = "cut"
        panel_id = f"panel_{sid}_01"
        prod = _production_mode(local_df, shot_role)
        vc = _vertical_composition(idx, local_df)
        axis = _camera_axis(local_df, idx)
        coverage_role = coverage_roles[i % len(coverage_roles)]
        must_show = f"{coverage_role}: {_clip_nar(piece, 60)}"
        visible_change = {
            "establish": "空间与人物关系可读",
            "reveal": "新线索或欲望被看见",
            "reaction": "角色反应发生变化",
            "action": "冲突动作完成一步",
            "consequence": "动作造成的状态后果",
        }[coverage_role]
        char_ids = list(character_ids[:2]) or ["hero"]
        shots.append(
            {
                "id": sid,
                "order": idx,
                "filmSpecShotId": sid,
                "beatId": beat["id"],
                "beat_id": beat["id"],
                "narrativePurpose": str(beat.get("objective") or local_df),
                "dramaticFunction": local_df,
                "shotSize": "close-up" if local_df in {"hook", "reaction", "action"} else "medium",
                "verticalComposition": vc,
                "cameraMovement": axis,
                "productionMode": prod,
                "targetDuration": per,
                "characterIds": char_ids,
                "locationId": location_id,
                "wardrobeState": "full",
                "heatPhase": "",
                "chainMode": chain,
                "coverage_role": coverage_role,
                "must_show": must_show,
                "visible_change": visible_change,
                "start_state": "",
                "end_state": "",
                "source_refs": [beat.get("id")],
                "nar": nar,
                "panelIds": [panel_id],
                "keyframeIds": [],
                "motionClipIds": [],
                "dialogueLineIds": [f"dlg_{sid}"],
                "panels": [
                    {
                        "id": panel_id,
                        "order": 1,
                        "subject": char_ids[0] if char_ids else "hero",
                        "action": must_show,
                        "expression": "",
                        "location": location_id or "",
                        "verticalComposition": vc,
                        "cameraAngle": "eye_level",
                        "lighting": "",
                        "style": "vertical drama comic",
                        "continuityConstraints": [f"chain_mode={chain}"],
                        "negativeConstraints": [
                            "no landscape crop",
                            "no horizontal storyboard paste",
                        ],
                        "referenceAssetIds": [],
                        "sourcePromptPath": None,
                        "must_include": [must_show],
                    }
                ],
                "assetHints": {
                    "keyframePath": None,
                    "clipPath": None,
                    "promptPath": None,
                    "hasKeyframe": False,
                    "hasClip": False,
                    "hasPrompt": False,
                },
                # film-spec projection helpers
                "_film": {
                    "title": _clip_nar(str(beat.get("objective") or sid), 24),
                    "shot_role": shot_role,
                    "dramatic_function": local_df,
                    "duration_sec": per,
                    "nar": nar,
                    "beat_id": beat["id"],
                    "dsl": {
                        "subject": f"vertical 9:16, {char_ids[0] if char_ids else 'hero'}",
                        "action": must_show,
                        "motion": axis.replace("_", " "),
                        "camera_axis": axis,
                        "visible_change": visible_change,
                        "story_beat": str(beat.get("objective") or local_df),
                        "start_pose": "enter beat",
                        "end_pose": "exit beat — feeds next",
                        "chain_mode": chain,
                        "cut_on": "mid_motion" if chain == "continue" else "fresh",
                        "cast": char_ids,
                        "viewpoint": "objective",
                        "look_axis": "center",
                        "camera": {
                            "shot_size": "close-up"
                            if local_df in {"hook", "reaction", "action"}
                            else "medium",
                            "angle": "eye_level",
                        },
                    },
                },
            }
        )
    return shots


def build_planned_graph(
    normalized: dict[str, Any],
    *,
    target_duration: float = 45.0,
    root: Path | None = None,
) -> dict[str, Any]:
    """Full plan: normalize → episode → scenes → beats → shots → graph."""
    episode = structure_episode(normalized, target_duration=target_duration)
    scenes = segment_scenes(normalized, episode)
    total = float(episode["targetDuration"])
    # weight scenes equally (or by body length)
    weights = []
    for sc in scenes:
        w = max(1, len(str(sc.get("body") or "")))
        weights.append(w)
    wsum = sum(weights) or 1
    char_ids = [c["id"] for c in (normalized.get("character_candidates") or []) if c.get("id")]
    if not char_ids:
        char_ids = ["hero"]

    shot_i = 1
    scenes_out: list[dict[str, Any]] = []
    for si, sc in enumerate(scenes):
        budget = total * (weights[si] / wsum)
        sc["targetDuration"] = round(budget, 1)
        beats = extract_beats(sc, scene_budget_sec=budget, is_only_scene=len(scenes) == 1)
        beats_out: list[dict[str, Any]] = []
        for bt in beats:
            shots = plan_shots(
                bt,
                scene=sc,
                shot_counter_start=shot_i,
                character_ids=char_ids,
                location_id=sc.get("locationId"),
                chain_continue=True,
            )
            shot_i += len(shots)
            bt_out = {
                "id": bt["id"],
                "order": bt["order"],
                "objective": bt["objective"],
                "action": bt["action"],
                "outcome": bt.get("outcome") or "",
                "emotionalShift": bt.get("emotionalShift") or {"from": "", "to": ""},
                "importance": bt["importance"],
                "targetDuration": bt["targetDuration"],
                "director_board": draft_director_board(),
                "shots": shots,
            }
            beats_out.append(bt_out)
        sc_out = {
            "id": sc["id"],
            "order": sc["order"],
            "title": sc["title"],
            "synopsis": sc.get("synopsis") or "",
            "locationId": sc.get("locationId"),
            "characterIds": sc.get("characterIds") or char_ids,
            "targetDuration": sc.get("targetDuration"),
            "productionMode": sc.get("productionMode") or "hybrid",
            "status": "planned",
            "beats": beats_out,
        }
        scenes_out.append(sc_out)

    episode_out = {
        **episode,
        "scenes": scenes_out,
        "status": "planning",
    }

    characters = []
    for c in normalized.get("character_candidates") or []:
        if not isinstance(c, dict):
            continue
        characters.append(
            {
                "id": c.get("id"),
                "identity": c.get("name") or c.get("id"),
                "defaultWardrobe": "",
                "castMaster": None,
            }
        )
    locations = [
        {"id": x.get("id"), "description": x.get("description") or ""}
        for x in (normalized.get("location_candidates") or [])
        if isinstance(x, dict)
    ]

    root_s = str(root) if root else ""
    graph = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "kind": "vertical-drama-graph",
        "derived_from": {
            "film_spec": None,
            "style_bible": None,
            "at": utc_now(),
            "mode": "planned",
            "planner": "story_plan.v2",
            "normalized_title": normalized.get("title"),
        },
        "project": {
            "id": _slug(str(normalized.get("title") or "project"), "project"),
            "title": str(normalized.get("title") or "untitled"),
            "aspectRatio": "9:16",
            "targetResolution": "1080x1920",
            "targetFps": 30,
            "root": root_s,
        },
        "episodes": [episode_out],
        "story": _draft_story_contract(normalized),
        "characters": characters,
        "locations": locations,
        "props": [],
        "warnings": list(normalized.get("warnings") or []),
    }
    ensure_graph_controls(graph)
    graph["content_sha256"] = graph_content_sha256(graph)
    return graph


def stabilize_shot_ids(new_graph: dict[str, Any], previous_graph: dict[str, Any] | None) -> dict[str, Any]:
    """Reuse prior shot ids by semantic slot, not by array position."""
    if not isinstance(previous_graph, dict):
        return new_graph
    old_slots: dict[tuple[str, str], str] = {}
    for ep in previous_graph.get("episodes") or []:
        for sc in (ep.get("scenes") or []) if isinstance(ep, dict) else []:
            for bt in (sc.get("beats") or []) if isinstance(sc, dict) else []:
                if not isinstance(bt, dict):
                    continue
                bid = str(bt.get("id") or "")
                for sh in bt.get("shots") or []:
                    if not isinstance(sh, dict):
                        continue
                    sid = str(sh.get("id") or "")
                    role = str(sh.get("coverage_role") or "")
                    if bid and sid and role:
                        old_slots[(bid, role)] = sid

    used: set[str] = set()
    for ep in new_graph.get("episodes") or []:
        for sc in (ep.get("scenes") or []) if isinstance(ep, dict) else []:
            for bt in (sc.get("beats") or []) if isinstance(sc, dict) else []:
                if not isinstance(bt, dict):
                    continue
                bid = str(bt.get("id") or "")
                for sh in bt.get("shots") or []:
                    if not isinstance(sh, dict):
                        continue
                    old_id = old_slots.get((bid, str(sh.get("coverage_role") or "")))
                    sid = old_id if old_id and old_id not in used else str(sh.get("id") or "")
                    used.add(sid)
                    old_sid = str(sh.get("id") or "")
                    if sid != old_sid:
                        sh["id"] = sid
                        sh["filmSpecShotId"] = sid
                        sh["panelIds"] = [str(x).replace(old_sid, sid) for x in (sh.get("panelIds") or [])]
                        for panel in sh.get("panels") or []:
                            if isinstance(panel, dict):
                                panel["id"] = str(panel.get("id") or "").replace(old_sid, sid)
                    for panel in sh.get("panels") or []:
                        if isinstance(panel, dict):
                            panel["sourcePromptPath"] = None
    return new_graph


def project_graph_to_film_spec(
    graph: dict[str, Any],
    *,
    base_spec: dict[str, Any] | None = None,
    normalized: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project planned graph → film-spec scenes/shots (executable)."""
    base = dict(base_spec or {})
    ep = (graph.get("episodes") or [{}])[0]
    if not isinstance(ep, dict):
        ep = {}
    title = str(
        graph.get("project", {}).get("title")
        or ep.get("title")
        or base.get("title")
        or "untitled"
    )
    logline = str(ep.get("openingHook") or (normalized or {}).get("logline") or title)
    vo_mode = str(
        (normalized or {}).get("vo_mode_suggest")
        or base.get("vo_mode")
        or "storyteller"
    )
    if vo_mode not in {"storyteller", "character", "hybrid"}:
        vo_mode = "storyteller"

    cast_ids = [c.get("id") for c in (graph.get("characters") or []) if isinstance(c, dict) and c.get("id")]
    if not cast_ids:
        cast_ids = ["hero"]

    scenes_fs: list[dict[str, Any]] = []
    for sc in ep.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        shots_fs: list[dict[str, Any]] = []
        for bt in sc.get("beats") or []:
            if not isinstance(bt, dict):
                continue
            for sh in bt.get("shots") or []:
                if not isinstance(sh, dict):
                    continue
                film = sh.get("_film") if isinstance(sh.get("_film"), dict) else {}
                dsl = film.get("dsl") if isinstance(film.get("dsl"), dict) else {}
                if not dsl:
                    dsl = {
                        "subject": "vertical 9:16 subject",
                        "action": sh.get("nar") or "",
                        "motion": sh.get("cameraMovement") or "dolly_in",
                        "camera_axis": sh.get("cameraMovement") or "dolly_in",
                        "visible_change": sh.get("nar") or "",
                        "story_beat": sh.get("narrativePurpose") or "",
                        "chain_mode": sh.get("chainMode") or "continue",
                        "cast": sh.get("characterIds") or cast_ids[:1],
                    }
                shot_obj = {
                    "id": sh.get("id") or sh.get("filmSpecShotId"),
                    "title": film.get("title") or sh.get("narrativePurpose") or sh.get("id"),
                    "shot_role": film.get("shot_role") or "hero",
                    "dramatic_function": film.get("dramatic_function")
                    or sh.get("dramaticFunction")
                    or "action",
                    "duration_sec": float(
                        film.get("duration_sec") or sh.get("targetDuration") or 5
                    ),
                    "nar": film.get("nar") or sh.get("nar") or "……",
                    "beat_id": film.get("beat_id") or sh.get("beatId"),
                    "coverage_role": sh.get("coverage_role") or "",
                    "must_show": sh.get("must_show") or "",
                    "visible_change": sh.get("visible_change") or "",
                    "start_state": sh.get("start_state") or "",
                    "end_state": sh.get("end_state") or "",
                    "source_refs": list(sh.get("source_refs") or []),
                    "production_mode": sh.get("productionMode"),
                    "vertical_composition": sh.get("verticalComposition"),
                    "lipsync": False,
                    "dsl": dsl,
                }
                shots_fs.append(shot_obj)
        scenes_fs.append(
            {
                "title": sc.get("title") or "Scene",
                "summary": sc.get("synopsis") or "",
                "shots": shots_fs,
            }
        )

    story = graph.get("story") if isinstance(graph.get("story"), dict) else {}
    emotional = [str(x) for x in (story.get("emotional_arc") or []) if str(x).strip()]
    if len(emotional) < 3:
        emotional = [
            str(ep.get("openingHook") or ""),
            str(ep.get("climax") or ""),
            str(ep.get("endingHook") or ""),
        ]

    base_di = (
        base.get("director_intent")
        if isinstance(base.get("director_intent"), dict)
        else {}
    )
    logline_full = logline if len(logline) >= 8 else (logline + " ——竖屏漫剧。")
    taboos = base_di.get("taboos") if isinstance(base_di.get("taboos"), list) else None
    if not taboos:
        taboos = ["横屏分镜硬裁", "无钩子开场"]

    spec: dict[str, Any] = {
        **base,
        "title": title,
        "description": logline,
        "aspect_ratio": "9:16",
        "vo_mode": vo_mode,
        "tts_backend": base.get("tts_backend") or "edge",
        "i2v_provider": base.get("i2v_provider") or "grok",
        "caption_mode": base.get("caption_mode") or "zh",
        "director_intent": {
            **base_di,
            "premise": story.get("premise") or base_di.get("premise") or "",
            "logline": logline_full,
            "tone": base_di.get("tone") or story.get("theme") or "竖屏漫剧",
            "emotional_arc": emotional,
            "theme": base_di.get("theme") or story.get("theme") or "",
            "audience": base_di.get("audience") or "竖屏短视频",
            "cast": cast_ids,
            "taboos": taboos,
            "protagonist_goal": story.get("protagonist_goal") or "",
            "opposition": story.get("opposition") or "",
            "stakes": story.get("stakes") or "",
            "climax_choice": story.get("climax_choice") or "",
            "ending_hook": story.get("ending_hook") or "",
        },
        "scenes": scenes_fs,
        "_plan": {
            "source": "story_plan.v1",
            "at": utc_now(),
            "episode_id": ep.get("id"),
            "target_duration": ep.get("targetDuration"),
            "graph_mode": (graph.get("derived_from") or {}).get("mode"),
        },
        "_projection": {
            "source": "drama-graph.json",
            "source_revision": int(graph.get("revision") or 1),
            "source_sha256": graph_content_sha256(graph),
            "generated_at": utc_now(),
            "state": graph.get("state") or "draft",
        },
    }
    return spec


def seed_style_bible_from_normalized(
    root: Path,
    normalized: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Light-touch character/location seed into style-bible (never unlock Approved)."""
    root = Path(root)
    path = root / "style-bible.json"
    bible = read_json(path) or {"schema_version": 2, "locked": False}
    if bible.get("locked") or str(bible.get("state") or "").lower() == "approved":
        if not force:
            return {"ok": True, "skipped": True, "reason": "bible locked"}
    chars = bible.get("characters") if isinstance(bible.get("characters"), dict) else {}
    for c in normalized.get("character_candidates") or []:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        cid = str(c["id"])
        if cid in chars and not force:
            continue
        chars[cid] = {
            "identity": str(c.get("name") or cid),
            "default_wardrobe": "",
            "cast_master": chars.get(cid, {}).get("cast_master")
            if isinstance(chars.get(cid), dict)
            else None,
        }
    bible["characters"] = chars
    locs = bible.get("locations") if isinstance(bible.get("locations"), dict) else {}
    for loc in normalized.get("location_candidates") or []:
        if not isinstance(loc, dict) or not loc.get("id"):
            continue
        lid = str(loc["id"])
        if lid not in locs or force:
            locs[lid] = str(loc.get("description") or lid)
    bible["locations"] = locs
    if not bible.get("title"):
        bible["title"] = normalized.get("title")
    bible["schema_version"] = bible.get("schema_version") or 2
    bible["updated_at"] = utc_now()
    write_json(path, bible)
    return {"ok": True, "skipped": False, "characters": list(chars.keys()), "locations": list(locs.keys())}


def _ensure_film_root_skeleton(root: Path, *, title: str, theme: str) -> None:
    """Create dirs + minimal manifest so write-spec works without prior init."""
    for sub in (
        "receipts",
        "prompts",
        "keyframes",
        "clips",
        "canonical/cast",
        "canonical/lookbook",
        "selects",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)
    man_path = root / "manifest.json"
    if not man_path.is_file():
        write_json(
            man_path,
            {
                "schema_version": 1,
                "provider_default": "grok-imagine",
                "title": title,
                "theme": theme,
                "aspect_ratio": "9:16",
                "width": 720,
                "height": 1280,
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "style_locked": False,
                "stills": {},
                "clips": {},
                "gates": {
                    "brief": True,
                    "style": False,
                    "spec": False,
                    "stills": False,
                    "motion": False,
                    "assembly": False,
                    "final": False,
                },
                "outputs": {},
                "notes": ["Created by aifilm plan run (Phase 3)"],
            },
        )


def run_plan(
    root: Path,
    raw: str,
    *,
    title: str | None = None,
    target_duration: float = 45.0,
    apply_film_spec: bool = True,
    force: bool = False,
    source_path: str | None = None,
    seed_bible: bool = True,
) -> dict[str, Any]:
    """End-to-end Phase 3 planner for a film root."""
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    normalized = normalize_story(raw, title_hint=title, source_path=source_path)
    _ensure_film_root_skeleton(
        root,
        title=str(normalized.get("title") or "untitled"),
        theme=str(normalized.get("logline") or "")[:200],
    )
    write_json(root / "receipts" / "story-normalize.json", normalized)

    previous_graph = read_json(root / "drama-graph.json") or None
    graph = build_planned_graph(normalized, target_duration=target_duration, root=root)
    graph = stabilize_shot_ids(graph, previous_graph)
    if root:
        graph["project"]["root"] = str(root)

    from drama_graph import GRAPH_NAME, validate_graph

    write_json(root / GRAPH_NAME, graph)
    v = validate_graph(graph)
    narrative = validate_narrative_graph(graph)
    write_json(
        root / "receipts" / "drama-graph-plan.json",
        {
            "ok": bool(v.get("ok")),
            "at": utc_now(),
            "mode": "planned",
            "shot_count": v.get("shot_count"),
            "errors": v.get("errors"),
            "warnings": (graph.get("warnings") or []) + (v.get("warnings") or []),
            "narrative": narrative,
            "state": graph.get("state"),
            "content_sha256": graph.get("content_sha256"),
        },
    )

    bible_report = None
    if seed_bible:
        bible_report = seed_style_bible_from_normalized(root, normalized, force=force)

    assets_report: dict[str, Any] | None = None

    spec_report: dict[str, Any] | None = None
    if not apply_film_spec:
        existing = read_json(root / "film-spec.json") or {}
        has_existing_shots = any(
            isinstance(sc, dict) and sc.get("shots")
            for sc in (existing.get("scenes") or [])
        )
        if has_existing_shots:
            spec_report = {
                "ok": True,
                "skipped": True,
                "reason": "draft-only run preserved existing film-spec; pass --apply-film-spec --force to overwrite",
            }
    if apply_film_spec:
        existing = read_json(root / "film-spec.json") or {}
        has_shots = False
        for sc in existing.get("scenes") or []:
            if isinstance(sc, dict) and sc.get("shots"):
                has_shots = True
                break
        if has_shots and not force:
            spec_report = {
                "ok": False,
                "skipped": True,
                "reason": "film-spec already has shots; pass --force to overwrite plan projection",
            }
        else:
            spec = project_graph_to_film_spec(graph, base_spec=existing, normalized=normalized)
            write_json(root / "film-spec.json", spec)
            # seed timeline
            shots_flat = []
            for sc in spec.get("scenes") or []:
                for sh in (sc.get("shots") or []):
                    if isinstance(sh, dict) and sh.get("id"):
                        shots_flat.append(sh)
            timeline = {
                "schema_version": 1,
                "fps": 30,
                "width": 720,
                "height": 1280,
                "shots": [
                    {
                        "id": s["id"],
                        "duration_sec": float(s.get("duration_sec") or 5),
                        "title": s.get("title") or s["id"],
                    }
                    for s in shots_flat
                ],
            }
            write_json(root / "timeline.json", timeline)
            # brief
            brief = read_json(root / "brief.json") or {}
            brief.update(
                {
                    "title": spec.get("title"),
                    "theme": (normalized.get("logline") or "")[:200],
                    "aspect_ratio": "9:16",
                    "planned_at": utc_now(),
                    "plan_source": "story_plan.v1",
                }
            )
            write_json(root / "brief.json", brief)
            spec_report = {
                "ok": True,
                "draft": True,
                "ready_for_media": bool(narrative.get("ok")) and all(
                    scope in (graph.get("lock_scopes") or [])
                    for scope in ("story", "beats", "shots", "panels")
                ),
                "shot_count": len(shots_flat),
                "scene_count": len(spec.get("scenes") or []),
                "path": str(root / "film-spec.json"),
                "note": "Run aifilm write-spec --root to validate + inject prompts",
            }

    # Phase 4: structure assets + CharacterState timeline after film-spec exists
    if apply_film_spec and (spec_report or {}).get("ok"):
        try:
            from asset_registry import sync_assets

            assets_report = sync_assets(root, write=True, force=force, update_graph=True)
        except Exception as exc:  # noqa: BLE001
            assets_report = {"ok": False, "error": str(exc)[:200]}

    # count tree
    from drama_graph import graph_status

    # Asset sync may add non-creative graph metadata; refresh the canonical
    # hash and bind the draft projection to the final graph snapshot.
    latest_graph = read_json(root / GRAPH_NAME) or graph
    ensure_graph_controls(latest_graph)
    write_json(root / GRAPH_NAME, latest_graph)
    if (root / "film-spec.json").is_file():
        latest_spec = read_json(root / "film-spec.json") or {}
        projection = latest_spec.get("_projection") if isinstance(latest_spec.get("_projection"), dict) else {}
        projection.update({
            "source": GRAPH_NAME,
            "source_revision": latest_graph.get("revision"),
            "source_sha256": graph_content_sha256(latest_graph),
            "generated_at": utc_now(),
            "state": latest_graph.get("state") or "draft",
        })
        latest_spec["_projection"] = projection
        write_json(root / "film-spec.json", latest_spec)
    st = graph_status(root, auto_derive=False)

    write_json(
        root / "receipts" / "plan.json",
        {
            "ok": bool(v.get("ok")),
            "at": utc_now(),
            "title": normalized.get("title"),
            "target_duration": target_duration,
            "validate": v,
            "narrative": narrative,
            "film_spec": spec_report,
            "bible": bible_report,
            "assets": assets_report,
            "graph_line": st.get("line"),
        },
    )

    return {
        "ok": bool(v.get("ok")),
        "draft": True,
        "ready_for_projection": bool(narrative.get("ok")) and all(
            scope in (latest_graph.get("lock_scopes") or [])
            for scope in ("story", "beats", "shots", "panels")
        ),
        "root": str(root),
        "title": normalized.get("title"),
        "logline": normalized.get("logline"),
        "normalized_path": str(root / "receipts" / "story-normalize.json"),
        "graph_path": str(root / GRAPH_NAME),
        "validate": v,
        "narrative": narrative,
        "counts": st.get("counts"),
        "line": st.get("line"),
        "film_spec": spec_report,
        "bible": bible_report,
        "assets": assets_report,
        "warnings": (normalized.get("warnings") or []) + (v.get("warnings") or []),
        "next": [
            f'aifilm write-spec --root "{root}"',
            f'aifilm assets check --root "{root}"',
            f'aifilm graph status --root "{root}" --with-jobs',
            f'aifilm dispatch --root "{root}"',
        ],
    }


def plan_status(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    norm = read_json(root / "receipts" / "story-normalize.json")
    plan = read_json(root / "receipts" / "plan.json")
    from drama_graph import graph_status

    st = graph_status(root, auto_derive=False)
    from narrative_control import control_status
    return {
        "ok": True,
        "root": str(root),
        "has_normalize": bool(norm),
        "has_plan_receipt": bool(plan),
        "title": (norm or {}).get("title") or (plan or {}).get("title"),
        "graph": st,
        "control": control_status(root),
        "plan_receipt": plan,
    }
