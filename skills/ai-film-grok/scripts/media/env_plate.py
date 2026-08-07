#!/usr/bin/env python3
"""FRW LTX T2V env plate: no-face ambient video + first-frame keyframe.

Platform template: ltx-文生视频 / ltx-t2v / 3507313183813537792
Verified 201→completed on production key. Unlimited FRW quota path.
Never for hero/face identity locks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from frw_canary import DEFAULT_HOST  # single source of truth for FRW API host

LTX_T2V_TEMPLATE_ID = "3507313183813537792"
LTX_T2V_MODEL = "ltx-t2v"


class EnvPlateError(RuntimeError):
    pass


def _load_frw_key() -> tuple[str, str]:
    env_key = os.environ.get("FRW_API_KEY", "").strip()
    if env_key:
        return env_key, "env:FRW_API_KEY"
    home = Path.home()
    for p in (
        home / ".hermes" / "skills" / "frwclaw-pro" / ".env",
        home / ".agents" / "skills" / "frwclaw-pro" / ".env",
    ):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("FRW_API_KEY="):
                k = line.split("=", 1)[1].strip().strip('"').strip("'")
                if k:
                    return k, f"file:{p}"
    raise EnvPlateError("FRW_API_KEY not found (env or frwclaw-pro/.env)")


def _http_json(
    method: str,
    url: str,
    *,
    api_key: str,
    body: dict[str, Any] | None = None,
    timeout: float = 60,
) -> tuple[int, Any]:
    data = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "aifilm-env-plate/1.0",
        "X-Api-Key": api_key,
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(raw) if raw else {"message": str(exc)}
        except json.JSONDecodeError:
            payload = {"raw": raw[:500]}
        return int(exc.code), payload


def submit_ltx_t2v(
    prompt: str,
    *,
    width: str = "720",
    height: str = "1280",
    duration: str = "5",
    fps: str = "24",
    host: str = DEFAULT_HOST,
) -> dict[str, Any]:
    api_key, key_src = _load_frw_key()
    # force no-face language
    low = prompt.lower()
    if (
        "no people" not in low
        and "no faces" not in low
        and "无人" not in prompt
        and "无脸" not in prompt
    ):
        prompt = prompt.rstrip() + ", no people, no faces, empty unoccupied scene"

    st, body = _http_json(
        "POST",
        f"{host.rstrip('/')}/api/frwapi/v1/tasks",
        api_key=api_key,
        body={
            "templateId": LTX_T2V_TEMPLATE_ID,
            "clientUserId": "aifilm-env-plate",
            "parameters": {
                "prompt": prompt,
                "width": str(width),
                "height": str(height),
                "video_duration": str(duration),
                "video_fps": str(fps),
            },
        },
    )
    if st not in (200, 201) or not isinstance(body, dict):
        raise EnvPlateError(f"ltx-t2v submit failed http={st} body={body}")
    task_id = (body.get("data") or {}).get("taskId")
    if not task_id:
        raise EnvPlateError(f"ltx-t2v no taskId: {body}")
    return {
        "task_id": str(task_id),
        "http": st,
        "key_source": key_src,
        "prompt": prompt,
        "host": host.rstrip("/"),
        "api_key": api_key,
    }


def poll_task(
    task_id: str,
    *,
    api_key: str,
    host: str = DEFAULT_HOST,
    timeout_s: float = 240,
) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        st, body = _http_json(
            "GET",
            f"{host.rstrip('/')}/api/frwapi/v1/tasks/{task_id}",
            api_key=api_key,
            timeout=30,
        )
        if st != 200 or not isinstance(body, dict):
            last = {"http": st, "body": body}
            time.sleep(5)
            continue
        data = body.get("data") or {}
        status = data.get("status")
        url = None
        results = data.get("results") or []
        if results and isinstance(results[0], dict):
            url = results[0].get("url")
        last = {
            "http": st,
            "status": status,
            "costPoints": data.get("costPoints"),
            "errorMessage": data.get("errorMessage"),
            "url": url,
        }
        if status in {"completed", "failed"}:
            return last
        time.sleep(5)
    last["status"] = last.get("status") or "timeout"
    return last


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "aifilm-env-plate/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        dest.write_bytes(resp.read())
    if not dest.is_file() or dest.stat().st_size < 1000:
        raise EnvPlateError(f"download tiny/missing: {dest}")
    return dest


def _extract_first_frame(video: Path, out_png: Path) -> Path:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(video), "-vframes", "1", "-q:v", "2", str(out_png)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0 or not out_png.is_file():
        raise EnvPlateError(f"ffmpeg first frame failed: {(proc.stderr or '')[:300]}")
    return out_png


def run_env_plate(
    *,
    prompt: str,
    root: Path | None = None,
    shot_id: str | None = None,
    wait: bool = True,
    width: str = "720",
    height: str = "1280",
    duration: str = "5",
    fps: str = "24",
    register: bool = True,
    extract_keyframe: bool = True,
    out_dir: Path | None = None,
    poll_timeout: float = 240,
) -> dict[str, Any]:
    if not (prompt or "").strip():
        raise EnvPlateError("prompt required")

    sub = submit_ltx_t2v(
        prompt.strip(),
        width=width,
        height=height,
        duration=duration,
        fps=fps,
    )
    report: dict[str, Any] = {
        "ok": False,
        "kind": "ai-film-env-plate",
        "at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "model": LTX_T2V_MODEL,
        "template_id": LTX_T2V_TEMPLATE_ID,
        "template_name": "ltx-文生视频",
        "platform_note": "FRW exposes ltx-t2v (not branded '2.3'); verified 201→completed",
        "prompt": sub["prompt"],
        "task_id": sub["task_id"],
        "key_source": sub["key_source"],
        "params": {
            "width": str(width),
            "height": str(height),
            "video_duration": str(duration),
            "video_fps": str(fps),
        },
        "note": "env/no-face only; register frw_ltx_t2v; hero faces stay Grok",
    }

    if not wait:
        report["ok"] = True
        report["status"] = "submitted"
        report["next"] = f"poll task {sub['task_id']} or re-run with --wait"
        return report

    polled = poll_task(
        sub["task_id"],
        api_key=sub["api_key"],
        host=sub["host"],
        timeout_s=poll_timeout,
    )
    report["poll"] = {k: v for k, v in polled.items() if k != "body"}
    if polled.get("status") != "completed" or not polled.get("url"):
        raise EnvPlateError(
            f"ltx-t2v not completed: status={polled.get('status')} err={polled.get('errorMessage')}"
        )

    video_url = str(polled["url"])
    report["video_url"] = video_url

    root_p = Path(root).expanduser().resolve() if root else None
    sid = (shot_id or "env_plate").strip()
    if root_p:
        clip_dir = root_p / "clips"
        kf_dir = root_p / "keyframes"
    else:
        base = Path(out_dir or "/tmp/aifilm-env-plate").expanduser()
        clip_dir = base
        kf_dir = base / "keyframes"

    clip_path = clip_dir / f"{sid}_ltx_t2v.mp4"
    _download(video_url, clip_path)
    report["clip_path"] = str(clip_path)
    report["bytes"] = clip_path.stat().st_size

    if extract_keyframe:
        kf = kf_dir / f"{sid}.png"
        _extract_first_frame(clip_path, kf)
        report["keyframe_path"] = str(kf)

    if register and root_p and shot_id:
        aifilm = Path(__file__).resolve().parent.parent / "aifilm_grok.py"
        reg = [
            sys.executable,
            str(aifilm),
            "register-clip",
            "--root",
            str(root_p),
            "--shot-id",
            sid,
            "--source",
            str(clip_path),
            "--source-endpoint",
            "frw_ltx_t2v",
            "--identity-approved",
            "--motion-approved",
            "--review-note",
            "provider=frw model=ltx-t2v role=env no-face unlimited FRW",
        ]
        proc = subprocess.run(reg, capture_output=True, text=True, timeout=120)
        report["register_rc"] = proc.returncode
        try:
            report["register"] = json.loads((proc.stdout or "").strip().splitlines()[-1])
        except Exception:
            report["register_stdout"] = (proc.stdout or "")[:400]

    report["ok"] = True
    if root_p:
        rec = root_p / "receipts" / "env-plate.json"
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["receipt_path"] = str(rec)
    # scrub key from nested if any
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="env_plate", description="FRW LTX T2V env plate")
    p.add_argument("--prompt", required=True)
    p.add_argument("--root", default=None)
    p.add_argument("--shot-id", default=None)
    p.add_argument("--wait", action="store_true", default=True)
    p.add_argument("--no-wait", action="store_true")
    p.add_argument("--width", default="720")
    p.add_argument("--height", default="1280")
    p.add_argument("--duration", default="5")
    p.add_argument("--fps", default="24")
    p.add_argument("--no-register", action="store_true")
    p.add_argument("--no-keyframe", action="store_true")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--poll-timeout", type=float, default=240)
    args = p.parse_args(argv)
    try:
        rep = run_env_plate(
            prompt=args.prompt,
            root=Path(args.root) if args.root else None,
            shot_id=args.shot_id,
            wait=not args.no_wait,
            width=args.width,
            height=args.height,
            duration=args.duration,
            fps=args.fps,
            register=not args.no_register and bool(args.root and args.shot_id),
            extract_keyframe=not args.no_keyframe,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            poll_timeout=float(args.poll_timeout),
        )
    except EnvPlateError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    # never print api keys
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
