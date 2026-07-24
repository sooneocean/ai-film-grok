#!/usr/bin/env python3
"""Long-form continuity_chain.md + byte-identical first/last frame gates."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CHECKLIST_KEYS = (
    "pose",
    "gaze",
    "hands_props",
    "travel",
    "axis",
    "hair",
    "wardrobe",
    "weather",
    "lighting",
)

CODE_MISSING_CHAIN_DOC = "CONTINUITY_CHAIN_DOC_MISSING"
CODE_BYTE_MISMATCH = "CONTINUITY_CHAIN_BYTE_MISMATCH"
CODE_CHECKLIST_INCOMPLETE = "CONTINUITY_CHAIN_CHECKLIST_INCOMPLETE"


def flatten_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    scenes = spec.get("scenes")
    if not isinstance(scenes, list):
        return shots
    for sc in scenes:
        if isinstance(sc, dict) and isinstance(sc.get("shots"), list):
            for s in sc["shots"]:
                if isinstance(s, dict):
                    shots.append(s)
    return shots


def ordered_shot_ids(spec: dict[str, Any]) -> list[str]:
    return [str(s.get("id") or "") for s in flatten_shots(spec) if s.get("id")]


def next_shot_after(spec: dict[str, Any], shot_id: str) -> dict[str, Any] | None:
    """Return the next shot dict in story order, or None if last."""
    shots = flatten_shots(spec)
    for i, s in enumerate(shots):
        if str(s.get("id") or "") == str(shot_id):
            if i + 1 < len(shots):
                return shots[i + 1]
            return None
    return None


def shot_chain_mode(shot: dict[str, Any] | None) -> str:
    if not isinstance(shot, dict):
        return ""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return str(dsl.get("chain_mode") or shot.get("chain_mode") or "").strip().lower()


def wardrobe_state_of(shot: dict[str, Any] | None) -> str:
    if not isinstance(shot, dict):
        return ""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return str(shot.get("wardrobe_state") or dsl.get("wardrobe_state") or "").strip().lower()


# Undress ranks used to decide story-serial promote (keep in sync with edit_policy)
_WARDROBE_RANK = {
    "full": 0,
    "armored": 1,
    "partial": 2,
    "undressed": 3,
    "bare": 4,
}


def should_auto_promote_next(
    prev: dict[str, Any] | None,
    nxt: dict[str, Any] | None,
    *,
    heat_scale: str | None = None,
) -> tuple[bool, str]:
    """Whether register-clip should promote prev last frame → next first frame.

    Product (2026-07-21 教训): 生成时必须按剧情实际 first/last 接戏，
    禁止每镜从 cast 全装重起（回穿 / 姿势断）。
    """
    if not prev or not nxt:
        return False, "no next shot"
    mode = shot_chain_mode(prev) or shot_chain_mode(nxt)
    if mode in {"cut", "bridge", "hard_cut"}:
        return False, f"chain_mode={mode} (no byte promote)"
    if mode in {"continue", "hold", "soft"}:
        return True, f"chain_mode={mode}"
    # Default story serial: undress ladder or max heat sequential
    pw = wardrobe_state_of(prev)
    nw = wardrobe_state_of(nxt)
    pr = _WARDROBE_RANK.get(pw)
    nr = _WARDROBE_RANK.get(nw)
    if pr is not None and pr >= 2:  # partial+
        return True, f"undress continuity prev={pw} (story serial promote)"
    if nr is not None and nr >= 2:
        return True, f"undress continuity next={nw}"
    scale = (heat_scale or "").strip().lower()
    if scale in {"max", "hot"}:
        # Adult short: default continue between consecutive plates unless cut
        return True, f"heat_scale={scale} default serial first/last"
    # Explicit continue via end_pose feeds start
    dsl_p = prev.get("dsl") if isinstance(prev.get("dsl"), dict) else {}
    end = str(dsl_p.get("end_pose") or "").lower()
    if "feed" in end or "→" in end or "feeds" in end:
        return True, "end_pose feeds next"
    return False, "no auto-promote rule matched"


def planned_duration_sec(shots: list[dict[str, Any]]) -> float:
    total = 0.0
    for s in shots:
        d = s.get("duration_sec")
        try:
            total += float(d) if d is not None else 6.0
        except (TypeError, ValueError):
            total += 6.0
    return total


def is_long_form(spec: dict[str, Any], shots: list[dict[str, Any]] | None = None) -> bool:
    if spec.get("long_form") is True or spec.get("require_continuity_chain") is True:
        return True
    if shots is None:
        shots = flatten_shots(spec)
    if len(shots) >= 6:
        return True
    return planned_duration_sec(shots) >= 36.0


def chain_doc_path(root: Path) -> Path:
    return root / "continuity_chain.md"


def frame_chain_receipt_path(root: Path) -> Path:
    return root / "receipts" / "frame-chain.json"


def load_frame_chain_receipt(root: Path) -> dict[str, Any]:
    p = frame_chain_receipt_path(root)
    if not p.is_file():
        return {"schema_version": 1, "joins": [], "updated_at": None}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "joins": [], "updated_at": None}
    if not isinstance(data, dict):
        return {"schema_version": 1, "joins": [], "updated_at": None}
    if not isinstance(data.get("joins"), list):
        data["joins"] = []
    return data


def save_frame_chain_receipt(root: Path, data: dict[str, Any]) -> Path:
    p = frame_chain_receipt_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(UTC).isoformat()
    data["schema_version"] = 1
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def upsert_join(
    root: Path,
    *,
    from_id: str,
    to_id: str,
    mode: str,
    last_sha: str,
    first_sha: str,
    last_path: str | None = None,
    first_path: str | None = None,
    checklist: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = load_frame_chain_receipt(root)
    joins = [
        j
        for j in data["joins"]
        if not (isinstance(j, dict) and j.get("from") == from_id and j.get("to") == to_id)
    ]
    rec = {
        "from": from_id,
        "to": to_id,
        "mode": mode,
        "last_frame_sha256": last_sha,
        "first_frame_sha256": first_sha,
        "byte_identical": bool(last_sha and first_sha and last_sha == first_sha),
        "last_frame_path": last_path,
        "first_frame_path": first_path,
        "checklist": checklist or {},
    }
    joins.append(rec)
    data["joins"] = joins
    save_frame_chain_receipt(root, data)
    return rec


def render_chain_skeleton(
    *,
    title: str,
    root: Path,
    shots: list[dict[str, Any]],
    spine: str = "（填写一句话动作脊柱）",
) -> str:
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    n = len(shots)
    ids = [str(s.get("id") or f"shot{i + 1}") for i, s in enumerate(shots)]
    lines = [
        f"# Continuity Chain — {title}",
        "",
        "> continue 缝：下镜首帧 SHA 必须等于上镜已核准末帧 SHA。规则：skill `references/continuity_chain.md`。",
        "",
        f"- **film root**: `{root}`",
        f"- **updated**: {date}",
        "- **long_form**: true",
        f"- **shot_count**: {n}",
        "",
        "## 动作脊柱（一句话）",
        "",
        spine,
        "",
        "## 全局轴线 / 天气 / 主光",
        "",
        "| 项 | 锁定值 |",
        "|---|---|",
        "| 屏幕主行进方向 |  |",
        "| 180° 轴线 |  |",
        "| 天气 |  |",
        "| 主光 |  |",
        "",
        "## 连接点",
        "",
    ]
    for i in range(len(ids) - 1):
        a, b = ids[i], ids[i + 1]
        dsl = shots[i + 1].get("dsl") if isinstance(shots[i + 1].get("dsl"), dict) else {}
        mode = str(dsl.get("chain_mode") or "continue")
        lines += [
            f"### Join: {a} → {b}",
            "",
            "| 字段 | 值 |",
            "|---|---|",
            f"| chain_mode | {mode} |",
            f"| last_frame path | `clips/{a}.mp4` last |",
            "| last_frame sha256 |  |",
            f"| first_frame path | `keyframes/{b}.png` |",
            "| first_frame sha256 |  |",
            "| byte_identical |  |",
            "",
            "**九项核对**（全部 pass 才 I2V 下镜）：",
            "",
            "| # | 维度 | pass/fail | 备注 |",
            "|---|---|---|---|",
            "| 1 | 姿势 pose |  |  |",
            "| 2 | 视线 gaze |  |  |",
            "| 3 | 手与道具归属 hands_props |  |  |",
            "| 4 | 行进方向 travel |  |  |",
            "| 5 | 镜头轴线 axis |  |  |",
            "| 6 | 发型 hair |  |  |",
            "| 7 | 服装 wardrobe |  |  |",
            "| 8 | 天气 weather |  |  |",
            "| 9 | 光线 lighting |  |  |",
            "",
            "**禁止掩盖**：未使用加长 dissolve / 定格 / 倒放 / 无关插镜挡跳切。□ 确认",
            "",
        ]
    lines += [
        "## Cut 缝（故意断开）",
        "",
        "| from → to | 叙事理由 | transition |",
        "|---|---|---|",
        "|  |  | hard |",
        "",
        "## 生成顺序（打勾）",
        "",
        "- [ ] continuity_chain.md 已写脊柱 + 全部 join",
        "- [ ] 仅链首（或 cut 后首镜）从 cast 起 still",
        "- [ ] 每 continue 缝：`extract-frame --promote-keyframe` 后再 I2V",
        "- [ ] `aifilm continuity-chain check` 通过",
        "- [ ] final 前未用后期掩盖断裂",
        "",
    ]
    return "\n".join(lines)


def init_chain_doc(root: Path, spec: dict[str, Any], *, force: bool = False) -> Path:
    path = chain_doc_path(root)
    if path.is_file() and not force:
        return path
    shots = flatten_shots(spec)
    title = str(spec.get("title") or root.name)
    intent = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    spine = str(intent.get("logline") or "（填写一句话动作脊柱）")
    path.write_text(
        render_chain_skeleton(title=title, root=root, shots=shots, spine=spine),
        encoding="utf-8",
    )
    return path


def _parse_checklist_from_md(text: str) -> dict[str, dict[str, str]]:
    """Best-effort: join header + pass/fail cells. Returns { 'shot01→shot02': {pose: pass, ...} }."""
    result: dict[str, dict[str, str]] = {}
    current: str | None = None
    join_re = re.compile(r"###\s*Join:\s*(\S+)\s*→\s*(\S+)", re.I)
    row_re = re.compile(
        r"\|\s*\d+\s*\|\s*[^|]*\b("
        + "|".join(CHECKLIST_KEYS)
        + r")\b[^|]*\|\s*(pass|fail|PASS|FAIL|ok|OK|yes|YES|no|NO|\s*)\s*\|",
        re.I,
    )
    for line in text.splitlines():
        m = join_re.search(line)
        if m:
            current = f"{m.group(1)}→{m.group(2)}"
            result.setdefault(current, {})
            continue
        if current is None:
            continue
        rm = row_re.search(line)
        if rm:
            key = rm.group(1).lower()
            val = (rm.group(2) or "").strip().lower()
            if val in {"pass", "ok", "yes"}:
                result[current][key] = "pass"
            elif val in {"fail", "no"}:
                result[current][key] = "fail"
    return result


def check_continuity_chain(
    root: Path,
    spec: dict[str, Any],
    *,
    strict: bool = False,
    require_doc_if_long: bool = True,
) -> dict[str, Any]:
    """Return lint report: ok, hard/soft issues, codes."""
    shots = flatten_shots(spec)
    long_form = is_long_form(spec, shots)
    issues: list[dict[str, Any]] = []
    doc = chain_doc_path(root)
    receipt = load_frame_chain_receipt(root)
    joins_by_pair = {}
    for j in receipt.get("joins") or []:
        if isinstance(j, dict) and j.get("from") and j.get("to"):
            joins_by_pair[f"{j['from']}→{j['to']}"] = j

    if require_doc_if_long and long_form and not doc.is_file():
        issues.append(
            {
                "code": CODE_MISSING_CHAIN_DOC,
                "severity": "error",
                "message": (
                    "long-form film missing continuity_chain.md — "
                    "run: aifilm continuity-chain init --root <root>"
                ),
            }
        )

    md_checklists: dict[str, dict[str, str]] = {}
    if doc.is_file():
        try:
            md_checklists = _parse_checklist_from_md(doc.read_text(encoding="utf-8"))
        except OSError:
            md_checklists = {}

    # Byte identity for continue joins recorded in receipt
    for pair, j in joins_by_pair.items():
        mode = str(j.get("mode") or "continue").lower()
        if mode in {"cut", "hard"}:
            continue
        last_s = j.get("last_frame_sha256") or ""
        first_s = j.get("first_frame_sha256") or ""
        identical = j.get("byte_identical")
        if identical is False or (last_s and first_s and last_s != first_s):
            issues.append(
                {
                    "code": CODE_BYTE_MISMATCH,
                    "severity": "error",
                    "message": (
                        f"join {pair}: first_frame sha != last_frame sha "
                        f"(must byte-reuse approved last frame; do not restart from cast)"
                    ),
                    "join": pair,
                }
            )
        # checklist
        cl = j.get("checklist") if isinstance(j.get("checklist"), dict) else {}
        if not cl and pair in md_checklists:
            cl = md_checklists[pair]
        missing = [
            k for k in CHECKLIST_KEYS if str(cl.get(k, "")).lower() not in {"pass", "ok", "yes"}
        ]
        fails = [k for k in CHECKLIST_KEYS if str(cl.get(k, "")).lower() in {"fail", "no"}]
        if fails:
            issues.append(
                {
                    "code": CODE_CHECKLIST_INCOMPLETE,
                    "severity": "error" if strict else "warning",
                    "message": f"join {pair}: checklist FAIL on {fails}",
                    "join": pair,
                }
            )
        elif missing and strict:
            issues.append(
                {
                    "code": CODE_CHECKLIST_INCOMPLETE,
                    "severity": "warning",
                    "message": f"join {pair}: checklist incomplete (need pass for {missing})",
                    "join": pair,
                }
            )

    # Long form soft: no promote receipts yet after stills started
    codes = sorted({i["code"] for i in issues})
    hard = [i for i in issues if i.get("severity") == "error"]
    soft = [i for i in issues if i.get("severity") != "error"]
    return {
        "ok": len(hard) == 0,
        "long_form": long_form,
        "doc_present": doc.is_file(),
        "doc_path": str(doc) if doc.is_file() else None,
        "receipt_joins": len(joins_by_pair),
        "issues": issues,
        "codes": codes,
        "error_count": len(hard),
        "warning_count": len(soft),
        "hard": hard,
        "soft": soft,
        "checklist_keys": list(CHECKLIST_KEYS),
        "forbidden_coverups": [
            "long dissolve to hide break",
            "freeze frame",
            "reverse playback",
            "unrelated insert to mask jump",
        ],
    }
