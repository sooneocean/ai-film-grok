#!/usr/bin/env python3
"""Cinema-grade camera-move prompt generation (Seedance camera language bridge).

Replaces the fixed-enum rotation in ``story_plan._camera_axis`` with a richer
vocabulary adapted from the Seedance prompt skill (camera language + visual
styles). Produces a structured ``camera_prompt`` field for ``film-spec.json``
shot DSL, consumed by I2V providers (Grok / Seedance) and the prompt injector.

Pure deterministic logic — no external LLM calls, no network. The vocabulary
tables live here so unit tests can assert coverage without reading markdown.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from util import read_json, write_json


class CinemaPromptError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Seedance camera language vocabulary (camera language + visual styles)
# Adapted from songguoxs/seedance-prompt-skill. These are curated term banks,
# not generated prose — the generator below composes them deterministically.
# ---------------------------------------------------------------------------

SHOT_TYPES = {
    "ecu": "大特写（ECU）：仅眼部/唇部/手指局部，情绪密度最高",
    "cu": "特写（CU）：面部占满画幅，呼吸与微表情可见",
    "mcu": "中近景（MCU）：胸部以上，对话与情绪并重",
    "ms": "中景（MS）：腰部以上，人物动作与关系可见",
    "mls": "中远景（MLS）：膝盖以上，人物在环境中",
    "fs": "全景（FS）：全身入画，环境与姿态并重",
    "ws": "远景（WS）：人物渺小，环境主导",
    "ews": "大远景（EWS）：地平线级，史诗感或孤独感",
}

CAMERA_MOVES = {
    "dolly_in": "缓慢推镜（dolly-in），镜头向主体匀速推进，空间压缩感渐增",
    "dolly_out": "缓慢拉镜（dolly-out），从主体退离，揭示环境",
    "pan_with": "跟摇（pan-with-subject），镜头随主体横向移动，不推进",
    "tilt_up": "仰摇（tilt-up），从低处向上升，主体崇高感",
    "tilt_down": "俯摇（tilt-down），从高处向下落，审视或坠落感",
    "tracking": "侧跟（lateral tracking），与主体平行移动，沉浸感",
    "crane_up": "摇臂上升（crane-up），由近及远由低到高，开阔收束",
    "crane_down": "摇臂下降（crane-down），由远及近由高到低，逼近压迫",
    "handheld": "手持微抖（handheld），呼吸感的轻微晃动，临场真实",
    "locked": "固定机位（locked），零位移，画面静止如凝视",
    "ecu_hold": "大特写凝住（ECU hold），推至极限后定格，时间凝固",
    "low_lean": "低位前倾（low-lean），镜头低位微前倾，压迫与窥视",
    "pull_back": "后撤（pull-back），镜头缓慢退离，余韵与疏离",
    "orbit": "环绕（orbit），镜头绕主体弧形运动，立体展示",
    "push_pull_breath": "呼吸式推拉（breath push-pull），极缓的推拉交替，心跳节奏",
}

ANGLES = {
    "eye": "平视（eye-level），与主体视线齐平，中性客观",
    "low": "仰拍（low-angle），镜头低位向上，主体权威与压迫",
    "high": "俯拍（high-angle），镜头高位向下，主体渺小或被审视",
    "dutch": "荷兰角（dutch tilt），画面倾斜，失衡与不安",
    "overhead": "顶俯（overhead / top-down），上帝视角，构图化与命运感",
    "ots": "过肩（OTS），越过一人肩部看向另一人，关系与对话",
}

PACING = {
    "slow": "运镜缓慢绵长，单镜内节奏沉稳，情绪先行",
    "medium": "运镜中速稳定，推进与情绪同频",
    "fast": "运镜利落带速，镜头有加速度，冲突与紧迫",
    "hold": "近乎静止的凝视，时间感被拉长",
}

FOCUS = {
    "rack": "焦点转换（rack focus），前景→后景或反之，引导视线跳转",
    "deep": "深焦（deep focus），前后景皆清晰，信息密度高",
    "shallow": "浅焦（shallow DOF），主体锐利背景虚化，隔离主体",
    "pull": "失焦→合焦（focus pull），由虚到实，从梦境到现实",
}

TRANSITIONS = {
    "hard": "硬切（hard cut），无转场，时间与空间跳变",
    "match": "匹配剪辑（match cut），动作或构图衔接两镜",
    "fade": "淡入淡出（fade），黑场或白场过渡，段落感",
    "dissolve": "叠化（dissolve），两镜交叠融化，时间流逝",
}

# Visual styles — film grains, color palettes, lighting, animation
VISUAL_STYLES = {
    "film_grain": {
        "fine": "细颗粒胶片质感（fine grain），模拟 35mm 微粒，温暖怀旧",
        "coarse": "粗颗粒（coarse grain），16mm 手持质感，纪实与粗粝",
        "clean": "无颗粒数字质感（clean），锐利通透，现代感",
        "halation": "胶片光晕（halation），高光泛红溢出，复古梦幻",
    },
    "color_palette": {
        "teal_orange": "青橙互补（teal-orange），阴影偏青高光偏暖，好莱坞商业质感",
        "desaturated": "低饱和（desaturated），色彩克制，冷峻写实",
        "warm_amber": "暖琥珀（warm amber），整体偏黄褐，怀旧与亲密",
        "cool_steel": "冷钢蓝（cool steel），偏青蓝，疏离与清冷",
        "high_contrast": "高反差（high contrast），黑白场分明，戏剧张力",
        "pastel": "柔和粉彩（pastel），低对比柔色，梦幻与少女感",
    },
    "lighting": {
        "rembrandt": "伦勃朗光（Rembrandt），单侧三角光斑，立体与古典",
        "backlight": "逆光（backlight），轮廓发光，主体与背景分离",
        "practical": "现场光（practical），环境光源可见，真实生活感",
        "low_key": "低调光（low-key），大面积暗部，神秘与压抑",
        "high_key": "高调光（high-key），均匀明亮，通透与纯净",
        "neon": "霓虹光（neon），饱和色光投射，赛博与夜店",
        "golden_hour": "黄金时刻光（golden hour），日落暖侧光，柔金质感",
        "blue_hour": "蓝调时刻（blue hour），日落后天光偏蓝，静谧忧郁",
    },
}

# Genre → scenario strategy (Seedance scenario prompts)
SCENARIO_STRATEGIES = {
    "short_drama": {
        "label": "短剧",
        "moves": ["dolly_in", "ecu_hold", "low_lean", "pan_with"],
        "lighting": ["low_key", "practical"],
        "palette": ["teal_orange", "high_contrast"],
        "pacing": "fast",
    },
    "ecchi_romance": {
        "label": "成人向情感",
        "moves": ["dolly_in", "push_pull_breath", "ecu_hold", "tracking"],
        "lighting": ["warm_amber", "backlight", "golden_hour"],
        "palette": ["warm_amber", "pastel"],
        "pacing": "slow",
    },
    "ecommerce": {
        "label": "电商广告",
        "moves": ["orbit", "tracking", "crane_up"],
        "lighting": ["high_key", "practical"],
        "palette": ["clean", "pastel"],
        "pacing": "medium",
    },
    "xianxia": {
        "label": "仙侠奇幻",
        "moves": ["crane_up", "orbit", "tracking", "push_pull_breath"],
        "lighting": ["backlight", "golden_hour", "blue_hour"],
        "palette": ["pastel", "cool_steel"],
        "pacing": "slow",
    },
    "science": {
        "label": "科普",
        "moves": ["dolly_in", "tracking", "tilt_down"],
        "lighting": ["high_key", "clean"],
        "palette": ["cool_steel", "desaturated"],
        "pacing": "medium",
    },
    "music_video": {
        "label": "音乐MV",
        "moves": ["handheld", "orbit", "tracking", "dolly_in"],
        "lighting": ["neon", "low_key"],
        "palette": ["high_contrast", "teal_orange"],
        "pacing": "fast",
    },
}

# dramatic_function → camera move mapping (replaces story_plan._camera_axis fixed enum)
DF_CAMERA_MAP = {
    "hook": ("dolly_in", "fast", "shallow"),
    "approach": ("pan_with", "medium", "shallow"),
    "sensory": ("low_lean", "slow", "shallow"),
    "reaction": ("ecu_hold", "hold", "shallow"),
    "action": ("dolly_in", "fast", "deep"),
    "afterglow": ("pull_back", "slow", "shallow"),
    "bridge": ("locked", "medium", "deep"),
}

# heat_phase → intensity modulation
HEAT_INTENSITY = {
    "warmup": ("medium", "warm_amber"),
    "rising": ("slow", "warm_amber"),
    "peak": ("slow", "warm_amber"),
    "climax": ("hold", "high_contrast"),
    "cooldown": ("slow", "cool_steel"),
}


def _pick(values: dict[str, str], key: str, fallback: str = "locked") -> str:
    """Return the vocab entry for *key* or *fallback*."""
    return values.get(key, values[fallback])


def _resolve_camera_move(df: str, idx: int) -> str:
    """Resolve the camera move, mirroring story_plan._camera_axis idx modulation."""
    base, _pacing, _focus = DF_CAMERA_MAP.get(df, ("dolly_in", "medium", "shallow"))
    if idx % 3 == 1 and base == "dolly_in":
        return "ecu_hold"
    return base


def build_camera_prompt(
    *,
    dramatic_function: str = "bridge",
    shot_index: int = 0,
    heat_phase: str | None = None,
    scene_type: str | None = None,
    shot_type: str | None = None,
    angle: str | None = None,
    duration_sec: float = 5.0,
) -> dict[str, Any]:
    """Build a structured cinema-grade camera prompt for one shot.

    Returns a dict with ``camera_axis`` (enum, backward-compatible with
    story_plan), ``camera_prompt`` (rich Chinese prose), and structured
    fields (move / shot_type / angle / pacing / focus / palette / lighting).
    """
    move = _resolve_camera_move(dramatic_function, shot_index)

    # Scenario strategy can override palette/lighting/pacing
    scenario = SCENARIO_STRATEGIES.get(scene_type or "", {})
    heat = HEAT_INTENSITY.get(heat_phase or "")

    pacing = DF_CAMERA_MAP.get(dramatic_function, ("dolly_in", "medium", "shallow"))[1]
    palette_key = "teal_orange"
    lighting_key = "practical"
    focus_key = DF_CAMERA_MAP.get(dramatic_function, ("dolly_in", "medium", "shallow"))[2]

    if scenario:
        if move not in scenario.get("moves", []):
            move = scenario["moves"][0]
        pacing = scenario.get("pacing", pacing)
        palette_key = scenario.get("palette", [palette_key])[0]
        lighting_key = scenario.get("lighting", [lighting_key])[0]

    if heat:
        pacing, palette_key = heat

    # Shot type: default by dramatic function
    if not shot_type:
        shot_type = {
            "hook": "mcu",
            "approach": "ms",
            "sensory": "cu",
            "reaction": "ecu",
            "action": "ms",
            "afterglow": "mls",
            "bridge": "ws",
        }.get(dramatic_function, "ms")

    if not angle:
        angle = {
            "hook": "eye",
            "approach": "ots",
            "sensory": "low",
            "reaction": "eye",
            "action": "low",
            "afterglow": "high",
            "bridge": "eye",
        }.get(dramatic_function, "eye")

    move_text = _pick(CAMERA_MOVES, move)
    shot_text = _pick(SHOT_TYPES, shot_type, "ms")
    angle_text = _pick(ANGLES, angle, "eye")
    pacing_text = _pick(PACING, pacing, "medium")
    focus_text = _pick(FOCUS, focus_key, "shallow")
    palette_text = VISUAL_STYLES["color_palette"].get(palette_key, "")
    lighting_text = VISUAL_STYLES["lighting"].get(lighting_key, "")

    prompt = (
        f"{shot_text}。{angle_text}。{move_text}。"
        f"{pacing_text}。{focus_text}。"
        f"色温/调色：{palette_text}。"
        f"布光：{lighting_text}。"
        f"时长约 {duration_sec:.1f}s。"
    )

    return {
        "camera_axis": move,  # backward-compatible enum
        "camera_move": move,
        "shot_type": shot_type,
        "angle": angle,
        "pacing": pacing,
        "focus": focus_key,
        "palette": palette_key,
        "lighting": lighting_key,
        "camera_prompt": prompt,
        "dramatic_function": dramatic_function,
        "shot_index": shot_index,
        "scene_type": scene_type,
        "heat_phase": heat_phase,
    }


def inject_camera_prompts(root: Path | str) -> dict[str, Any]:
    """Walk film-spec.json shots and write ``dsl.camera_prompt`` to each.

    Idempotent: re-running overwrites with the same deterministic output.
    Does NOT call external LLMs — pure vocabulary composition.
    """
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json")
    if not spec:
        raise CinemaPromptError(f"film-spec.json not found or invalid in {root}")

    scene_type = str(spec.get("genre") or spec.get("scene_type") or "").strip().lower()
    updated = 0
    shot_counter = 0

    for scene in spec.get("scenes") or []:
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            dsl = shot.get("dsl")
            if not isinstance(dsl, dict):
                dsl = {}
            df = str(dsl.get("dramatic_function") or shot.get("dramatic_function") or "bridge")
            heat = shot.get("heat_phase") or scene.get("heat_phase")
            duration = float(shot.get("duration_sec") or 5.0)

            prompt_data = build_camera_prompt(
                dramatic_function=df,
                shot_index=shot_counter,
                heat_phase=heat,
                scene_type=scene_type or None,
                duration_sec=duration,
            )

            dsl["camera_axis"] = prompt_data["camera_axis"]
            dsl["camera_prompt"] = prompt_data["camera_prompt"]
            dsl["camera_move"] = prompt_data["camera_move"]
            dsl["shot_type"] = prompt_data["shot_type"]
            dsl["angle"] = prompt_data["angle"]
            dsl["pacing"] = prompt_data["pacing"]
            dsl["focus"] = prompt_data["focus"]
            dsl["palette"] = prompt_data["palette"]
            dsl["lighting"] = prompt_data["lighting"]
            shot["dsl"] = dsl
            updated += 1
            shot_counter += 1

    write_json(root / "film-spec.json", spec)

    receipt = {
        "schema_version": 1,
        "kind": "cinema-prompt-injection",
        "ok": True,
        "shots_updated": updated,
        "scene_type": scene_type or None,
        "created_at": utc_now(),
        "note": "Pure deterministic vocabulary composition; no external LLM calls.",
    }
    out = root / "receipts" / "cinema-prompt-injection.json"
    write_json(out, receipt)
    receipt["path"] = str(out)
    return receipt
