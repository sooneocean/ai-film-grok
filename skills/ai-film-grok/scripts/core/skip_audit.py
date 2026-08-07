"""Runtime SKIP escape audit (honesty-rail R1 · 2026-08-07).

Central helper for reading ``AIFILM_SKIP_*`` (and optional CLI origin) so every
escape can be ledgered under ``receipts/skip-usage.json``.

I4.2 iron-status lists static gates; this module records **runtime** usage.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from util.logger import log
except Exception:  # pragma: no cover - ultra-early import path
    log = None  # type: ignore[assignment]

# IRON-class escapes: closeout refuses cert / forces PARTIAL when used without reason.
IRON_SKIP_FLAGS: frozenset[str] = frozenset(
    {
        "AIFILM_SKIP_HEAT_FINAL_GATE",
        "AIFILM_SKIP_HEAT_QUEUE_GATE",
        "AIFILM_SKIP_ANTI_HIJACK",
        "AIFILM_SKIP_VARIETY_PREFLIGHT",
        "AIFILM_SKIP_VARIETY_PIXEL",
        "AIFILM_SKIP_PLATE_BORING",
        "AIFILM_SKIP_ANATOMY_SAFETY",
        "AIFILM_SKIP_GENERATION_REQUEST",
        "AIFILM_SKIP_ENDFRAME_WARDROBE",
        "AIFILM_SKIP_SCALE_PROMOTE_GATE",
        "AIFILM_SKIP_GATE_AUTO",
        "AIFILM_SKIP_TRUE_VIDEO_POLICY",
        "AIFILM_SKIP_I2V_MOTION_GATE",
        "AIFILM_SKIP_CINEMATIC_GATE",
        "AIFILM_SKIP_LOOP_RISK_GATE",
        "AIFILM_SKIP_PILOT_GATE",
        "AIFILM_SKIP_ANTI_BORING_GATE",
        "AIFILM_SKIP_HEADROOM_GATE",
        "AIFILM_SKIP_TRANSITION_POLICY_GATE",
        "AIFILM_SKIP_TRANSITION_READBACK_GATE",
        "AIFILM_SKIP_STYLE_BIBLE_GATE",
        "AIFILM_SKIP_FACE_IDENTITY_GATE",
        "AIFILM_SKIP_CONTINUITY_GATE",
    }
)

USAGE_REL = "receipts/skip-usage.json"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def normalize_skip_name(name: str) -> str:
    n = str(name or "").strip()
    if not n:
        return ""
    if n.upper().startswith("AIFILM_SKIP_"):
        return n.upper() if n.startswith("AIFILM_") else n
    # allow bare HEAT_FINAL_GATE
    bare = n.upper()
    if bare.startswith("SKIP_"):
        bare = bare[len("SKIP_") :]
    if bare.startswith("AIFILM_"):
        return bare
    return f"AIFILM_SKIP_{bare}"


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def is_iron_skip(name: str) -> bool:
    return normalize_skip_name(name) in IRON_SKIP_FLAGS


def load_skip_usage(root: Path | str | None) -> dict[str, Any]:
    if root is None:
        return {"schema_version": 1, "kind": "skip-usage", "entries": []}
    base = Path(root).expanduser().resolve()
    path = base / USAGE_REL
    try:
        from util import read_json

        data = read_json(path) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    entries = data.get("entries")
    if not isinstance(entries, list):
        entries = []
    return {
        "schema_version": 1,
        "kind": "skip-usage",
        "root": str(base),
        "entries": [e for e in entries if isinstance(e, dict)],
    }


def record_skip_usage(
    root: Path | str | None,
    name: str,
    *,
    origin: str = "env",
    reason: str | None = None,
    call_site: str | None = None,
) -> dict[str, Any]:
    """Append one usage row (idempotent per name+origin in this process ledger)."""
    canon = normalize_skip_name(name)
    if not canon or root is None:
        return load_skip_usage(root)
    base = Path(root).expanduser().resolve()
    ledger = load_skip_usage(base)
    entries: list[dict[str, Any]] = list(ledger.get("entries") or [])
    for e in entries:
        if e.get("name") == canon and str(e.get("origin") or "env") == str(origin or "env"):
            # already recorded this escape for this origin
            if reason and not e.get("reason"):
                e["reason"] = str(reason)[:240]
            break
    else:
        try:
            from util import utc_now

            at = utc_now()
        except Exception:
            at = None
        entries.append(
            {
                "name": canon,
                "origin": str(origin or "env"),
                "reason": (str(reason)[:240] if reason else None),
                "call_site": (str(call_site)[:200] if call_site else None),
                "iron": canon in IRON_SKIP_FLAGS,
                "at": at,
            }
        )
    payload = {
        "schema_version": 1,
        "kind": "skip-usage",
        "root": str(base),
        "entries": entries,
        "count": len(entries),
        "iron_count": sum(1 for e in entries if e.get("iron")),
    }
    try:
        from util import write_json

        write_json(base / USAGE_REL, payload)
    except (OSError, ValueError, TypeError) as exc:
        # never break the gate path on ledger I/O; caller still gets bool
        if log is not None:
            log.warning("skip_usage ledger write failed: %s", exc)
    return payload


def skip_flag(
    name: str,
    *,
    origin: str = "env",
    film_root: Path | str | None = None,
    reason: str | None = None,
    call_site: str | None = None,
) -> bool:
    """Return True when SKIP env is armed; ledger first hit under film_root."""
    canon = normalize_skip_name(name)
    if not canon:
        return False
    if not _env_truthy(canon):
        return False
    if film_root is not None:
        record_skip_usage(
            film_root,
            canon,
            origin=origin,
            reason=reason or os.environ.get("AIFILM_SKIP_REASON"),
            call_site=call_site,
        )
    if log is not None:
        log.warning(
            "AIFILM skip armed name=%s origin=%s iron=%s call_site=%s root=%s",
            canon,
            origin,
            canon in IRON_SKIP_FLAGS,
            call_site,
            film_root,
        )
    return True


def sync_armed_env_skips(
    root: Path | str | None,
    *,
    reason: str | None = None,
    call_site: str = "sync_armed_env_skips",
) -> dict[str, Any]:
    """Scan process env for armed AIFILM_SKIP_* and ledger them (closeout pre-pass).

    Catches escapes that never went through ``skip_flag`` (legacy direct os.environ reads).
    """
    if root is None:
        return load_skip_usage(root)
    ledger = load_skip_usage(root)
    reason_eff = reason or os.environ.get("AIFILM_SKIP_REASON")
    # Prefer known IRON set + any AIFILM_SKIP_* currently in env
    candidates: set[str] = set(IRON_SKIP_FLAGS)
    for key in os.environ:
        if key.upper().startswith("AIFILM_SKIP_") and key.upper() != "AIFILM_SKIP_REASON":
            candidates.add(key.upper() if key.startswith("AIFILM_") else key)
    for name in sorted(candidates):
        if _env_truthy(name):
            record_skip_usage(
                root,
                name,
                origin="env",
                reason=reason_eff,
                call_site=call_site,
            )
    return load_skip_usage(root)


def verify_skip_usage(
    root: Path | str | None,
    *,
    sync_env: bool = True,
) -> dict[str, Any]:
    """Closeout helper: IRON skips without reason → not certifiable.

    When ``sync_env`` is True (default), first ledger any armed env escapes so
    legacy direct ``os.environ`` readers still appear in the report.
    """
    if sync_env and root is not None:
        sync_armed_env_skips(root)
    ledger = load_skip_usage(root)
    entries = list(ledger.get("entries") or [])
    iron_unreasoned: list[dict[str, Any]] = []
    for e in entries:
        if not e.get("iron"):
            continue
        if not str(e.get("reason") or "").strip():
            iron_unreasoned.append(e)
    ok = not iron_unreasoned
    skips_used = [e.get("name") for e in entries if e.get("name")]
    return {
        "ok": ok,
        "kind": "skip-usage-verify",
        "entries": entries,
        "skips_used": skips_used,
        "iron_unreasoned": [
            {"name": e.get("name"), "origin": e.get("origin")} for e in iron_unreasoned
        ],
        "partial": (not ok),
        "classification": "PARTIAL" if not ok else ("CLEAN" if not entries else "SKIP_DOCUMENTED"),
        "next_cmd": (
            None
            if ok
            else "set AIFILM_SKIP_REASON='why this IRON escape' before re-final/closeout"
        ),
    }


def attach_skips_to_report(
    report: dict[str, Any],
    root: Path | str | None,
) -> dict[str, Any]:
    """Mutate/return official-final-style report with skips_used fields."""
    ver = verify_skip_usage(root, sync_env=True)
    report = dict(report or {})
    report["skips_used"] = list(ver.get("skips_used") or [])
    report["skip_audit"] = {
        "ok": ver.get("ok"),
        "classification": ver.get("classification"),
        "iron_unreasoned": ver.get("iron_unreasoned") or [],
        "partial": ver.get("partial"),
    }
    if ver.get("partial"):
        report["partial"] = True
        limits = list(report.get("honest_limits") or [])
        if "iron_skip_unreasoned" not in limits:
            limits.append("iron_skip_unreasoned")
        report["honest_limits"] = limits
        if str(report.get("status") or "") == "TECHNICAL_FINAL":
            report["status"] = "OFFICIAL_FINAL_PLATE"
    return report
