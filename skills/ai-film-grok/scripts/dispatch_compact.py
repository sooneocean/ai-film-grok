#!/usr/bin/env python3
"""Compact agent-facing dispatch projection and orchestration-only metrics."""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from context_routing import select_context_refs
from workflow_spine import public_flow_phase

_STATE_SUFFIXES = {".json", ".md", ".txt", ".srt"}
_STATE_IGNORES = {
    "dispatch.json",
    "capability-cache.json",
    "orchestration-usage.jsonl",
    "pipeline_stage.json",
    "scene-sound-status.json",
}
HARD_GATE_CODES = [
    "WRITE_SPEC_REQUIRED",
    "PILOT_USER_APPROVAL_REQUIRED",
    "SILENT_PROVIDER_SWITCH_FORBIDDEN",
    "FINAL_HUMAN_REVIEW_REQUIRED",
    "STATE_INDEX_REQUIRED",
    "NARRATIVE_PROJECTION_CURRENT_REQUIRED",
    "PRODUCTION_EVIDENCE_REQUIRED",
    "HERO_QUALITY_RECEIPT_REQUIRED",
    "PROVIDER_FALLBACK_REPILOT_REQUIRED",
    "HEAT_AGENT_HARD_FAIL",
    "HEAT_FINAL_NOT_OK",
]


def _json_bytes(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def estimated_tokens(value: object) -> int:
    """Cheap, explicitly estimated orchestration token count."""
    return math.ceil(_json_bytes(value) / 4)


def _bounded_text(value: object, *, max_bytes: int) -> str | None:
    if value is None:
        return None
    raw = str(value)
    encoded = raw.encode("utf-8")
    if len(encoded) <= max_bytes:
        return raw
    suffix = "…（详见完整回执）"
    budget = max(0, max_bytes - len(suffix.encode("utf-8")))
    prefix = encoded[:budget]
    while prefix:
        try:
            return prefix.decode("utf-8") + suffix
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    return suffix


def compute_state_hash(
    root: Path,
    *,
    gates: dict[str, Any] | None = None,
    open_reshoot_count: int = 0,
) -> str:
    """Hash control-plane text inputs while excluding generated dispatch telemetry."""
    root = Path(root).expanduser().resolve()
    digest = hashlib.sha256()
    digest.update(str(root).encode("utf-8"))
    digest.update(b"\0")
    digest.update(
        json.dumps(
            {"gates": gates or {}, "open_reshoot_count": open_reshoot_count},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if not root.is_dir():
        return digest.hexdigest()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _STATE_SUFFIXES:
            continue
        if path.name in _STATE_IGNORES:
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(
            part in {"out", "clips", "keyframes", ".cache", "_final_work"} for part in rel.parts
        ):
            continue
        if rel.parts[:2] == ("receipts", "transactions"):
            continue
        try:
            size = path.stat().st_size
            if size > 4 * 1024 * 1024:
                continue
            digest.update(str(rel).encode("utf-8"))
            digest.update(b"\0")
            if path.name == "manifest.json":
                manifest = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(manifest, dict):
                    manifest.pop("updated_at", None)
                digest.update(
                    json.dumps(
                        manifest,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
            else:
                digest.update(path.read_bytes())
            digest.update(b"\0")
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    referenced_media: set[str] = set()
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
        referenced_media.update(
            str(item.get("path") or "")
            for item in clips.values()
            if isinstance(item, dict) and item.get("status") == "approved"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    try:
        dailies = json.loads((root / "receipts" / "dailies.json").read_text(encoding="utf-8"))
        referenced_media.update(
            str(item.get("candidate") or "")
            for items in (dailies.get("shots") or {}).values()
            for item in (items if isinstance(items, list) else [])
            if isinstance(item, dict)
        )
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    for value in sorted(item for item in referenced_media if item):
        media = Path(value).expanduser()
        if not media.is_absolute():
            media = root / media
        try:
            relative = media.resolve().relative_to(root)
            digest.update(str(relative).encode("utf-8"))
            digest.update(b"\0")
            with media.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
        except (OSError, ValueError):
            digest.update(f"missing:{value}".encode())
    return digest.hexdigest()


def _attention(packet: dict[str, Any]) -> list[dict[str, str]]:
    attention: list[dict[str, str]] = []
    action = packet.get("next_action") if isinstance(packet.get("next_action"), dict) else {}
    if action.get("approval_class") == "human_required":
        attention.append(
            {
                "code": "HUMAN_APPROVAL_REQUIRED",
                "severity": "stop",
                "summary": "下一动作涉及用户批准、付费或外部服务；不得自动执行。",
            }
        )
    narrative = (
        packet.get("narrative_control") if isinstance(packet.get("narrative_control"), dict) else {}
    )
    for code in narrative.get("issue_codes") or []:
        attention.append(
            {
                "code": str(code),
                "severity": "block",
                "summary": "叙事控制存在阻断；按错误码加载对应阶段卡。",
            }
        )
    quality = packet.get("quality") if isinstance(packet.get("quality"), dict) else {}
    if int(quality.get("failed_count") or 0) > 0:
        attention.append(
            {
                "code": "QUALITY_GATE_FAILED",
                "severity": "block",
                "summary": "质量回执未通过，先修上游再重新生成。",
            }
        )
    post = packet.get("post_audit") if isinstance(packet.get("post_audit"), dict) else {}
    if int(post.get("hard_failure_count") or 0) > 0:
        attention.append(
            {
                "code": "POST_AUDIT_FAILED",
                "severity": "block",
                "summary": "后期审计存在硬失败，禁止宣称 final_complete。",
            }
        )
    heat = packet.get("heat") if isinstance(packet.get("heat"), dict) else {}
    if heat.get("active") and heat.get("hard_fail"):
        attention.append(
            {
                "code": "HEAT_AGENT_HARD_FAIL",
                "severity": "block",
                "summary": _bounded_text(
                    heat.get("why")
                    or "成人 max 尺度未达标 — 先 heat boost 再 bulk/final（media-queue 硬拦）",
                    max_bytes=240,
                )
                or "成人 max 尺度未达标",
            }
        )
    elif heat.get("active") and heat.get("final_ok") is False:
        attention.append(
            {
                "code": "HEAT_FINAL_NOT_OK",
                "severity": "block",
                "summary": _bounded_text(
                    heat.get("why")
                    or "成人 max 未达 final_ok（需 impact≥S）— 先 heat boost 再 final/export",
                    max_bytes=240,
                )
                or "成人 max final 尺度未满",
            }
        )
    elif heat.get("active") and heat.get("needs_boost"):
        attention.append(
            {
                "code": "HEAT_NEEDS_BOOST",
                "severity": "info",
                "summary": "成人 max impact/ecchi 未拉满 S 档 — bulk 前建议 heat boost；final 硬拦。",
            }
        )
    if not packet.get("next_action"):
        attention.append(
            {
                "code": "NO_EXECUTABLE_NEXT_ACTION",
                "severity": "info",
                "summary": "当前没有可直接执行的结构化动作；读取 next_why 或完整回执。",
            }
        )
    return attention[:8]


def _public_phase(packet: dict[str, Any]) -> dict[str, Any]:
    """Project legacy/professional state onto the one seven-step user flow."""
    workflow = packet.get("workflow") if isinstance(packet.get("workflow"), dict) else {}
    if workflow:
        return public_flow_phase(workflow)
    # Lightweight callers and older receipts may not carry workflow yet.
    craft = str(packet.get("craft_stage") or "idea")
    fallback_stage = {
        "idea": "concept_lock",
        "story": "script_lock",
        "beats": "shot_animatic_lock",
        "shots": "shot_animatic_lock",
        "media": "bulk",
        "selects": "dailies_review",
        "rough": "selects_rough_cut",
        "verified": "master_lock",
    }.get(craft, "concept_lock")
    return public_flow_phase({"current_stage": fallback_stage})


def _optional_actions(packet: dict[str, Any]) -> list[dict[str, str]]:
    """Expose alternatives as deliberately non-primary, non-executable summaries."""
    primary_id = str(packet.get("next_id") or "")
    optional: list[dict[str, str]] = []
    for action in packet.get("next_actions") or []:
        if not isinstance(action, dict) or str(action.get("id") or "") == primary_id:
            continue
        action_id = str(action.get("id") or "")
        why = _bounded_text(action.get("why"), max_bytes=280)
        if not action_id or not why:
            continue
        optional.append({"id": action_id, "why": why})
        if len(optional) == 3:
            break
    return optional


def compact_dispatch(packet: dict[str, Any]) -> dict[str, Any]:
    """Project the full audit packet into the default agent-facing schema."""
    attention = _attention(packet)
    issue_codes = [item["code"] for item in attention]
    action = packet.get("next_action") if isinstance(packet.get("next_action"), dict) else {}
    refs = select_context_refs(
        craft_stage=str(packet.get("craft_stage") or "idea"),
        pipeline_stage=str(packet.get("pipeline_stage") or "agent"),
        skill_id=str(action.get("skill_id") or ""),
        issue_codes=issue_codes,
    )
    full_bytes = _json_bytes(packet)
    base_metrics = packet.get("metrics") if isinstance(packet.get("metrics"), dict) else {}
    phase = _public_phase(packet)
    blockers = [
        {"code": item["code"], "summary": item["summary"]}
        for item in attention
        if item["severity"] in {"block", "stop"} or item["code"] == "NO_EXECUTABLE_NEXT_ACTION"
    ]
    compact = {
        "ok": bool(packet.get("ok")),
        "kind": "ai-film-dispatch",
        "schema_version": 4,
        "full_schema_version": packet.get("schema_version"),
        "mode": "compact",
        "at": packet.get("at"),
        "root": packet.get("root"),
        "craft_stage": packet.get("craft_stage"),
        "pipeline_stage": packet.get("pipeline_stage"),
        # The sole user-facing progress model.  `workflow` remains below as a
        # diagnostic compatibility projection for existing callers.
        "phase": phase,
        "next_id": packet.get("next_id"),
        "next_cmd": _bounded_text(packet.get("next_cmd"), max_bytes=1536),
        "next_why": _bounded_text(packet.get("next_why"), max_bytes=768),
        # The bound action is the execution contract. Compact mode may omit
        # surrounding diagnostics, but it must never alter this contract.
        "next_action": dict(action),
        "responsibility": packet.get("responsibility"),
        "department_handoff": packet.get("department_handoff"),
        # Weapon selection is also a bound orchestration contract. Keeping the
        # same object prevents compact/full mode from choosing different tools.
        "weapon_route": packet.get("weapon_route"),
        "workflow": {
            "public_entry": (packet.get("workflow") or {}).get("public_entry"),
            "mode": (packet.get("workflow") or {}).get("mode"),
            "current_stage": (packet.get("workflow") or {}).get("current_stage"),
            "current_label_zh": (packet.get("workflow") or {}).get("current_label_zh"),
            "stage_index": (packet.get("workflow") or {}).get("stage_index"),
            "stage_total": (packet.get("workflow") or {}).get("stage_total"),
            "blocking": (packet.get("workflow") or {}).get("blocking"),
        },
        "blocked_by": blockers,
        "required_proof": phase["proof"],
        "optional_actions": _optional_actions(packet),
        "attention": attention,
        "hard_gate_codes": HARD_GATE_CODES,
        "context_refs": refs,
        "state_hash": packet.get("state_hash"),
        "receipt_path": packet.get("receipt_path"),
        "metrics": {
            "build_elapsed_ms": base_metrics.get("build_elapsed_ms"),
            "state_cache_hit": bool(base_metrics.get("state_cache_hit")),
            "capability_cache_hit": bool(base_metrics.get("capability_cache_hit")),
            "full_bytes": full_bytes,
            "output_bytes": 0,
            "estimated_tokens": 0,
            "context_ref_count": len(refs),
            "context_ref_bytes": sum(int(ref.get("bytes") or 0) for ref in refs),
            "estimator": "utf8_bytes_div_4",
        },
    }
    # F0/S1 · input fidelity one-liner (score + worst code)
    try:
        root_s = str(packet.get("root") or "")
        if root_s:
            from input_fidelity import fidelity_status, human_fidelity_summary

            _fid = fidelity_status(root_s)
            if _fid.get("has_source") or _fid.get("shot_count"):
                codes = _fid.get("codes") or []
                worst = str(codes[0]) if codes else "ok"
                compact["fidelity"] = {
                    "ok": bool(_fid.get("ok")),
                    "score": _fid.get("score"),
                    "worst_code": worst,
                    "summary": _bounded_text(
                        human_fidelity_summary(_fid).replace("\n", " | "),
                        max_bytes=240,
                    ),
                }
                if not _fid.get("ok") and "FIDELITY_NOT_OK" not in issue_codes:
                    attention.append(
                        {
                            "code": "FIDELITY_NOT_OK",
                            "severity": "info",
                            "summary": (
                                f"input fidelity score={_fid.get('score')} "
                                f"codes={','.join(str(c) for c in codes[:3]) or '—'}"
                            ),
                        }
                    )
                    compact["attention"] = attention[:8]
    except Exception:
        pass

    # Wave 5: slim heat surface for agent loops (only when adult-max active)
    heat = packet.get("heat") if isinstance(packet.get("heat"), dict) else None
    if heat and heat.get("active"):
        compact["heat"] = {
            "active": True,
            "hard_fail": bool(heat.get("hard_fail")),
            "needs_boost": bool(heat.get("needs_boost")),
            "final_ok": bool(heat.get("final_ok")),
            "score": heat.get("score"),
            "grade": heat.get("grade"),
            "target_s": heat.get("target_s"),
            "ecchi_score": heat.get("ecchi_score"),
            "next_cmd": _bounded_text(heat.get("next_cmd"), max_bytes=512),
        }
        compact["metrics"]["heat_score"] = heat.get("score")
        compact["metrics"]["heat_hard_fail"] = bool(heat.get("hard_fail"))
        compact["metrics"]["heat_final_ok"] = bool(heat.get("final_ok"))
    compact["metrics"]["output_bytes"] = _json_bytes(compact)
    compact["metrics"]["estimated_tokens"] = estimated_tokens(compact)
    if compact["metrics"]["output_bytes"] > 5000:
        compact["next_cmd"] = _bounded_text(compact.get("next_cmd"), max_bytes=512)
        compact["next_why"] = "内容过长；详见完整回执。"
        compact["metrics"]["output_bytes"] = _json_bytes(compact)
        compact["metrics"]["estimated_tokens"] = estimated_tokens(compact)
    return compact


def record_orchestration_metrics(root: Path, compact: dict[str, Any]) -> Path:
    """Append only dispatch telemetry; never generation cost, prompts or credentials."""
    root = Path(root).expanduser().resolve()
    path = root / "receipts" / "orchestration-usage.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = compact.get("metrics") if isinstance(compact.get("metrics"), dict) else {}
    record = {
        "schema_version": 1,
        "kind": "orchestration-usage",
        "at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "state_hash": compact.get("state_hash"),
        "craft_stage": compact.get("craft_stage"),
        "pipeline_stage": compact.get("pipeline_stage"),
        "next_id": compact.get("next_id"),
        "build_elapsed_ms": metrics.get("build_elapsed_ms"),
        "state_cache_hit": bool(metrics.get("state_cache_hit")),
        "capability_cache_hit": bool(metrics.get("capability_cache_hit")),
        "full_bytes": metrics.get("full_bytes"),
        "output_bytes": metrics.get("output_bytes"),
        "estimated_tokens": metrics.get("estimated_tokens"),
        "context_ref_count": metrics.get("context_ref_count"),
        "context_ref_bytes": metrics.get("context_ref_bytes"),
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return path
