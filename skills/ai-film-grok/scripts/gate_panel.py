"""Aggregated, UI-friendly view of the pipeline's hard gates.

This module does NOT re-implement gate logic.  It calls the *existing* gate
modules and rule tables (``hard-defaults.md`` values read from ``film-spec``)
and normalises every result into ``{name, code, status, detail, required}`` so
the web console can render one consistent "门禁面板".

Any gate whose module is unavailable, or that cannot be evaluated without a
fully built film, degrades to ``unknown`` / ``skipped`` rather than crashing the
panel — the authoritative fail-closed enforcement still lives in
``review_control`` / the pipeline gates themselves.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from util import read_json

Status = str  #: "pass" | "warn" | "fail" | "unknown" | "skipped"


def _read_spec(root: Path | str) -> dict[str, Any]:
    value = read_json(Path(root) / "film-spec.json")
    return value if isinstance(value, dict) else {}


def _check_adult_scale(root: Path | str) -> tuple[Status, str]:
    spec = _read_spec(root)
    if not spec:
        return ("skipped", "no film-spec.json")
    genre = str(spec.get("genre", "")).lower()
    heat = spec.get("heat_scale")
    adult_iron = spec.get("adult_max_iron", True)
    if genre == "adult" and heat != "max" and adult_iron is not False:
        return ("fail", "成人 genre 必须 heat_scale=max（成人尺度 IRON）")
    sex = spec.get("sex_min_duration_ratio") or spec.get("sex_floor_ratio")
    note = f"heat_scale={heat or 'n/a'}"
    if sex is not None:
        note += f" · sex≥{sex}"
    return ("pass", note)


def _check_zero_narration(root: Path | str) -> tuple[Status, str]:
    spec = _read_spec(root)
    if not spec:
        return ("skipped", "no film-spec.json")
    strict = bool(spec.get("zero_narration_strict", True))
    ratio = float(spec.get("narration_budget_ratio", 0.05) or 0.05)
    if strict and ratio > 0:
        return ("warn", f"zero_narration_strict 但 narration_budget_ratio={ratio}")
    return ("pass", f"zero_narration_strict={strict}")


def _check_voice_lang(root: Path | str) -> tuple[Status, str]:
    spec = _read_spec(root)
    if not spec:
        return ("skipped", "no film-spec.json")
    voices = spec.get("cast_voices") or {}
    if not isinstance(voices, dict):
        return ("skipped", "cast_voices 未定义")
    bad = [
        f"{k}={v}"
        for k, v in voices.items()
        if isinstance(v, str) and not str(v).lower().startswith("zh")
    ]
    if bad:
        return ("fail", "非中文声线: " + ", ".join(bad))
    return ("pass", "cast_voices 全中文锁")


def _wired(root: Path | str, module: str, attr: str | None = None) -> tuple[Status, str]:
    """Report whether a heavy gate module is importable / wired.

    The real evaluation runs inside the pipeline (preflight / final / review
    action). The panel only signals that the gate is present and will be
    enforced, so a missing module is surfaced as ``unknown`` instead of hiding
    a safety control.
    """
    try:
        imported = __import__(module)
    except Exception:  # noqa: BLE001 -- degrade, do not crash the panel
        return ("unknown", f"{module} 不可用（未在环境接入）")
    if attr and not hasattr(imported, attr):
        return ("unknown", f"{module}.{attr} 不存在")
    return ("pass", f"{module} 已接入，将在 preflight/final 机读执行")


# (code, name, required, checker)
GATE_REGISTRY: list[tuple[str, str, bool, Callable[[Path | str], tuple[Status, str]]]] = [
    ("adult_scale", "成人尺度 IRON", True, _check_adult_scale),
    ("zero_narration", "零旁白锁", True, _check_zero_narration),
    ("voice_lang", "声线中文锁", True, _check_voice_lang),
    ("i2v_motion", "高动/抗无聊 (i2v_motion_gate)", True, lambda r: _wired(r, "i2v_motion_gate", "MEAN_MEAT_FLOOR")),
    ("five_track", "5轨影院混音 (five_track)", True, lambda r: _wired(r, "five_track")),
    ("true_video", "真视频策略 (true_video_policy)", True, lambda r: _wired(r, "true_video_policy")),
    ("dramatic_meaning", "戏剧意义 (dramatic_meaning)", True, lambda r: _wired(r, "dramatic_meaning")),
    ("anti_hijack", "构图防抢走 (composition_anti_hijack)", True, lambda r: _wired(r, "composition_anti_hijack")),
    ("anatomy", "毒镜/解剖安全 (anatomy_safety)", True, lambda r: _wired(r, "anatomy_safety")),
    ("cinematic", "综合 cinematic-gate", True, lambda r: _wired(r, "cinematic_gate")),
]


def collect_gates(root: Path | str) -> dict[str, Any]:
    """Return the unified gate panel for ``root``."""
    base = Path(root).expanduser().resolve()
    gates: list[dict[str, Any]] = []
    hard_fail: list[str] = []
    for code, name, required, checker in GATE_REGISTRY:
        try:
            status, detail = checker(base)
        except Exception as exc:  # noqa: BLE001 -- never let one gate break the panel
            status, detail = ("unknown", f"{code} 评估异常: {exc}")
        gates.append(
            {"code": code, "name": name, "required": required, "status": status, "detail": detail}
        )
        if required and status == "fail":
            hard_fail.append(code)
    return {
        "kind": "gate-panel",
        "root": str(base),
        "gates": gates,
        "hard_fail": hard_fail,
        "blocking": bool(hard_fail),
    }
