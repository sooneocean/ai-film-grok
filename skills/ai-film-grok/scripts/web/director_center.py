"""Director command center CLI: open/status/stop/wait."""
from __future__ import annotations

import argparse
import os
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any

from util import read_json, utc_now
from web.director_live_ext import project_director_live, session_meta

SESSION_NAME = "review-ui-session.json"


class DirectorCenterError(ValueError):
    pass


def _root(root: Path | str) -> Path:
    value = Path(root).expanduser().resolve()
    if not value.is_dir():
        raise DirectorCenterError("film root must be an existing directory")
    return value


def _aifilm_launcher() -> Path:
    return Path(__file__).resolve().parents[1] / "aifilm"


def _session_alive(root: Path) -> dict[str, Any] | None:
    meta = session_meta(root)
    return meta if meta.get("active") else None


class _suppress:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return True


def open_center(root, *, port=0, open_browser=True, wait_seconds=12.0):
    base = _root(root)
    existing = _session_alive(base)
    if existing:
        url = str(existing["url"])
        if open_browser:
            with _suppress():
                webbrowser.open(url)
        return {
            "ok": True,
            "action": "reuse",
            "url": url,
            "port": existing.get("port"),
            "pid": existing.get("pid"),
            "root": str(base),
            "at": utc_now(),
        }
    launcher = _aifilm_launcher()
    if not launcher.is_file():
        raise DirectorCenterError(f"aifilm launcher missing: {launcher}")
    (base / "receipts").mkdir(parents=True, exist_ok=True)
    path = base / "receipts" / SESSION_NAME
    if path.is_file() and not path.is_symlink():
        stale = read_json(path)
        if isinstance(stale, dict) and stale.get("root") == str(base):
            path.unlink(missing_ok=True)
    log_path = base / "receipts" / "director-center-serve.log"
    log_fh = open(log_path, "ab", buffering=0)  # noqa: SIM115
    try:
        proc = subprocess.Popen(  # noqa: S603
            [str(launcher), "review-ui", "serve", "--root", str(base), "--port", str(int(port))],
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except OSError as exc:
        log_fh.close()
        raise DirectorCenterError(f"failed to spawn review-ui: {exc}") from exc
    deadline = time.monotonic() + max(2.0, float(wait_seconds))
    meta = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log_fh.close()
            raise DirectorCenterError(
                f"review-ui exited early code={proc.returncode}; see {log_path}"
            )
        meta = _session_alive(base)
        if meta:
            break
        time.sleep(0.15)
    log_fh.close()
    if not meta:
        try:
            proc.kill()
        except OSError:
            pass
        raise DirectorCenterError(f"review-ui session not ready; see {log_path}")
    url = str(meta["url"])
    if open_browser:
        with _suppress():
            webbrowser.open(url)
    return {
        "ok": True,
        "action": "spawned",
        "url": url,
        "port": meta.get("port"),
        "pid": meta.get("pid") or proc.pid,
        "root": str(base),
        "log": str(log_path),
        "at": utc_now(),
    }


def status_center(root):
    base = _root(root)
    live = project_director_live(base, include_token=True)
    return {
        "ok": True,
        "kind": "director-center-status",
        "root": str(base),
        "session": live.get("session"),
        "live": {k: v for k, v in live.items() if k != "session"},
        "at": utc_now(),
    }


def stop_center(root):
    from review_ui import ReviewUIError, stop

    try:
        result = stop(_root(root))
    except ReviewUIError as exc:
        raise DirectorCenterError(str(exc)) from exc
    return {"ok": True, "kind": "director-center-stop", **result, "at": utc_now()}


def _find_stage_item(items, stage):
    exact = next((i for i in items if isinstance(i, dict) and str(i.get("id")) == stage), None)
    if exact is not None:
        return exact
    if ":" not in stage:
        for candidate in (f"director:{stage}", stage):
            hit = next(
                (i for i in items if isinstance(i, dict) and str(i.get("id")) == candidate), None
            )
            if hit is not None:
                return hit
    return None


def wait_for_approval(root, *, stage, timeout_sec=3600.0, poll_sec=1.0):
    base = _root(root)
    stage = str(stage or "").strip()
    if not stage:
        raise DirectorCenterError("stage is required")
    timeout_sec = max(1.0, float(timeout_sec))
    poll_sec = max(0.2, min(float(poll_sec), 30.0))
    deadline = time.monotonic() + timeout_sec
    last_state = matched_id = None
    while time.monotonic() < deadline:
        from review_control import review_queue

        items = review_queue(base).get("items") or []
        item = _find_stage_item(items if isinstance(items, list) else [], stage)
        if item is None:
            last_state = "missing"
            time.sleep(poll_sec)
            continue
        matched_id = str(item.get("id"))
        last_state = str(item.get("state") or "")
        if last_state == "approved":
            return {
                "ok": True,
                "kind": "director-center-wait",
                "stage": matched_id,
                "state": last_state,
                "approval_id": item.get("approval_id"),
                "waited": True,
                "at": utc_now(),
            }
        time.sleep(poll_sec)
    return {
        "ok": False,
        "kind": "director-center-wait",
        "stage": matched_id or stage,
        "state": last_state,
        "error": f"timeout after {timeout_sec}s",
        "at": utc_now(),
    }


def add_director_center_parsers(subparsers):
    parser = subparsers.add_parser("director-center", help="open|status|stop|wait")
    sub = parser.add_subparsers(dest="director_center_action", required=True)
    o = sub.add_parser("open")
    o.add_argument("--root", required=True)
    o.add_argument("--port", type=int, default=0)
    o.add_argument("--no-browser", action="store_true")
    o.add_argument("--wait-seconds", type=float, default=12.0)
    s = sub.add_parser("status")
    s.add_argument("--root", required=True)
    st = sub.add_parser("stop")
    st.add_argument("--root", required=True)
    w = sub.add_parser("wait")
    w.add_argument("--root", required=True)
    w.add_argument("--stage", required=True)
    w.add_argument("--timeout", type=float, default=3600.0)
    w.add_argument("--poll", type=float, default=1.0)


def run_director_center(args):
    action = str(args.director_center_action)
    if action == "open":
        return (
            open_center(
                args.root,
                port=int(args.port),
                open_browser=not bool(args.no_browser),
                wait_seconds=float(args.wait_seconds),
            ),
            0,
        )
    if action == "status":
        return status_center(args.root), 0
    if action == "stop":
        return stop_center(args.root), 0
    if action == "wait":
        r = wait_for_approval(
            args.root,
            stage=str(args.stage),
            timeout_sec=float(args.timeout),
            poll_sec=float(args.poll),
        )
        return r, 0 if r.get("ok") else 2
    raise DirectorCenterError(action)
