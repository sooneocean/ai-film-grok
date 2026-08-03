#!/usr/bin/env python3
"""Start designed-post Studio preview (HyperFrames or Remotion) and surface the URL.

HyperFrames: `npx hyperframes preview --background`
Remotion: `npx remotion studio src/index.ts` (requires node_modules after npm install)

Writes receipts/compose-preview.json for --require-preview gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from logger import log
from security_policy import SecurityPolicyError, minimal_subprocess_env, safe_workspace_directory
from util import utc_now

URL_RE = re.compile(r"https?://[^\s)>\"]+")
PREVIEW_RECEIPT_REL = "receipts/compose-preview.json"
PREVIEW_META_REL = "compose/preview.json"


class ComposePreviewError(RuntimeError):
    pass


def preview_receipt_path(root: Path) -> Path:
    return Path(root).expanduser().resolve() / "receipts" / "compose-preview.json"


def load_preview_receipt(root: Path) -> dict[str, Any] | None:
    path = preview_receipt_path(root)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def has_valid_preview_receipt(root: Path) -> bool:
    """True when compose-preview wrote a usable receipt (real URL + ok).

    Fallback-only URLs (guessed localhost without process confirmation) must
    set ok=false and do not satisfy --require-preview.
    """
    rec = load_preview_receipt(root)
    if not rec:
        return False
    if rec.get("ok") is False:
        return False
    if rec.get("url_guessed") is True:
        return False
    url = rec.get("url")
    return isinstance(url, str) and url.startswith("http")


def write_preview_receipt(
    root: Path,
    *,
    url: str,
    hf_dir: str,
    already_running: bool = False,
    port: int | None = None,
    background: bool = True,
    opened_browser: dict[str, Any] | None = None,
    ok: bool = True,
    url_guessed: bool = False,
    engine: str = "hyperframes",
) -> Path:
    """Durable receipt for next_actions + --require-preview gate."""
    root = Path(root).expanduser().resolve()
    receipts = root / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    # Guessed URLs never satisfy require-preview even if written for debugging
    receipt_ok = bool(ok) and not url_guessed and bool(url and str(url).startswith("http"))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "compose-preview-receipt",
        "ok": receipt_ok,
        "url": url,
        "url_guessed": bool(url_guessed),
        "engine": engine,
        "hf_dir": hf_dir,
        "started_at": utc_now(),
        "already_running": bool(already_running),
        "port": port,
        "background": background,
        "opened_browser": opened_browser,
        "note": (
            "Satisfies final/compose-render --require-preview when ok=true "
            "and url was observed from Studio (not guessed)"
        ),
    }
    path = receipts / "compose-preview.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # legacy pointer (status / desktop export)
    try:
        compose_root = root / "compose"
        compose_root.mkdir(parents=True, exist_ok=True)
        (compose_root / "preview.json").write_text(
            json.dumps(
                {
                    "url": url,
                    "hf_dir": hf_dir,
                    "started_at": payload["started_at"],
                    "port": port,
                    "background": background,
                    "receipt": "receipts/compose-preview.json",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return path


def run_env() -> dict[str, str]:
    env = minimal_subprocess_env()
    for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "NODE_PATH", "npm_config_cache"):
        if key in os.environ:
            env[key] = os.environ[key]
    if "HOME" in env:
        env.setdefault("npm_config_cache", str(Path(env["HOME"]) / ".npm"))
    return env


def which_npx() -> str | None:
    return shutil.which("npx")


def extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text or "")


def prefer_studio_url(urls: list[str]) -> str | None:
    if not urls:
        return None
    for u in urls:
        if "localhost" in u or "127.0.0.1" in u:
            return u.rstrip(".,;")
    return urls[0].rstrip(".,;")


def hyperframes_preview_cmd(
    hf_dir: Path,
    *,
    port: int | None,
    background: bool,
    open_browser: bool,
    stop: bool = False,
    status: bool = False,
) -> list[str]:
    npx = which_npx()
    if not npx:
        raise ComposePreviewError("npx missing — install Node.js 22+")
    cmd = [npx, "--yes", "hyperframes", "preview", str(hf_dir)]
    if stop:
        cmd.append("--stop")
        return cmd
    if status:
        cmd.append("--status")
        return cmd
    if background:
        cmd.append("--background")
    if port is not None:
        cmd += ["--port", str(int(port))]
    if open_browser:
        cmd.append("--open")
    else:
        cmd.append("--no-open")
    return cmd


def run_preview_command(cmd: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        env=run_env(),
        timeout=timeout,
    )


def open_system_browser(url: str) -> dict[str, Any]:
    opener = None
    if sys.platform == "darwin":
        opener = ["open", url]
    elif shutil.which("xdg-open"):
        opener = ["xdg-open", url]
    elif shutil.which("gio"):
        opener = ["gio", "open", url]
    if not opener:
        return {"ok": False, "error": "no system browser opener found"}
    try:
        proc = subprocess.run(opener, check=False, capture_output=True, text=True, timeout=15)
        return {
            "ok": proc.returncode == 0,
            "cmd": opener,
            "stderr": (proc.stderr or "")[:300],
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}


def ensure_remotion_dir(root: Path, *, export_if_missing: bool) -> Path:
    rem = root / "compose" / "remotion"
    entry = rem / "src" / "index.ts"
    if entry.is_file():
        return rem
    if not export_if_missing:
        raise ComposePreviewError(
            f"missing {entry} — run export-compose --engine remotion or pass --export"
        )
    try:
        from export_composition import ComposeExportError, export_composition
    except ImportError as exc:
        raise ComposePreviewError(f"export_composition import failed: {exc}") from exc
    try:
        export_composition(root, engine="remotion", force=True, layout="auto")
    except ComposeExportError as exc:
        raise ComposePreviewError(f"export-compose remotion failed: {exc}") from exc
    if not entry.is_file():
        raise ComposePreviewError(f"export-compose did not create {entry}")
    return rem


def remotion_studio_cmd(
    rem_dir: Path,
    *,
    port: int | None = 3003,
) -> list[str]:
    """Prefer local remotion bin after npm install; fall back to npx."""
    local = rem_dir / "node_modules" / ".bin" / "remotion"
    entry = "src/index.ts"
    if local.is_file():
        cmd = [str(local), "studio", entry]
    else:
        npx = which_npx()
        if not npx:
            raise ComposePreviewError("npx missing — install Node.js 22+")
        # Without local deps, studio usually fails — still emit actionable cmd
        cmd = [npx, "--yes", "remotion", "studio", entry]
    if port is not None:
        cmd += ["--port", str(int(port))]
    return cmd


def compose_preview_remotion(
    root: Path,
    *,
    port: int | None = 3003,
    open_browser: bool = True,
    export_if_missing: bool = True,
    background: bool = True,
) -> dict[str, Any]:
    """Start Remotion Studio for compose/remotion (designed-post only)."""
    root = root.expanduser().resolve()
    try:
        safe_workspace_directory(root, "compose", field="compose")
    except SecurityPolicyError as exc:
        raise ComposePreviewError(str(exc)) from exc

    rem_dir = ensure_remotion_dir(root, export_if_missing=export_if_missing)
    nm = rem_dir / "node_modules" / "remotion"
    if not nm.is_dir() and not (rem_dir / "node_modules" / ".bin" / "remotion").is_file():
        raise ComposePreviewError(
            f"Remotion deps missing under {rem_dir}. Run once:\n"
            f'  "$AIFILM" compose-render --root "{root}" --engine remotion --npm-install\n'
            f'  # or: cd "{rem_dir}" && npm install\n'
            "Then re-run compose-preview --engine remotion"
        )

    # media must exist for Studio playback
    plan = rem_dir / "media-copy-plan.json"
    pub_clips = rem_dir / "public" / "clips"
    has_public = pub_clips.is_dir() and any(pub_clips.iterdir())
    if plan.is_file() and not has_public:
        try:
            from compose_render import copy_remotion_media

            copy_remotion_media(root)
        except Exception as exc:
            log(f"warning: remotion media-copy before studio: {exc}")

    cmd = remotion_studio_cmd(rem_dir, port=port)
    log("starting remotion studio: " + " ".join(cmd[-6:]))
    env = run_env()
    nm_bin = rem_dir / "node_modules" / ".bin"
    if nm_bin.is_dir():
        env["PATH"] = str(nm_bin) + os.pathsep + env.get("PATH", "")

    url: str | None = None
    url_guessed = False
    proc_rc = 0
    log_tail = ""
    pid: int | None = None

    if background:
        # Detach studio; capture early stdout for URL
        log_path = rem_dir / ".studio.log"
        log_f = open(log_path, "w", encoding="utf-8")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(rem_dir),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                start_new_session=True,
            )
        except OSError as exc:
            log_f.close()
            raise ComposePreviewError(f"remotion studio failed to start: {exc}") from exc
        pid = proc.pid
        # Wait briefly for URL in log
        for _ in range(20):
            time.sleep(0.4)
            try:
                text = log_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            url = prefer_studio_url(extract_urls(text))
            log_tail = text[-800:]
            if url:
                break
            if proc.poll() is not None:
                proc_rc = int(proc.returncode or 1)
                break
        if not url:
            url = f"http://localhost:{port or 3003}"
            url_guessed = True
            log(f"warning: Remotion Studio URL not observed; guessed {url}")
    else:
        # Foreground blocks — not recommended for agents
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(rem_dir),
                check=False,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            text = (proc.stdout or "") + (proc.stderr or "")
            url = prefer_studio_url(extract_urls(text)) or f"http://localhost:{port or 3003}"
            url_guessed = prefer_studio_url(extract_urls(text)) is None
            proc_rc = proc.returncode
            log_tail = text[-800:]
        except subprocess.TimeoutExpired:
            # studio is long-running — timeout means it probably started
            url = f"http://localhost:{port or 3003}"
            url_guessed = True
            proc_rc = 0
            log_tail = "timeout waiting for studio (likely running)"

    opened = (
        open_system_browser(url)
        if open_browser and url and not url_guessed
        else {"ok": False, "skipped": True, "reason": "url_guessed" if url_guessed else "no-open"}
    )
    receipt = write_preview_receipt(
        root,
        url=url or "",
        hf_dir=str(rem_dir),
        already_running=False,
        port=port,
        background=background,
        opened_browser=opened,
        ok=not url_guessed and bool(url),
        url_guessed=url_guessed,
        engine="remotion",
    )
    return {
        "ok": not url_guessed and bool(url),
        "engine": "remotion",
        "url": url,
        "url_guessed": url_guessed,
        "remotion_dir": str(rem_dir),
        "pid": pid,
        "opened_browser": opened,
        "returncode": proc_rc,
        "background": background,
        "started_at": utc_now(),
        "receipt": str(receipt),
        "stop_hint": f"kill the remotion studio process (pid={pid})"
        if pid
        else "stop studio from terminal",
        "log_tail": log_tail,
        "message": (
            None
            if not url_guessed
            else "URL guessed; open Studio manually or re-run after studio is up"
        ),
    }


def ensure_hyperframes_dir(root: Path, *, export_if_missing: bool) -> Path:
    root = root.expanduser().resolve()
    hf = root / "compose" / "hyperframes"
    index = hf / "index.html"
    if index.is_file():
        return hf
    if not export_if_missing:
        raise ComposePreviewError(f"missing {index} — run export-compose or pass --export")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from export_composition import ComposeExportError, export_composition

    try:
        export_composition(root, engine="hyperframes", force=True, layout="auto")
    except ComposeExportError as exc:
        raise ComposePreviewError(f"export-compose failed: {exc}") from exc
    if not index.is_file():
        raise ComposePreviewError(f"export ran but still missing {index}")
    return hf


def preview_status(hf_dir: Path) -> dict[str, Any]:
    cmd = hyperframes_preview_cmd(
        hf_dir, port=None, background=False, open_browser=False, status=True
    )
    proc = run_preview_command(cmd, timeout=60)
    text = (proc.stdout or "") + (proc.stderr or "")
    url = prefer_studio_url(extract_urls(text))
    running = "running" in text.lower() or (url is not None and proc.returncode == 0)
    return {
        "returncode": proc.returncode,
        "running": bool(running and url),
        "url": url,
        "raw_tail": text[-1500:],
    }


def preview_stop(hf_dir: Path) -> dict[str, Any]:
    cmd = hyperframes_preview_cmd(
        hf_dir, port=None, background=False, open_browser=False, stop=True
    )
    proc = run_preview_command(cmd, timeout=60)
    text = (proc.stdout or "") + (proc.stderr or "")
    return {"ok": proc.returncode == 0, "returncode": proc.returncode, "raw_tail": text[-800:]}


def compose_preview(
    root: Path,
    *,
    engine: str = "hyperframes",
    port: int | None = 3002,
    open_browser: bool = True,
    export_if_missing: bool = True,
    background: bool = True,
    force_new: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    engine = (engine or "hyperframes").strip().lower()
    if engine == "remotion":
        return compose_preview_remotion(
            root,
            port=port if port is not None else 3003,
            open_browser=open_browser,
            export_if_missing=export_if_missing,
            background=background,
        )
    if engine != "hyperframes":
        raise ComposePreviewError(f"engine must be hyperframes|remotion; got {engine!r}")

    try:
        safe_workspace_directory(root, "compose", field="compose")
    except SecurityPolicyError as exc:
        raise ComposePreviewError(str(exc)) from exc

    hf_dir = ensure_hyperframes_dir(root, export_if_missing=export_if_missing)

    if force_new:
        preview_stop(hf_dir)

    # Already running?
    st = preview_status(hf_dir)
    if st.get("running") and st.get("url") and not force_new:
        opened = (
            open_system_browser(str(st["url"])) if open_browser else {"ok": False, "skipped": True}
        )
        receipt = write_preview_receipt(
            root,
            url=str(st["url"]),
            hf_dir=str(hf_dir),
            already_running=True,
            port=port,
            background=background,
            opened_browser=opened,
        )
        return {
            "ok": True,
            "already_running": True,
            "url": st["url"],
            "hf_dir": str(hf_dir),
            "opened_browser": opened,
            "started_at": utc_now(),
            "receipt": str(receipt),
            "stop_cmd": f'npx hyperframes preview "{hf_dir}" --stop',
        }

    cmd = hyperframes_preview_cmd(
        hf_dir,
        port=port,
        background=background,
        open_browser=False,  # we control open ourselves for reliable JSON
    )
    if force_new:
        cmd.append("--force-new")
    log("starting hyperframes preview: " + " ".join(cmd[-6:]))
    proc = run_preview_command(cmd, timeout=180)
    text = (proc.stdout or "") + (proc.stderr or "")
    url = prefer_studio_url(extract_urls(text))

    # background start sometimes prints URL after a beat
    if not url and background:
        for _ in range(8):
            time.sleep(0.4)
            st2 = preview_status(hf_dir)
            if st2.get("url"):
                url = st2["url"]
                text = (text + "\n" + (st2.get("raw_tail") or ""))[-3000:]
                break

    if proc.returncode != 0 and not url:
        raise ComposePreviewError(
            "hyperframes preview failed: " + (text[-2000:] or f"exit {proc.returncode}")
        )
    url_guessed = False
    if not url:
        # Soft fallback for agent debugging only — does NOT satisfy --require-preview
        url = f"http://localhost:{port or 3002}"
        url_guessed = True
        log(
            f"warning: Studio URL not observed in logs; guessed {url} "
            "(receipt ok=false — will not pass --require-preview)"
        )

    opened = (
        open_system_browser(url)
        if open_browser and not url_guessed
        else {"ok": False, "skipped": True, "reason": "url_guessed" if url_guessed else "no-open"}
    )
    receipt = write_preview_receipt(
        root,
        url=url,
        hf_dir=str(hf_dir),
        already_running=False,
        port=port,
        background=background,
        opened_browser=opened,
        ok=not url_guessed,
        url_guessed=url_guessed,
        engine="hyperframes",
    )

    return {
        "ok": not url_guessed,
        "already_running": False,
        "url": url,
        "url_guessed": url_guessed,
        "hf_dir": str(hf_dir),
        "opened_browser": opened,
        "returncode": proc.returncode,
        "background": background,
        "started_at": utc_now(),
        "receipt": str(receipt),
        "stop_cmd": f'npx hyperframes preview "{hf_dir}" --stop',
        "log_tail": text[-800:],
        "message": (
            None
            if not url_guessed
            else "URL guessed; re-run compose-preview or open Studio until URL is observed"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Designed-post Studio preview (HyperFrames / Remotion)")
    p.add_argument("--root", required=True)
    p.add_argument(
        "--engine",
        default="hyperframes",
        choices=["hyperframes", "remotion"],
        help="hyperframes Studio (default) or remotion studio",
    )
    p.add_argument("--port", type=int, default=None, help="Default 3002 (HF) / 3003 (Remotion)")
    p.add_argument("--no-open", action="store_true", help="Do not open system browser")
    p.add_argument("--no-export", action="store_true", help="Do not auto export-compose")
    p.add_argument("--foreground", action="store_true", help="Do not use --background (blocks)")
    p.add_argument("--force-new", action="store_true")
    p.add_argument("--stop", action="store_true")
    p.add_argument("--status", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = Path(args.root).expanduser().resolve()
        engine = str(getattr(args, "engine", "hyperframes") or "hyperframes")
        default_port = 3003 if engine == "remotion" else 3002
        port = int(args.port) if args.port is not None else default_port
        hf_dir = root / "compose" / "hyperframes"
        if args.stop:
            if engine == "remotion":
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "engine": "remotion",
                            "error": "Remotion Studio stop is manual (kill studio process / Ctrl-C)",
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 2
            if not hf_dir.is_dir():
                raise ComposePreviewError("compose/hyperframes missing")
            result = preview_stop(hf_dir)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("ok") else 2
        if args.status:
            if engine == "remotion":
                rem = root / "compose" / "remotion"
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "engine": "remotion",
                            "dir": str(rem),
                            "package": (rem / "package.json").is_file(),
                            "node_modules": (rem / "node_modules" / "remotion").is_dir(),
                            "receipt": load_preview_receipt(root),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 0
            if not hf_dir.is_dir():
                raise ComposePreviewError("compose/hyperframes missing")
            result = preview_status(hf_dir)
            print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
            return 0
        result = compose_preview(
            root,
            engine=engine,
            port=port,
            open_browser=not args.no_open,
            export_if_missing=not args.no_export,
            background=not args.foreground,
            force_new=bool(args.force_new),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") is not False else 2
    except ComposePreviewError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    except subprocess.TimeoutExpired:
        print(
            json.dumps(
                {"ok": False, "error": "preview command timed out"}, ensure_ascii=False, indent=2
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
