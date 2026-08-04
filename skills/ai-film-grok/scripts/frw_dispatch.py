#!/usr/bin/env python3
"""Thin launcher for the installed frwclaw-pro official CLI contract.

Used by ai-film-grok for catalog-driven FRW video work, including LTX 2.3
``img2video-audio`` for an explicitly reviewed dialogue performance candidate.
It supports both the current root launcher (``frwclaw-pro``) and the retired
``img-video-frw/scripts/dispatch.py`` layout during local migrations.

Usage:
  frw_dispatch.py help
  # Key capability canary (writes receipts when --root given):
  frw_dispatch.py canary [--root FILM_ROOT] [--wait] [--full]
  # Catalog-driven A/B control plane:
  frw_dispatch.py ab catalog [--root FILM_ROOT]
  frw_dispatch.py ab plan|run|poll|rank|approve|status ...
  # DEFAULT bulk I2V (quality):
  frw_dispatch.py newvideo --model seedance-2-fast-i2v \\
    --img-url URL --prompt "@Image1 …" \\
    --aspect-ratio 9:16 --resolution 720p --duration 5 --wait
  frw_dispatch.py newvideo-query --task-id ID --wait
  # FLF:
  frw_dispatch.py newvideo --model seedance-2-pro-flf \\
    --img1 URL --img2 URL --prompt "@Image1 @Image2 …" --aspect-ratio 9:16 --wait
  frw_dispatch.py upload --file-path /path/to/keyframe.png --category image
  # Native-audio dialogue candidate (must pass native-text and human review):
  frw_dispatch.py img2video-audio --img-url URL \
    --prompt "Japanese dialogue; no visible text, subtitles, captions, or watermark" --wait

Env:
  FRWCLAW_ROOT    override skill root
  FRWCLAW_PYTHON  override interpreter (default: $FRWCLAW_ROOT/.venv/bin/python)
  FRW_API_KEY     from env or frwclaw-pro/.env
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def run_canary(argv: list[str]) -> int:
    """Local canary — does not proxy to frwclaw dispatch."""
    canary = Path(__file__).resolve().parent / "frw_canary.py"
    if not canary.is_file():
        print(
            f'{{"protocol_version":"1.0","success":false,"user_reply":"missing {canary.name}"}}',
            file=sys.stderr,
        )
        return 1
    # Prefer frwclaw venv only if present; canary is stdlib-only so system py is fine
    proc = subprocess.run(
        [sys.executable, str(canary), *argv],
        timeout=120,
        check=False,
    )
    return proc.returncode


def _current_launcher(root: Path) -> Path | None:
    launcher = root / "frwclaw-pro"
    return launcher if launcher.is_file() else None


def _legacy_dispatch(root: Path) -> Path | None:
    dispatch = root / "img-video-frw" / "scripts" / "dispatch.py"
    return dispatch if dispatch.is_file() else None


def is_supported_frw_root(root: Path) -> bool:
    """Whether *root* exposes a known, runnable frwclaw-pro entry point."""
    return _current_launcher(root) is not None or _legacy_dispatch(root) is not None


def build_dispatch_command(root: Path, argv: list[str]) -> list[str]:
    """Build the command without ever placing FRW credentials in argv."""
    launcher = _current_launcher(root)
    if launcher is not None:
        return [str(launcher), *argv]
    dispatch = _legacy_dispatch(root)
    if dispatch is not None:
        return [resolve_python(root), str(dispatch), *argv]
    # ``resolve_frw_root`` verifies real roots before this helper is reached.
    # Retaining the legacy shape here keeps the launcher independently testable
    # when callers inject a root in a subprocess contract test.
    return [resolve_python(root), str(root / "img-video-frw" / "scripts" / "dispatch.py"), *argv]


def run_upload_probe(argv: list[str]) -> int:
    """Run the no-paid upload authorization canary and redact provider URLs."""
    if "--file-path" not in argv:
        print(json.dumps({"ok": False, "error": "upload-probe requires --file-path"}))
        return 2
    root = resolve_frw_root()
    if _current_launcher(root) is not None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "command": "upload-probe",
                    "error": "FRW_UPLOAD_PROBE_UNAVAILABLE_CURRENT_PACKAGE",
                    "next": "run an explicit reviewed `aifilm frw upload` when upload is authorized",
                },
                ensure_ascii=False,
            )
        )
        return 2
    env = os.environ.copy()
    load_dotenv(root, env)
    env["PYTHONPATH"] = ""
    cmd = build_dispatch_command(root, ["upload-canary", *argv])
    try:
        proc = subprocess.run(
            cmd, env=env, cwd=str(root), timeout=120, capture_output=True, text=True
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": f"upload-probe failed: {exc}"}))
        return 1
    payload: object = {}
    for line in reversed((proc.stdout or "").splitlines()):
        try:
            payload = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    if isinstance(payload, dict):
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        print(
            json.dumps(
                {
                    "ok": proc.returncode == 0
                    and bool(payload.get("success", payload.get("ok", False))),
                    "command": "upload-canary",
                    "status": payload.get("success", payload.get("ok")),
                    "error_code": data.get("error_code"),
                },
                ensure_ascii=False,
            )
        )
    else:
        print(
            json.dumps(
                {"ok": False, "command": "upload-canary", "error": "invalid provider response"}
            )
        )
    return proc.returncode


def run_ab(argv: list[str]) -> int:
    """Run the local catalog-driven A/B control plane."""
    from frw_ab import main as ab_main

    return int(ab_main(argv))


def resolve_frw_root() -> Path:
    env = os.environ.get("FRWCLAW_ROOT", "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    home = Path.home()
    candidates.extend(
        [
            home / ".hermes" / "skills" / "frwclaw-pro",
            home / ".agents" / "skills" / "frwclaw-pro",
        ]
    )
    for root in candidates:
        if is_supported_frw_root(root):
            return root.resolve()
    raise SystemExit(
        "frw_dispatch: cannot find frwclaw-pro with a current launcher or legacy dispatch.py. "
        "Install/sync frwclaw-pro or set FRWCLAW_ROOT. "
        "See references/frw-degrade-dispatch.md"
    )


def resolve_python(root: Path) -> str:
    env = os.environ.get("FRWCLAW_PYTHON", "").strip()
    if env and Path(env).expanduser().is_file():
        return str(Path(env).expanduser())
    venv_py = root / ".venv" / "bin" / "python"
    try:
        if venv_py.is_file() and venv_py.resolve().exists():
            return str(venv_py)
    except OSError:
        pass
    return sys.executable


def load_dotenv(root: Path, env: dict[str, str]) -> None:
    dotenv = root / ".env"
    if not dotenv.is_file():
        return
    for line in dotenv.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in env:
            env[k] = v


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        argv = ["help"]

    # Local capability probe (stdlib) — before frwclaw resolve
    if argv and argv[0] == "canary":
        return run_canary(argv[1:])
    if argv and argv[0] == "upload-probe":
        return run_upload_probe(argv[1:])
    if argv and argv[0] == "ab":
        return run_ab(argv[1:])

    root = resolve_frw_root()
    env = os.environ.copy()
    load_dotenv(root, env)
    # Avoid PYTHONPATH ABI leaks into frw venv
    env["PYTHONPATH"] = ""

    # Platform hard limit: image ≥30s, video ≥5min (shared with ai-film-frw).
    try:
        from frw_rate_limit import classify_frw_op, wait_frw_rate_limit

        kind = classify_frw_op(argv)
        if kind:
            wait_frw_rate_limit(kind)
    except Exception as rate_exc:  # noqa: BLE001 — never block auth help on rate module bugs
        print(f"frw_dispatch: rate-limit warn: {rate_exc}", file=sys.stderr)

    cmd = build_dispatch_command(root, argv)
    # Default 60s keeps CLI snappy for help/catalog; long polls set FRW_DISPATCH_TIMEOUT.
    timeout_s = int(os.environ.get("FRW_DISPATCH_TIMEOUT", "60") or "60")
    try:
        proc = subprocess.run(cmd, env=env, cwd=str(root), timeout=max(1, timeout_s))
    except OSError as exc:
        print(
            f"frw_dispatch: failed to exec FRW launcher: {exc}",
            file=sys.stderr,
        )
        return 1
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
