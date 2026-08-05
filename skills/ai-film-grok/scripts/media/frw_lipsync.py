#!/usr/bin/env python3
"""FRW cloud lipsync (音画同步) for ai-film-grok.

Models (newvideo):
  - ltx-lipsync      template 3507007950994542592  (ltx-音画同步)
  - wan-lipsync      template 3507253019391561728  (wan-音画同步)
  - seedance-2-pro-lipsync  3500510034968711168   (often 403)

2026-07-21 probe on production key:
  seedance lipsync → 403 permission
  ltx / wan lipsync → 502 platform
Code path is ready; probe() before bulk. Default storyteller stays lipsync off.

Usage:
  aifilm frw-lipsync probe
  aifilm frw-lipsync --root <film> --shot-id shot03 --face face.png --audio line.wav --wait
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

# Prefer order when auto: ltx (params known) → wan → seedance (often 403)
LIPSYNC_MODELS: dict[str, dict[str, Any]] = {
    "ltx-lipsync": {
        "template_id": "3507007950994542592",
        "family": "ltx",
        "register_endpoint": "frw_ltx_lipsync",
    },
    "wan-lipsync": {
        "template_id": "3507253019391561728",
        "family": "wan",
        "register_endpoint": "frw_wan_lipsync",
    },
    "seedance-2-pro-lipsync": {
        "template_id": "3500510034968711168",
        "family": "seedance",
        "register_endpoint": "frw_seedance_lipsync",
    },
}


class FrwLipsyncError(RuntimeError):
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
            if line.strip().startswith("FRW_API_KEY="):
                k = line.split("=", 1)[1].strip().strip('"').strip("'")
                if k:
                    return k, f"file:{p}"
    raise FrwLipsyncError("FRW_API_KEY missing")


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
        "User-Agent": "aifilm-frw-lipsync/1.0",
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
            payload: Any = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw[:400]}
        return int(exc.code), payload


def _upload_via_frw(file_path: Path, category: str) -> str:
    """Use frw_dispatch upload; return public URL."""
    from frw_upload import FrwUploadError, extract_upload_url

    frw = Path(__file__).resolve().parent.parent / "frw_dispatch.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(frw),
            "upload",
            "--file-path",
            str(file_path),
            "--category",
            category,
        ],
        capture_output=True,
        timeout=120,
        text=True,
    )
    out = (proc.stdout or "").strip()
    line = out.splitlines()[-1] if out else ""
    try:
        data = json.loads(line) if line.startswith("{") else {}
    except json.JSONDecodeError:
        data = {}
    if proc.returncode != 0:
        raise FrwLipsyncError(
            f"upload failed: {data.get('user_reply') or proc.stderr or out}"[:300]
        )
    try:
        return extract_upload_url(data)
    except FrwUploadError as exc:
        raise FrwLipsyncError(str(exc)) from exc


def build_parameters(model: str, *, img_url: str, audio_url: str, prompt: str) -> dict[str, Any]:
    fam = LIPSYNC_MODELS[model]["family"]
    if fam == "ltx":
        return {
            "prompt": prompt or "natural talking head, subtle mouth motion",
            "image_url": img_url,
            "audio_url": audio_url,
            "width": "720",
            "height": "1280",
            "video_duration": "5",
            "video_fps": "24",
        }
    if fam == "wan":
        return {
            "prompt": prompt or "talking",
            "image_url": img_url,
            "audio_url": audio_url,
        }
    # seedance
    return {
        "prompt": prompt or "@Image1 speaking softly, no subtitles",
        "imageUrls": [img_url],
        "audioUrl": audio_url,
        "aspectRatio": "9:16",
        "resolution": "720p",
        "duration": "5",
        "generate_audio": "false",
    }


def probe_lipsync_models(*, host: str = DEFAULT_HOST) -> dict[str, Any]:
    """Cheap permission probe: submit then abandon (or fail fast on 403/502)."""
    api_key, src = _load_frw_key()
    # public tiny assets — only for capability signal
    img = "https://www.w3schools.com/w3css/img_lights.jpg"
    audio = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"
    results: dict[str, Any] = {}
    for model, meta in LIPSYNC_MODELS.items():
        params = build_parameters(model, img_url=img, audio_url=audio, prompt="probe")
        st, body = _http_json(
            "POST",
            f"{host.rstrip('/')}/api/frwapi/v1/tasks",
            api_key=api_key,
            body={
                "templateId": meta["template_id"],
                "clientUserId": "aifilm-lipsync-probe",
                "parameters": params,
            },
        )
        label = f"{st}"
        if st == 201:
            label = "201_submitted"
        elif st == 403:
            label = "403_permission"
        elif st == 502:
            label = "502_platform"
        elif st == 400:
            msg = ""
            if isinstance(body, dict):
                err = body.get("error") or body
                msg = str(err.get("message") if isinstance(err, dict) else err)[:80]
            label = f"400:{msg}"
        results[model] = {
            "http": st,
            "status": label,
            "register_endpoint": meta["register_endpoint"],
        }
    # pick first usable
    usable = [m for m, r in results.items() if str(r.get("status", "")).startswith("201")]
    return {
        "ok": bool(usable),
        "key_source": src,
        "models": results,
        "recommended": usable[0] if usable else None,
        "note": (
            "201=usable; 403=key not entitled; 502=platform down. "
            "2026-07-21 sample: seedance lipsync 403, ltx/wan 502."
            if not usable
            else f"use model={usable[0]}"
        ),
        "ref": "references/frw-lipsync.md",
    }


def poll_task(
    task_id: str, *, api_key: str, host: str = DEFAULT_HOST, timeout_s: float = 300
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
            time.sleep(5)
            continue
        data = body.get("data") or {}
        status = data.get("status")
        url = None
        results = data.get("results") or []
        if results and isinstance(results[0], dict):
            url = results[0].get("url")
        last = {
            "status": status,
            "url": url,
            "costPoints": data.get("costPoints"),
            "errorMessage": data.get("errorMessage"),
        }
        if status in {"completed", "failed"}:
            return last
        time.sleep(6)
    last["status"] = last.get("status") or "timeout"
    return last


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "aifilm-frw-lipsync/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        dest.write_bytes(resp.read())
    if dest.stat().st_size < 1000:
        raise FrwLipsyncError("downloaded video too small")
    return dest


def run_frw_lipsync(
    *,
    face: Path,
    audio: Path,
    out: Path | None = None,
    root: Path | None = None,
    shot_id: str | None = None,
    model: str = "auto",
    prompt: str = "",
    wait: bool = True,
    register: bool = False,
    poll_timeout: float = 300,
) -> dict[str, Any]:
    face = Path(face).expanduser().resolve()
    audio = Path(audio).expanduser().resolve()
    if not face.is_file():
        raise FrwLipsyncError(f"face missing: {face}")
    if not audio.is_file():
        raise FrwLipsyncError(f"audio missing: {audio}")

    if model == "auto":
        pr = probe_lipsync_models()
        model = pr.get("recommended") or "ltx-lipsync"
        if not pr.get("ok"):
            raise FrwLipsyncError(
                f"no FRW lipsync model usable now: {pr.get('models')}. "
                "Retry later or use local wav2lip after backend-lock."
            )
    if model not in LIPSYNC_MODELS:
        raise FrwLipsyncError(f"unknown model {model}; choose {sorted(LIPSYNC_MODELS)}")

    api_key, key_src = _load_frw_key()
    img_url = _upload_via_frw(face, "image")
    audio_url = _upload_via_frw(audio, "audio")
    params = build_parameters(model, img_url=img_url, audio_url=audio_url, prompt=prompt)
    meta = LIPSYNC_MODELS[model]
    st, body = _http_json(
        "POST",
        f"{DEFAULT_HOST}/api/frwapi/v1/tasks",
        api_key=api_key,
        body={
            "templateId": meta["template_id"],
            "clientUserId": "aifilm-frw-lipsync",
            "parameters": params,
        },
    )
    report: dict[str, Any] = {
        "ok": False,
        "kind": "ai-film-frw-lipsync",
        "at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "model": model,
        "template_id": meta["template_id"],
        "register_endpoint": meta["register_endpoint"],
        "key_source": key_src,
        "submit_http": st,
        "face": str(face),
        "audio": str(audio),
        "img_url": img_url,
        "audio_url": audio_url,
    }
    if st == 403:
        raise FrwLipsyncError(f"{model} 403 permission — contact FRW ops or try another model")
    if st == 502:
        raise FrwLipsyncError(f"{model} 502 platform — retry later; local Wav2Lip fallback")
    if st not in (200, 201):
        raise FrwLipsyncError(f"submit failed http={st} body={body}")
    task_id = (body.get("data") or {}).get("taskId")
    report["task_id"] = task_id
    if not wait:
        report["ok"] = True
        report["status"] = "submitted"
        return report
    polled = poll_task(str(task_id), api_key=api_key, timeout_s=poll_timeout)
    report["poll"] = polled
    if polled.get("status") != "completed" or not polled.get("url"):
        raise FrwLipsyncError(
            f"lipsync not completed: {polled.get('status')} {polled.get('errorMessage')}"
        )
    url = str(polled["url"])
    if root and shot_id:
        out = Path(root).expanduser().resolve() / "clips" / f"{shot_id}_frw_lipsync.mp4"
    elif out is None:
        out = Path("/tmp") / f"frw_lipsync_{task_id}.mp4"
    else:
        out = Path(out).expanduser().resolve()
    _download(url, out)
    report["path"] = str(out)
    report["bytes"] = out.stat().st_size
    report["video_url"] = url
    report["ok"] = True

    if register and root and shot_id:
        aifilm = Path(__file__).resolve().parent.parent / "aifilm_grok.py"
        reg = [
            sys.executable,
            str(aifilm),
            "register-clip",
            "--root",
            str(Path(root).resolve()),
            "--shot-id",
            str(shot_id),
            "--source",
            str(out),
            "--source-endpoint",
            meta["register_endpoint"],
            "--identity-approved",
            "--motion-approved",
            "--review-note",
            f"provider=frw model={model} lipsync face+audio",
        ]
        proc = subprocess.run(reg, capture_output=True, text=True, timeout=120)
        report["register_rc"] = proc.returncode
        try:
            report["register"] = json.loads((proc.stdout or "").strip().splitlines()[-1])
        except Exception:
            report["register_stdout"] = (proc.stdout or "")[:300]

    if root:
        rec = Path(root).expanduser().resolve() / "receipts" / "frw-lipsync.json"
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["receipt_path"] = str(rec)
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="frw_lipsync")
    p.add_argument("action", nargs="?", default="run", choices=["run", "probe"])
    p.add_argument("--face", default=None)
    p.add_argument("--audio", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--root", default=None)
    p.add_argument("--shot-id", default=None)
    p.add_argument("--model", default="auto", choices=["auto", *LIPSYNC_MODELS.keys()])
    p.add_argument("--prompt", default="")
    p.add_argument("--no-wait", action="store_true")
    p.add_argument("--register", action="store_true")
    p.add_argument("--poll-timeout", type=float, default=300)
    args = p.parse_args(argv)
    try:
        if args.action == "probe":
            print(json.dumps(probe_lipsync_models(), ensure_ascii=False, indent=2))
            return 0 if probe_lipsync_models().get("ok") else 1
        if not args.face or not args.audio:
            raise FrwLipsyncError("run requires --face and --audio")
        rep = run_frw_lipsync(
            face=Path(args.face),
            audio=Path(args.audio),
            out=Path(args.out) if args.out else None,
            root=Path(args.root) if args.root else None,
            shot_id=args.shot_id,
            model=args.model,
            prompt=args.prompt,
            wait=not args.no_wait,
            register=bool(args.register),
            poll_timeout=float(args.poll_timeout),
        )
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0 if rep.get("ok") else 1
    except FrwLipsyncError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
