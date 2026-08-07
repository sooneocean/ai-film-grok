"""Preflight issue reporting helpers (peeled leaf module for gates/preflight.py)."""

from __future__ import annotations

from typing import Any


def _issue(level: str, code: str, msg: str, *, fix: str = "") -> dict[str, str]:
    out = {"level": level, "code": code, "message": msg}
    if fix:
        out["fix"] = fix
    return out


def _is_heat_max_iron(spec: dict[str, Any] | None) -> bool:
    """True when adult max/hot/extreme IRON should fail-closed on heat probes."""
    if not isinstance(spec, dict):
        return False
    hs = str(spec.get("heat_scale") or "").lower()
    if hs not in {"max", "hot", "extreme"}:
        return False
    return spec.get("adult_max_iron") is not False


def _append_probe_error(
    hard: list[dict[str, str]],
    soft: list[dict[str, str]],
    *,
    code: str,
    exc: BaseException,
    fix: str = "",
    hard_mode: bool = False,
) -> None:
    """A1 · never swallow probe failures as silent green."""
    sev = "hard" if hard_mode else "soft"
    msg = f"{code}: {exc}"[:220]
    iss = _issue(sev, code, msg, fix=fix or "check preflight probe import / film-spec")
    if hard_mode:
        hard.append(iss)
    else:
        soft.append(iss)
