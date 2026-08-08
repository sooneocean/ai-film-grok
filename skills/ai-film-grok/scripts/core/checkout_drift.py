"""Dual-checkout drift probe (honesty-rail R3 · 2026-08-07).

Compares the plugin load tree vs the optional dev git checkout using only
``git rev-parse`` / ``git status`` / ``git rev-list`` — never file-copy.

Non-git / missing trees → soft warn, never break core doctor green.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

try:
    from util.logger import log
except Exception:  # pragma: no cover  # noqa: BLE001
    log = None  # type: ignore[assignment]

# Canonical paths from AGENTS.md (macOS dex layout; overridable via env later if needed)
DEFAULT_PLUGIN = Path.home() / ".grok" / "plugins" / "ai-film-grok"
DEFAULT_DEV = Path.home() / ".grok" / "ai-film-grok"


def _run_git(cwd: Path, *args: str, timeout: float = 8.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        if log is not None:
            log.debug("checkout_drift git failed cwd=%s args=%s err=%s", cwd, args, exc)
        return 127, "", str(exc)[:200]


def _is_git_root(path: Path) -> bool:
    if not path.is_dir():
        return False
    code, out, _ = _run_git(path, "rev-parse", "--is-inside-work-tree")
    return code == 0 and out.lower() == "true"


def _head(path: Path) -> str | None:
    code, out, _ = _run_git(path, "rev-parse", "HEAD")
    return out if code == 0 and out else None


def _toplevel(path: Path) -> str | None:
    code, out, _ = _run_git(path, "rev-parse", "--show-toplevel")
    return out if code == 0 and out else None


def _porcelain(path: Path, *, limit: int = 40) -> list[str]:
    code, out, _ = _run_git(path, "status", "--porcelain")
    if code != 0 or not out:
        return []
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return lines[:limit]


def check_checkout_drift(
    *,
    plugin_path: Path | str | None = None,
    dev_path: Path | str | None = None,
) -> dict[str, Any]:
    """Return drift report. ``status``: clean | drift | missing | non_git | error."""
    plugin = Path(plugin_path or DEFAULT_PLUGIN).expanduser()
    dev = Path(dev_path or DEFAULT_DEV).expanduser()
    report: dict[str, Any] = {
        "kind": "checkout-drift",
        "plugin_path": str(plugin),
        "dev_path": str(dev),
        "ok": True,  # soft by default for doctor
        "status": "clean",
        "advisory": True,
        "note": "",
        "next": [],
        "forbid": ["manual file copy between checkouts — use git only"],
    }

    plugin_git = _is_git_root(plugin)
    dev_git = _is_git_root(dev)

    if not plugin.exists() and not dev.exists():
        report["status"] = "missing"
        report["note"] = "neither plugin nor dev checkout path exists"
        report["ok"] = True
        return report

    if not plugin_git and not dev_git:
        report["status"] = "non_git"
        report["note"] = "no git worktree at expected paths (CI/plugin-validate safe)"
        report["ok"] = True
        return report

    if plugin_git:
        report["plugin_toplevel"] = _toplevel(plugin)
        report["plugin_head"] = _head(plugin)
        report["plugin_dirty"] = _porcelain(plugin)
    else:
        report["plugin_note"] = "plugin path not a git worktree"

    if dev_git:
        report["dev_toplevel"] = _toplevel(dev)
        report["dev_head"] = _head(dev)
        report["dev_dirty"] = _porcelain(dev)
    else:
        report["dev_note"] = "dev path missing or not a git worktree"
        if plugin_git:
            report["status"] = "missing"
            report["note"] = "dev checkout absent; plugin-only is OK for runtime"
            report["ok"] = True
        return report

    if not plugin_git:
        report["status"] = "missing"
        report["note"] = "plugin path not git; cannot compare"
        report["ok"] = True
        return report

    ph = report.get("plugin_head")
    dh = report.get("dev_head")
    dirty_p = list(report.get("plugin_dirty") or [])
    dirty_d = list(report.get("dev_dirty") or [])
    heads_differ = bool(ph and dh and ph != dh)
    dirty = bool(dirty_p or dirty_d)

    report["heads_match"] = bool(ph and dh and ph == dh)
    report["plugin_dirty_count"] = len(dirty_p)
    report["dev_dirty_count"] = len(dirty_d)

    if not heads_differ and not dirty:
        report["status"] = "clean"
        report["note"] = "plugin and dev heads match; working trees clean"
        report["ok"] = True
        report["warn"] = False
        return report

    # Dirty-only (same HEAD) is informational — common with local artifacts.
    # Real drift warn = HEAD mismatch (optionally plus dirty).
    bits: list[str] = []
    if heads_differ:
        bits.append(f"HEAD differ plugin={str(ph)[:10]}… dev={str(dh)[:10]}…")
        code, out, _ = _run_git(plugin, "rev-list", "--left-right", "--count", f"{dh}...{ph}")
        if code == 0 and out:
            report["rev_count_left_right"] = out
    if dirty_p:
        bits.append(f"plugin dirty files={len(dirty_p)}")
    if dirty_d:
        bits.append(f"dev dirty files={len(dirty_d)}")

    report["status"] = "drift" if heads_differ else "dirty"
    report["ok"] = True
    if log is not None:
        log.info(
            "checkout_drift status=%s heads_differ=%s dirty_p=%s dirty_d=%s",
            report["status"],
            heads_differ,
            len(dirty_p),
            len(dirty_d),
        )
    report["warn"] = bool(heads_differ)  # only HEAD mismatch escalates to doctor warning
    report["note"] = "; ".join(bits) or "checkout state noted"
    report["next"] = [
        "cd ~/.grok/plugins/ai-film-grok && git status && git log -1 --oneline",
        "cd ~/.grok/ai-film-grok && git fetch && git status",
        "sync with git only (ff-merge / pull); NEVER hand-copy files between trees",
    ]
    report["drift_files"] = {
        "plugin": dirty_p[:20],
        "dev": dirty_d[:20],
    }
    return report
