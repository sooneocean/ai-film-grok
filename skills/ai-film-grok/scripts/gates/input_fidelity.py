#!/usr/bin/env python3
"""Input Fidelity — aggregate how well the film root still matches user input.

Receipt: receipts/input-fidelity.json
Docs: references/hard-defaults.md · memory/2026-08-04-input-fidelity.md

Read-only aggregation over story-reception, script-value-debrief, film-spec,
and dialogue/caption fields. Does not rewrite story or approve pilot.
"""

from __future__ import annotations

from util.errors import FilmError

import os
import re
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT_NAME = "input-fidelity.json"
KIND = "input-fidelity"
DEFAULT_PLAN_FLOOR = 0.75
DEFAULT_FINAL_FLOOR = 0.80

_META_TOKEN_SKIP = frozenset(
    {
        "成人",
        "办事",
        "竖屏",
        "短剧",
        "旁白",
        "镜头",
        "特写",
        "时长",
        "开场",
        "转场",
        "集尾",
        "角色",
        "场景",
        "对白",
        "剧本",
        "小说",
        "故事",
        "画面",
        "动作",
        "高潮",
        "前戏",
        "插入",
    }
)

# Keep in sync with edit_policy_heat._TEMPLATE_NAR_POLLUTION_MARKERS
# (local copy avoids circular import edit_policy ↔ edit_policy_heat).
_TEMPLATE_NAR_POLLUTION_MARKERS: tuple[str, ...] = (
    "展厅落锁",
    "今晚只加演你",
    "今晚只办事加演",
    "肩带一滑，规矩失效",
    "肩带一滑。卸甲半裸",
    "贴耳：下一场",
    "咬耳：下一场",
    "门落锁。今晚只办事",
    "跨坐落稳。整根吃进",
    "门闩还热，故事未完",
    "扣子崩开。半裸卸甲",
)


def _is_template_nar_pollution(nar: object) -> bool:
    text = str(nar or "").strip()
    if not text:
        return False
    return any(m in text for m in _TEMPLATE_NAR_POLLUTION_MARKERS)


def _lint_pollution(
    shots: list[dict[str, Any]],
    *,
    source_excerpt: str | None = None,
) -> dict[str, Any]:
    """Local subset of lint_user_source_fidelity (no edit_policy import)."""
    excerpt = (source_excerpt or "").strip()
    if not excerpt:
        return {
            "ok": True,
            "applicable": False,
            "codes": [],
            "issues": [],
            "polluted_shots": [],
            "pollution_ratio": 0.0,
        }
    polluted: list[str] = []
    voiced = 0
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        nar = str(shot.get("nar") or "").strip()
        if not nar:
            continue
        voiced += 1
        if _is_template_nar_pollution(nar):
            polluted.append(str(shot.get("id") or "?"))
    ratio = (len(polluted) / voiced) if voiced else 0.0
    codes: list[str] = []
    issues: list[dict[str, Any]] = []
    if voiced >= 4 and ratio + 1e-9 >= 0.40:
        codes.append("USER_SOURCE_NAR_POLLUTED")
        issues.append(
            {
                "code": "USER_SOURCE_NAR_POLLUTED",
                "severity": "warning",
                "message": (f"旁白模板污染 {ratio:.0%}（{len(polluted)}/{voiced}）含库存句"),
            }
        )
    return {
        "ok": len(codes) == 0,
        "applicable": True,
        "codes": codes,
        "issues": issues,
        "polluted_shots": polluted,
        "pollution_ratio": round(ratio, 3),
    }


class InputFidelityError(FilmError):
    """User-facing fidelity check failure."""


def receipt_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / "receipts" / RECEIPT_NAME


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _shots_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scene in _as_list(spec.get("scenes")):
        if not isinstance(scene, dict):
            continue
        for sh in _as_list(scene.get("shots")):
            if isinstance(sh, dict):
                out.append(sh)
    # Flat ordered_shots fallback
    if not out:
        for sh in _as_list(spec.get("ordered_shots") or spec.get("shots")):
            if isinstance(sh, dict):
                out.append(sh)
    return out


def _load_reception(root: Path) -> dict[str, Any] | None:
    for candidate in (
        root / "receipts" / "story-reception.json",
        root / "story-reception.json",
    ):
        data = read_json(candidate)
        if isinstance(data, dict):
            return data
    return None


def _load_debrief(root: Path) -> dict[str, Any] | None:
    data = read_json(root / "receipts" / "script-value-debrief.json")
    return data if isinstance(data, dict) else None


def _source_blob(
    reception: dict[str, Any] | None,
    spec: dict[str, Any],
) -> tuple[str, str | None]:
    """Return (excerpt_text, source_sha_or_none)."""
    if reception:
        source = _as_dict(reception.get("source"))
        raw = _text(source.get("raw_text"))
        sha = _text(source.get("sha256")) or None
        if raw:
            return raw, sha
    excerpt = _text(spec.get("source_excerpt") or spec.get("user_source_excerpt"))
    sha = _text(spec.get("source_sha256") or spec.get("user_source_sha256")) or None
    return excerpt, sha


def _protected_dialogue(reception: dict[str, Any] | None) -> list[str]:
    if not reception:
        return []
    fid = _as_dict(reception.get("fidelity"))
    out: list[str] = []
    for item in _as_list(fid.get("protected_dialogue")):
        if isinstance(item, dict):
            t = _text(item.get("text") or item.get("line") or item.get("spoken_text"))
        else:
            t = _text(item)
        if t and t not in out:
            out.append(t)
    return out


def _must_keep_ids(debrief: dict[str, Any] | None) -> list[str]:
    if not debrief:
        return []
    ids: list[str] = []
    for key in ("must_keep_beat_ids", "must_keep_beats"):
        for item in _as_list(debrief.get(key)):
            if isinstance(item, dict):
                bid = _text(item.get("id") or item.get("beat_id"))
            else:
                bid = _text(item)
            if bid and bid not in ids:
                ids.append(bid)
    # beat_cards marked must_keep
    for card in _as_list(debrief.get("beat_cards")):
        if not isinstance(card, dict):
            continue
        if card.get("must_keep") is True or card.get("keep") is True:
            bid = _text(card.get("id") or card.get("beat_id"))
            if bid and bid not in ids:
                ids.append(bid)
    return ids


def _shot_corpus(shot: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "nar",
        "spoken_text",
        "spoken_text_zh",
        "caption_text",
        "playable_action",
        "story_beat",
        "source_quote",
        "visible_change",
    ):
        parts.append(_text(shot.get(key)))
    dsl = _as_dict(shot.get("dsl"))
    for key in ("action", "motion", "subject", "prompt", "i2v_prompt"):
        parts.append(_text(dsl.get(key)))
    # nested prompt bags
    for bag_key in ("prompt", "still_prompt", "i2v"):
        bag = shot.get(bag_key)
        if isinstance(bag, dict):
            parts.extend(_text(v) for v in bag.values() if isinstance(v, (str, int, float)))
        elif isinstance(bag, str):
            parts.append(bag)
    return "\n".join(p for p in parts if p)


def _all_shot_text(shots: list[dict[str, Any]]) -> str:
    return "\n".join(_shot_corpus(s) for s in shots)


def _distinctive_tokens(excerpt: str, *, limit: int = 16) -> list[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]{2,4}", excerpt)
    distinctive: list[str] = []
    for t in tokens:
        if t in _META_TOKEN_SKIP:
            continue
        if t not in distinctive:
            distinctive.append(t)
        if len(distinctive) >= limit:
            break
    # Latin/name tokens
    for t in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", excerpt):
        if t.lower() not in {x.lower() for x in distinctive}:
            distinctive.append(t)
        if len(distinctive) >= limit:
            break
    return distinctive


def _score_entity_coverage(
    excerpt: str,
    shots: list[dict[str, Any]],
) -> tuple[float, list[str], list[str]]:
    if not excerpt or not shots:
        return 0.0, [], []
    tokens = _distinctive_tokens(excerpt)
    if not tokens:
        return 1.0, [], []
    corpus = _all_shot_text(shots)
    hit = [t for t in tokens if t in corpus]
    miss = [t for t in tokens if t not in corpus]
    score = len(hit) / max(1, len(tokens))
    return round(score, 3), hit, miss


def _score_protected_dialogue(
    protected: list[str],
    shots: list[dict[str, Any]],
) -> tuple[float, list[dict[str, Any]], list[str]]:
    if not protected:
        return 1.0, [], []
    corpus = _all_shot_text(shots)
    covered: list[dict[str, Any]] = []
    missing: list[str] = []
    for line in protected:
        # substring or first 8 chars of CJK line
        needle = line if len(line) <= 24 else line[:16]
        ok = needle in corpus or line in corpus
        if ok:
            covered.append({"text": line[:80], "ok": True})
        else:
            missing.append(line[:80])
            covered.append({"text": line[:80], "ok": False})
    score = sum(1 for c in covered if c.get("ok")) / len(protected)
    return round(score, 3), covered, missing


def _score_must_keep_map(
    must_keep: list[str],
    shots: list[dict[str, Any]],
    debrief: dict[str, Any] | None,
) -> tuple[float, list[dict[str, Any]], list[str]]:
    if not must_keep:
        # no debrief contract → neutral (not a free pass for pollution)
        return 1.0, [], []
    shot_ids = {_text(s.get("id")) for s in shots if _text(s.get("id"))}
    beat_refs: set[str] = set()
    for s in shots:
        for key in ("beat_id", "must_keep_beat_id", "story_beat_id", "source_beat_id"):
            bid = _text(s.get(key))
            if bid:
                beat_refs.add(bid)
        for key in ("source_span", "source_quote"):
            if _text(s.get(key)):
                # presence of source anchor counts as mapped when ids unknown
                beat_refs.add("__has_source_anchor__")
    # debrief beat→shot map if present
    mapped_from_debrief: dict[str, list[str]] = {}
    if debrief:
        for item in _as_list(debrief.get("beat_shot_map") or debrief.get("shot_map")):
            if not isinstance(item, dict):
                continue
            bid = _text(item.get("beat_id") or item.get("id"))
            sids = item.get("shot_ids") or item.get("shots") or []
            if isinstance(sids, str):
                sids = [sids]
            if bid:
                mapped_from_debrief[bid] = [_text(x) for x in sids if _text(x)]

    rows: list[dict[str, Any]] = []
    unmapped: list[str] = []
    for bid in must_keep:
        shots_hit = mapped_from_debrief.get(bid) or []
        direct = bid in shot_ids or bid in beat_refs
        ok = bool(shots_hit) or direct
        # soft: any source_quote on majority shots when ids don't match naming
        if not ok and "__has_source_anchor__" in beat_refs and len(shots) >= 1:
            # partial credit path — still list as soft unmapped if no explicit id
            ok = False
        rows.append(
            {
                "must_keep_beat_id": bid,
                "shot_ids": shots_hit,
                "ok": ok,
            }
        )
        if not ok:
            unmapped.append(bid)
    score = (len(must_keep) - len(unmapped)) / len(must_keep)
    return round(score, 3), rows, unmapped


def _score_source_anchors(shots: list[dict[str, Any]]) -> tuple[float, int, int]:
    if not shots:
        return 0.0, 0, 0
    anchored = 0
    for s in shots:
        if any(
            _text(s.get(k))
            for k in ("source_quote", "source_span", "source_beat_id", "must_keep_beat_id")
        ):
            anchored += 1
            continue
        # weak anchor: playable_action or story_beat present
        if _text(s.get("playable_action") or s.get("story_beat")):
            anchored += 0  # do not count as strong anchor
    strong = sum(
        1
        for s in shots
        if any(
            _text(s.get(k))
            for k in ("source_quote", "source_span", "source_beat_id", "must_keep_beat_id")
        )
    )
    score = strong / len(shots)
    return round(score, 3), strong, len(shots)


def _score_debrief_contract(debrief: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
    if not debrief:
        return 0.0, {"present": False, "confirmed": False}
    promise = _text(debrief.get("viewer_promise"))
    confirmed = bool(
        debrief.get("confirmed_by_user")
        or debrief.get("user_confirmed")
        or _text(debrief.get("confirm_phrase"))
    )
    must_keep = _must_keep_ids(debrief)
    score = 0.0
    if promise:
        score += 0.4
    if len(must_keep) >= 2:
        score += 0.35
    elif len(must_keep) == 1:
        score += 0.15
    if confirmed:
        score += 0.25
    return round(min(1.0, score), 3), {
        "present": True,
        "confirmed": confirmed,
        "viewer_promise": promise[:120] if promise else "",
        "must_keep_count": len(must_keep),
    }


def build_input_fidelity_report(
    root: Path | str,
    *,
    strict: bool | None = None,
    write: bool = True,
    plan_floor: float = DEFAULT_PLAN_FLOOR,
) -> dict[str, Any]:
    """Aggregate fidelity signals and optionally write receipts/input-fidelity.json."""
    root_p = _root(root)
    spec = read_json(root_p / "film-spec.json") or {}
    reception = _load_reception(root_p)
    debrief = _load_debrief(root_p)
    shots = _shots_from_spec(spec)
    excerpt, source_sha = _source_blob(reception, spec)
    protected = _protected_dialogue(reception)
    must_keep = _must_keep_ids(debrief)

    codes: list[str] = []
    issues: list[dict[str, Any]] = []

    # 1) pollution lint (local copy — edit_policy_heat imports cycle)
    heat = _text(spec.get("heat_scale")) or None
    pollution = _lint_pollution(shots, source_excerpt=excerpt or None)
    pollution_ok = bool(pollution.get("ok", True))
    for c in _as_list(pollution.get("codes")):
        if c and c not in codes:
            codes.append(str(c))
    for iss in _as_list(pollution.get("issues")):
        if isinstance(iss, dict):
            issues.append(iss)

    # 2) entity coverage
    entity_score, entity_hit, entity_miss = _score_entity_coverage(excerpt, shots)
    if excerpt and shots and entity_score < 0.5 and len(entity_miss) >= 4:
        codes.append("INPUT_ENTITY_COVERAGE_LOW")
        issues.append(
            {
                "code": "INPUT_ENTITY_COVERAGE_LOW",
                "severity": "warning",
                "message": (
                    f"用户原文实体覆盖偏低 {entity_score:.0%}；缺失: " + "、".join(entity_miss[:6])
                ),
            }
        )

    # 3) protected dialogue
    prot_score, prot_rows, prot_missing = _score_protected_dialogue(protected, shots)
    if protected and prot_missing:
        codes.append("PROTECTED_DIALOGUE_DROPPED")
        issues.append(
            {
                "code": "PROTECTED_DIALOGUE_DROPPED",
                "severity": "warning",
                "message": ("保护台词未进入 spoken/caption/nar: " + "；".join(prot_missing[:4])),
            }
        )

    # 4) must_keep map
    mk_score, mk_rows, mk_unmapped = _score_must_keep_map(must_keep, shots, debrief)
    if must_keep and mk_unmapped:
        codes.append("MUST_KEEP_UNMAPPED")
        issues.append(
            {
                "code": "MUST_KEEP_UNMAPPED",
                "severity": "warning",
                "message": "不可砍 beat 未映射到 shot: " + ", ".join(mk_unmapped[:8]),
            }
        )

    # 5) source anchors on shots
    anchor_score, anchor_n, shot_n = _score_source_anchors(shots)
    if shots and anchor_score < 0.25 and excerpt:
        codes.append("SHOT_SOURCE_ANCHOR_SPARSE")
        issues.append(
            {
                "code": "SHOT_SOURCE_ANCHOR_SPARSE",
                "severity": "info",
                "message": (
                    f"仅 {anchor_n}/{shot_n} 镜有 source_quote/span/beat 锚点（F1 将默认要求）"
                ),
            }
        )

    # 6) debrief contract
    debrief_score, debrief_meta = _score_debrief_contract(debrief)
    if not debrief:
        codes.append("DEBRIEF_MISSING")
        issues.append(
            {
                "code": "DEBRIEF_MISSING",
                "severity": "warning",
                "message": "缺 receipts/script-value-debrief.json（lock 前应 seed+confirm）",
            }
        )
    elif not debrief_meta.get("confirmed"):
        codes.append("DEBRIEF_UNCONFIRMED")
        issues.append(
            {
                "code": "DEBRIEF_UNCONFIRMED",
                "severity": "info",
                "message": "debrief 未用户确认 promise/must_keep",
            }
        )

    if not excerpt:
        codes.append("SOURCE_EXCERPT_MISSING")
        issues.append(
            {
                "code": "SOURCE_EXCERPT_MISSING",
                "severity": "warning",
                "message": "无 story-reception.source.raw_text 且 film-spec 无 source_excerpt",
            }
        )

    if not shots:
        codes.append("FILM_SPEC_SHOTS_MISSING")
        issues.append(
            {
                "code": "FILM_SPEC_SHOTS_MISSING",
                "severity": "warning",
                "message": "film-spec 无 shots；fidelity 仅能评 reception/debrief",
            }
        )

    # Weighted score (explainable)
    # pollution: 0.30 · entity 0.25 · protected 0.15 · must_keep 0.15 · debrief 0.10 · anchor 0.05
    poll_score = (
        1.0 if pollution_ok else max(0.0, 1.0 - float(pollution.get("pollution_ratio") or 0.0))
    )
    if not excerpt:
        # without source, do not pretend high fidelity
        entity_score = min(entity_score, 0.3)
        poll_score = min(poll_score, 0.5)

    score = round(
        poll_score * 0.30
        + entity_score * 0.25
        + prot_score * 0.15
        + mk_score * 0.15
        + debrief_score * 0.10
        + anchor_score * 0.05,
        3,
    )

    hard_codes = {
        "USER_SOURCE_NAR_POLLUTED",
        "PROTECTED_DIALOGUE_DROPPED",
        "MUST_KEEP_UNMAPPED",
        "INPUT_ENTITY_COVERAGE_LOW",
    }
    if strict is None:
        env = (os.environ.get("AIFILM_FIDELITY_STRICT") or "").strip().lower()
        if env in {"1", "true", "yes", "on"}:
            strict = True
        elif env in {"0", "false", "no", "off"}:
            strict = False
        else:
            # default hard when max + user_source_fidelity_strict + debrief confirmed
            usf = spec.get("user_source_fidelity_strict")
            if usf is None:
                usf = heat == "max" and bool(excerpt)
            strict = bool(usf) and bool(debrief_meta.get("confirmed")) and heat == "max"

    blocking = [c for c in codes if c in hard_codes]
    ok = score >= plan_floor and (not strict or not blocking)
    if strict and blocking:
        ok = False

    promise_ref = ""
    if debrief:
        promise_ref = _text(debrief.get("viewer_promise"))[:200]

    report: dict[str, Any] = {
        "kind": KIND,
        "ok": ok,
        "score": score,
        "plan_floor": plan_floor,
        "strict": bool(strict),
        "codes": sorted(set(codes)),
        "blocking_codes": sorted(set(blocking)) if strict else [],
        "issues": issues,
        "source_sha": source_sha,
        "has_source": bool(excerpt),
        "promise_ref": promise_ref,
        "must_keep": must_keep,
        "protected_dialogue_coverage": {
            "score": prot_score,
            "total": len(protected),
            "missing": prot_missing,
            "rows": prot_rows,
        },
        "entity_coverage": {
            "score": entity_score,
            "hit": entity_hit,
            "miss": entity_miss,
        },
        "must_keep_map": {
            "score": mk_score,
            "unmapped": mk_unmapped,
            "rows": mk_rows,
        },
        "source_anchors": {
            "score": anchor_score,
            "anchored": anchor_n,
            "shot_count": shot_n,
        },
        "user_source_fidelity": {
            "ok": pollution_ok,
            "pollution_ratio": pollution.get("pollution_ratio"),
            "codes": pollution.get("codes"),
            "polluted_shots": pollution.get("polluted_shots"),
        },
        "debrief": debrief_meta,
        "shot_count": len(shots),
        "next_cmd": _suggest_next(codes, debrief_meta, shots, excerpt),
        "generated_at": utc_now(),
        "note": (
            "Input fidelity = how much the plan still looks like user input; "
            "not erotic impact. Soft by default; strict when max+usf+debrief confirmed "
            "or AIFILM_FIDELITY_STRICT=1."
        ),
    }

    if write:
        write_json(receipt_path(root_p), report)
        report["receipt"] = str(receipt_path(root_p))

    return report


def _suggest_next(
    codes: list[str],
    debrief_meta: dict[str, Any],
    shots: list[dict[str, Any]],
    excerpt: str,
) -> str:
    if "SOURCE_EXCERPT_MISSING" in codes or not excerpt:
        return 'aifilm plan receive --root "<film>" --file story-reception.json'
    if not debrief_meta.get("present"):
        return 'aifilm plan debrief --root "<film>" --action seed'
    if not debrief_meta.get("confirmed"):
        return (
            'aifilm plan debrief --root "<film>" --action confirm '
            '--user-phrase "确认 promise 与不可砍 beat"'
        )
    if not shots:
        return 'aifilm plan run --root "<film>" --received-file receipts/story-reception.json'
    if any(
        c in codes
        for c in (
            "USER_SOURCE_NAR_POLLUTED",
            "INPUT_ENTITY_COVERAGE_LOW",
            "PROTECTED_DIALOGUE_DROPPED",
            "MUST_KEEP_UNMAPPED",
            "SHOT_SOURCE_ANCHOR_SPARSE",
        )
    ):
        return 'aifilm fidelity apply --root "<film>" && aifilm fidelity check --root "<film>"'
    return 'aifilm dispatch --root "<film>"'


def _split_source_chunks(excerpt: str, n: int) -> list[str]:
    """Split source into n quote chunks (sentence-ish, CJK-friendly)."""
    text = (excerpt or "").strip()
    if not text or n <= 0:
        return []
    # Prefer 。！？；\n boundaries
    parts = re.split(r"(?<=[。！？；\n])", text)
    parts = [p.strip() for p in parts if p and p.strip()]
    if not parts:
        parts = [text]
    if len(parts) >= n:
        # distribute evenly
        out: list[str] = []
        step = len(parts) / n
        for i in range(n):
            start = int(i * step)
            end = int((i + 1) * step) if i < n - 1 else len(parts)
            chunk = "".join(parts[start:end]).strip() or parts[min(start, len(parts) - 1)]
            out.append(chunk[:80])
        return out
    # fewer sentences than shots: pad by sliding window
    out = list(parts)
    while len(out) < n:
        out.append(parts[len(out) % len(parts)])
    return [c[:80] for c in out[:n]]


def apply_fidelity_to_spec(
    root: Path | str,
    *,
    write_spec: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """F1 · stamp source_quote, must_keep map, protected dialogue onto film-spec shots.

    Does not invent story; only projects reception/debrief anchors.
    """
    root_p = _root(root)
    spec_path = root_p / "film-spec.json"
    spec = read_json(spec_path) or {}
    if not spec:
        raise InputFidelityError("film-spec.json missing — plan/write-spec first")
    reception = _load_reception(root_p)
    debrief = _load_debrief(root_p)
    excerpt, source_sha = _source_blob(reception, spec)
    if not excerpt:
        raise InputFidelityError("no source excerpt/raw_text to apply")
    protected = _protected_dialogue(reception)
    must_keep = _must_keep_ids(debrief)
    shots = _shots_from_spec(spec)
    if not shots:
        raise InputFidelityError("film-spec has no shots")

    chunks = _split_source_chunks(excerpt, len(shots))
    changed = 0
    for i, shot in enumerate(shots):
        quote = chunks[i] if i < len(chunks) else excerpt[:40]
        if force or not _text(shot.get("source_quote")):
            shot["source_quote"] = quote
            changed += 1
        if force or not _text(shot.get("source_span")):
            shot["source_span"] = f"chunk:{i}"
        # weak beat_id for must_keep round-robin
        if must_keep and (force or not _text(shot.get("must_keep_beat_id"))):
            shot["must_keep_beat_id"] = must_keep[i % len(must_keep)]
            if not _text(shot.get("beat_id")):
                shot["beat_id"] = shot["must_keep_beat_id"]

    # Protected dialogue: first N dialogue-capable shots get spoken_text
    if protected:
        placed = 0
        for shot in shots:
            if placed >= len(protected):
                break
            line = protected[placed]
            corpus = _shot_corpus(shot)
            if line in corpus or line[:12] in corpus:
                placed += 1
                continue
            # prefer empty spoken
            if force or not _text(shot.get("spoken_text") or shot.get("spoken_text_zh")):
                shot["spoken_text"] = line
                shot["spoken_text_zh"] = line
                if not _text(shot.get("caption_text")):
                    shot["caption_text"] = line
                if not _text(shot.get("caption_mode")):
                    shot["caption_mode"] = "zh"
                placed += 1
                changed += 1

    # debrief beat_shot_map if missing
    if debrief and must_keep:
        existing_map = _as_list(debrief.get("beat_shot_map"))
        if force or not existing_map:
            bmap = []
            for bi, bid in enumerate(must_keep):
                sid = _text(shots[bi % len(shots)].get("id"))
                bmap.append({"beat_id": bid, "shot_ids": [sid] if sid else []})
            debrief["beat_shot_map"] = bmap
            write_json(root_p / "receipts" / "script-value-debrief.json", debrief)

    if source_sha and not _text(spec.get("source_sha256")):
        spec["source_sha256"] = source_sha
    if not _text(spec.get("source_excerpt")):
        spec["source_excerpt"] = excerpt[:500]

    if write_spec:
        write_json(spec_path, spec)

    report = fidelity_check(root_p, write=True)
    return {
        "ok": True,
        "kind": "input-fidelity-apply",
        "shots_touched": changed,
        "shot_count": len(shots),
        "must_keep": must_keep,
        "protected_placed": len(protected),
        "fidelity": {
            "ok": report.get("ok"),
            "score": report.get("score"),
            "codes": report.get("codes"),
        },
        "receipt": report.get("receipt"),
        "generated_at": utc_now(),
    }


def still_source_overlap(
    root: Path | str,
    *,
    shot_id: str,
    playable_action: str | None = None,
) -> dict[str, Any]:
    """F2 · keyword overlap between still action and shot source_quote/dsl.action."""
    root_p = _root(root)
    spec = read_json(root_p / "film-spec.json") or {}
    shots = _shots_from_spec(spec)
    shot = next((s for s in shots if _text(s.get("id")) == str(shot_id).strip()), None)
    if not shot:
        return {
            "ok": True,
            "applicable": False,
            "codes": [],
            "note": f"shot {shot_id} not in film-spec",
        }
    quote = _text(shot.get("source_quote") or shot.get("playable_action") or shot.get("nar"))
    dsl = _as_dict(shot.get("dsl"))
    action = _text(dsl.get("action") or shot.get("playable_action"))
    pa = _text(playable_action) or action or quote
    needles = [
        t for t in re.findall(r"[\u4e00-\u9fff]{2,4}|[A-Za-z]{3,}", quote + " " + action) if t
    ]
    needles = needles[:8]
    if not needles:
        return {"ok": True, "applicable": False, "codes": [], "score": 1.0, "needles": []}
    hit = [t for t in needles if t in pa]
    score = len(hit) / len(needles)
    strict = (os.environ.get("AIFILM_STILL_SOURCE_OVERLAP_STRICT") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    } or bool(spec.get("still_source_overlap_strict"))
    ok = score >= 0.25 or not strict
    codes = [] if ok or score >= 0.25 else ["STILL_SOURCE_OVERLAP_LOW"]
    if score < 0.25:
        codes = ["STILL_SOURCE_OVERLAP_LOW"]
        ok = not strict
    return {
        "ok": ok,
        "applicable": True,
        "score": round(score, 3),
        "needles": needles,
        "hit": hit,
        "codes": codes,
        "strict": strict,
        "shot_id": shot_id,
        "source_quote": quote[:80],
    }


def assert_still_source_for_register(
    root: Path | str,
    *,
    shot_id: str,
    playable_action: str | None = None,
) -> dict[str, Any]:
    rep = still_source_overlap(root, shot_id=shot_id, playable_action=playable_action)
    if rep.get("strict") and not rep.get("ok"):
        raise InputFidelityError(
            f"still source overlap low for {shot_id}: score={rep.get('score')} "
            f"missing {rep.get('needles')}"
        )
    return rep


def story_beat_prompt_prefix(shot: dict[str, Any]) -> str:
    """F2 · I2V/H3 prompt head: Story beat from source_quote / playable_action."""
    quote = _text(
        shot.get("source_quote")
        or shot.get("playable_action")
        or shot.get("story_beat")
        or shot.get("nar")
    )
    if not quote:
        return ""
    return f"Story beat: {quote[:120]}."


def inject_story_beat_into_prompt(text: str, shot: dict[str, Any]) -> str:
    prefix = story_beat_prompt_prefix(shot)
    base = (text or "").strip()
    if not prefix:
        return base
    if prefix in base or "Story beat:" in base:
        return base
    if not base:
        return prefix
    return f"{prefix} {base}".strip()


def _craft_onepager(root: Path, variety: dict[str, Any]) -> dict[str, Any]:
    """Director one-pager: poses / CU / L4 / cameras / speakers (S5.1)."""
    spec = read_json(root / "film-spec.json") or {}
    shots: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict):
                shots.append(shot)
    if not shots and isinstance(spec.get("shots"), list):
        shots = [s for s in spec["shots"] if isinstance(s, dict)]

    speakers: list[str] = []
    cameras: list[str] = []
    sizes: list[str] = []
    for shot in shots:
        sp = str(
            shot.get("speaker")
            or (shot.get("audio_cues") or {}).get("speaker")
            or ""
        ).strip()
        if sp:
            speakers.append(sp)
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        cam = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
        dsl_cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
        move = str(
            shot.get("camera_move")
            or dsl.get("camera_move")
            or cam.get("move")
            or dsl_cam.get("move")
            or ""
        ).strip()
        if move:
            cameras.append(move)
        size = str(
            shot.get("shot_size")
            or cam.get("shot_size")
            or dsl.get("shot_size")
            or dsl_cam.get("shot_size")
            or ""
        ).strip()
        if size:
            sizes.append(size)

    unique_speakers = sorted({s for s in speakers if s})
    unique_cameras = sorted({c for c in cameras if c})
    unique_sizes = sorted({s for s in sizes if s})
    poses = list(variety.get("unique_poses") or [])
    face_cu = int(variety.get("face_cu_count") or 0)
    l4 = int(variety.get("l4_insert_count") or 0)
    floors = variety.get("floors") if isinstance(variety.get("floors"), dict) else {}
    pose_floor = int(floors.get("poses") or 4)
    cu_floor = int(floors.get("face_cu") or 2)
    l4_floor = int(floors.get("l4") or 2)
    lines = [
        f"poses: {len(poses)}/{pose_floor} → {', '.join(poses) or '—'}",
        f"face_CU: {face_cu}/{cu_floor} · L4: {l4}/{l4_floor}",
        f"cameras: {len(unique_cameras)} → {', '.join(unique_cameras) or '—'}",
        f"shot_sizes: {len(unique_sizes)} → {', '.join(unique_sizes) or '—'}",
        f"speakers: {len(unique_speakers)} → {', '.join(unique_speakers) or '—'}",
        f"variety_ok: {bool(variety.get('ok'))}",
    ]
    return {
        "poses": poses,
        "pose_count": len(poses),
        "face_cu_count": face_cu,
        "l4_insert_count": l4,
        "cameras": unique_cameras,
        "shot_sizes": unique_sizes,
        "speakers": unique_speakers,
        "variety_ok": bool(variety.get("ok")) if variety else None,
        "floors": {"poses": pose_floor, "face_cu": cu_floor, "l4": l4_floor},
        "summary_lines": lines,
        "matrix_md": variety.get("matrix_md"),
    }


def design_go(root: Path | str, *, write: bool = True) -> dict[str, Any]:
    """S3 · design-phase one-page GO (never signs pilot)."""
    root_p = _root(root)
    debrief = _load_debrief(root_p)
    debrief_meta = _score_debrief_contract(debrief)[1]
    fid = fidelity_check(root_p, write=write)
    variety: dict[str, Any] = {}
    try:
        from workflow_pack import variety_precheck

        variety = variety_precheck(root_p, write=False)
    except Exception as exc:  # noqa: BLE001
        variety = {"ok": False, "error": str(exc)[:160]}

    craft = _craft_onepager(root_p, variety if isinstance(variety, dict) else {})

    checks = {
        "debrief_present": bool(debrief_meta.get("present")),
        "debrief_confirmed": bool(debrief_meta.get("confirmed")),
        "fidelity_ok": bool(fid.get("ok")),
        "fidelity_score": fid.get("score"),
        "entity_coverage": (fid.get("entity_coverage") or {}).get("score"),
        "must_keep_mapped": (fid.get("must_keep_map") or {}).get("score") == 1.0
        or not fid.get("must_keep"),
        "variety_ok": bool(variety.get("ok")) if variety else None,
        "craft_onepager": True,
    }
    blockers: list[str] = []
    if not checks["debrief_present"]:
        blockers.append("debrief_missing")
    if checks["debrief_present"] and not checks["debrief_confirmed"]:
        blockers.append("debrief_unconfirmed")
    if not checks["fidelity_ok"]:
        blockers.append("fidelity_not_ok")
    if checks["variety_ok"] is False:
        blockers.append("variety_precheck")

    ok = not blockers
    report = {
        "kind": "design-go",
        "ok": ok,
        "go_ready": ok,
        "checks": checks,
        "blockers": blockers,
        "fidelity_codes": fid.get("codes"),
        "promise_ref": fid.get("promise_ref"),
        "must_keep": fid.get("must_keep"),
        "craft_onepager": craft,
        "next_cmd": (
            'aifilm pilot pack --root "<film>"'
            if ok
            else (fid.get("next_cmd") or 'aifilm fidelity apply --root "<film>"')
        ),
        "note": "design-go never signs pilot; human pilot approve still required",
        "generated_at": utc_now(),
    }
    if write:
        path = root_p / "receipts" / "design-go.json"
        write_json(path, report)
        report["receipt"] = str(path)
        md_path = root_p / "receipts" / "design-go-onepager.md"
        md_lines = [
            "# Design GO one-pager",
            "",
            f"- go_ready: **{ok}**",
            f"- promise: {report.get('promise_ref') or '—'}",
            "",
            "## Craft matrix",
            *[f"- {line}" for line in craft.get("summary_lines") or []],
            "",
            "## Blockers",
            *([f"- {b}" for b in blockers] if blockers else ["- (none)"]),
            "",
            f"next: `{report['next_cmd']}`",
            "",
        ]
        if craft.get("matrix_md"):
            md_lines.extend(["## Variety matrix", str(craft["matrix_md"]), ""])
        md_path.write_text("\n".join(md_lines), encoding="utf-8")
        report["onepager_md"] = str(md_path)
    return report


def human_fidelity_summary(report: dict[str, Any]) -> str:
    """F3 · three-line human summary for review-final / closeout."""
    promise = _text(report.get("promise_ref")) or "(no promise)"
    mk = report.get("must_keep") or []
    mk_map = report.get("must_keep_map") or {}
    unmapped = mk_map.get("unmapped") or []
    prot = report.get("protected_dialogue_coverage") or {}
    missing = prot.get("missing") or []
    line1 = f"promise: {promise[:100]}"
    line2 = f"must_keep: {len(mk)} total, unmapped={len(unmapped)}" + (
        f" ({', '.join(unmapped[:4])})" if unmapped else " (ok)"
    )
    line3 = f"protected_dialogue missing: {len(missing)}" + (
        f" — {'; '.join(str(m)[:20] for m in missing[:3])}" if missing else " (ok)"
    )
    return "\n".join([line1, line2, line3])


def fidelity_status(root: Path | str) -> dict[str, Any]:
    """Read last receipt or compute without requiring write (always recomputes light)."""
    root_p = _root(root)
    existing = read_json(receipt_path(root_p))
    report = build_input_fidelity_report(root_p, write=False)
    report["previous_receipt"] = bool(existing)
    if existing and isinstance(existing, dict):
        report["previous_score"] = existing.get("score")
        report["previous_ok"] = existing.get("ok")
    return report


def fidelity_check(
    root: Path | str,
    *,
    strict: bool | None = None,
    write: bool = True,
) -> dict[str, Any]:
    return build_input_fidelity_report(root, strict=strict, write=write)


def assert_fidelity_allows_final(
    root: Path | str,
    *,
    floor: float = DEFAULT_FINAL_FLOOR,
) -> dict[str, Any]:
    """Optional hard gate for final/export (Wave F3). Respects skip env."""
    try:
        from core.skip_audit import skip_flag

        if skip_flag(
            "AIFILM_SKIP_FIDELITY_FINAL_GATE",
            origin="env",
            film_root=root,
            call_site="assert_fidelity_allows_final",
        ):
            return {"ok": True, "skipped": True, "reason": "AIFILM_SKIP_FIDELITY_FINAL_GATE"}
    except Exception:
        if (os.environ.get("AIFILM_SKIP_FIDELITY_FINAL_GATE") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return {"ok": True, "skipped": True, "reason": "AIFILM_SKIP_FIDELITY_FINAL_GATE"}
    report = build_input_fidelity_report(root, write=True)
    report["human_summary"] = human_fidelity_summary(report)
    score = float(report.get("score") or 0.0)
    # Hard only when strict mode already true; soft otherwise (never silent block soft films)
    if report.get("strict") and score < floor:
        raise InputFidelityError(
            "input fidelity below final floor "
            f"({score} < {floor}); codes={report.get('codes')}\n"
            f"{report['human_summary']}"
        )
    if report.get("strict") and report.get("blocking_codes"):
        raise InputFidelityError(
            "input fidelity blocking codes: "
            f"{report.get('blocking_codes')}\n{report['human_summary']}"
        )
    return report
