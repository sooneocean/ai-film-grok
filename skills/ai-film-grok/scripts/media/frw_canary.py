#!/usr/bin/env python3
"""FRW key capability canary → receipts/frw-key-capability.json

Probes (cheap by default):
  1) GET /balance
  2) POST seedance-2-fast-i2v (permission signal: 201 vs 403)
  3) POST ltx-t2v (env-layer signal)
  4) frwcore upload-token exchange

Optional:
  --wait     poll ltx-t2v until completed/failed (costs credits if accepted)
  --full     also classic text2image + exact classic img2image + classic img2video + ltx-i2v
  --root     write receipts/frw-key-capability.json under film root

Exit codes:
  0  key usable for at least one production path (recommended_l1/l2 set)
  1  runtime/network error
  2  key invalid / balance fail / no usable path

See references/lessons-2026-07-21-frw-key-capability.md
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_HOST = "https://frw-dreamaiai-api2.aiaiartist.com"
DEFAULT_IMG = "https://www.w3schools.com/w3css/img_lights.jpg"
AUTH_HOST = "https://frwcore6.aiaiartist.com"

# templateId map (aligned with frwclaw NEW_VIDEO_TEMPLATES + classic)
TEMPLATES = {
    "seedance-2-fast-i2v": "3500510042619121664",
    "ltx-t2v": "3507313183813537792",
    "ltx-i2v": "3507007578464849920",
    "classic-text2image": "3487741729447088128",
    # This is a still-to-still template.  An I2V/T2V success is not evidence
    # that FRW can accept a canonical performance-state source image.
    "classic-img2image": "3487780244406931456",
    "classic-img2video": "3487718692404334592",
}


def _now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v:
            out[k] = v
    return out


def resolve_api_key() -> tuple[str, str]:
    """Return (key, source_label). Prefer process env, then frwclaw .env."""
    env_key = os.environ.get("FRW_API_KEY", "").strip()
    if env_key:
        return env_key, "env:FRW_API_KEY"

    home = Path.home()
    candidates = [
        Path(os.environ.get("FRWCLAW_ROOT", "")).expanduser()
        if os.environ.get("FRWCLAW_ROOT")
        else None,
        home / ".hermes" / "skills" / "frwclaw-pro" / ".env",
        home / ".agents" / "skills" / "frwclaw-pro" / ".env",
    ]
    for c in candidates:
        if c is None:
            continue
        dotenv = c if c.name == ".env" else (c / ".env" if c.is_dir() else None)
        if dotenv is None or not dotenv.is_file():
            continue
        data = _load_dotenv(dotenv)
        k = data.get("FRW_API_KEY", "").strip()
        if k:
            return k, f"file:{dotenv}"
    return "", ""


def _http_json(
    method: str,
    url: str,
    *,
    api_key: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    data = None
    # Cloudflare on FRW host bans default Python-urllib UA (Error 1010).
    headers = {
        "Accept": "application/json",
        "User-Agent": "aifilm-frw-canary/1.0 (+curl-compatible)",
    }
    if api_key:
        headers["X-Api-Key"] = api_key
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return int(resp.status), json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return int(resp.status), {"raw": raw[:500]}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(raw) if raw else {"message": str(exc)}
        except json.JSONDecodeError:
            payload = {"raw": raw[:500] or str(exc)}
        return int(exc.code), payload
    except Exception as exc:  # noqa: BLE001 — surface as transport error
        return 0, {"error": str(exc)}


def _submit(
    host: str,
    api_key: str,
    template_id: str,
    parameters: dict[str, Any],
    client_user_id: str = "aifilm-canary",
) -> tuple[int, Any]:
    return _http_json(
        "POST",
        f"{host.rstrip('/')}/api/frwapi/v1/tasks",
        api_key=api_key,
        body={
            "templateId": template_id,
            "clientUserId": client_user_id,
            "parameters": parameters,
        },
    )


def _status_label(http: int, body: Any) -> str:
    if http == 0:
        return f"transport_error:{(body or {}).get('error', body)}"
    if http == 201:
        tid = ""
        if isinstance(body, dict):
            tid = str((body.get("data") or {}).get("taskId") or "")
        return f"201_submitted{(':' + tid) if tid else ''}"
    if http == 403:
        msg = ""
        if isinstance(body, dict):
            err = body.get("error") or body
            if isinstance(err, dict):
                msg = str(err.get("message") or err.get("code") or "")
            else:
                msg = str(body.get("message") or "")
        return f"403:{msg or 'forbidden'}"
    if http == 502:
        return "502"
    if http == 400:
        msg = ""
        if isinstance(body, dict):
            err = body.get("error") or body
            if isinstance(err, dict):
                msg = str(err.get("message") or "")[:120]
            else:
                msg = str(body.get("message") or "")[:120]
        return f"400:{msg}"
    if http == 401:
        return "401_invalid_key"
    return f"{http}:{str(body)[:120]}"


def _poll_task(
    host: str, api_key: str, task_id: str, *, timeout_s: float = 180.0
) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        http, body = _http_json(
            "GET",
            f"{host.rstrip('/')}/api/frwapi/v1/tasks/{task_id}",
            api_key=api_key,
            timeout=20.0,
        )
        if http != 200 or not isinstance(body, dict):
            last = {"http": http, "body": body}
            time.sleep(5)
            continue
        data = body.get("data") or {}
        status = data.get("status")
        last = {
            "http": http,
            "status": status,
            "costPoints": data.get("costPoints"),
            "errorMessage": data.get("errorMessage"),
            "url": ((data.get("results") or [{}])[0] or {}).get("url"),
        }
        if status in {"completed", "failed"}:
            return last
        time.sleep(6)
    last["status"] = last.get("status") or "timeout"
    return last


def _classify(probes: dict[str, Any]) -> dict[str, str]:
    """Derive recommended L1/L2 and short rationale."""
    seedance = str(probes.get("seedance_i2v", ""))
    ltx_t2v = str(probes.get("ltx_t2v", ""))
    ltx_i2v = str(probes.get("ltx_i2v", ""))
    classic_i2v = str(probes.get("classic_img2video", ""))
    classic_i2i = str(probes.get("classic_img2image", ""))

    seedance_ok = seedance.startswith("201")
    ltx_t2v_ok = ltx_t2v.startswith("201") or ltx_t2v == "completed"
    ltx_i2v_ok = ltx_i2v.startswith("201") or ltx_i2v == "completed"
    classic_i2v_ok = classic_i2v.startswith("201") or classic_i2v == "completed"
    classic_i2i_ok = classic_i2i.startswith("201") or classic_i2i == "completed"

    if seedance_ok:
        l1 = "seedance-2-fast-i2v"
    elif ltx_i2v_ok:
        l1 = "ltx-i2v"
    else:
        l1 = "grok"

    l2 = "ltx-t2v" if ltx_t2v_ok else "legacy-text2video"

    notes: list[str] = []
    if "403" in seedance:
        notes.append("seedance_403_permission")
    if ltx_i2v.startswith("502") or ltx_i2v == "502":
        notes.append("ltx_i2v_502")
    if not seedance_ok and l1 == "grok":
        notes.append("l1_prefer_grok_720p")
    if classic_i2v_ok and l1 == "grok":
        notes.append("frw_only_lifeboat=legacy-img2video")

    return {
        "recommended_l1": l1,
        "recommended_l2": l2,
        "seedance_permission": "open"
        if seedance_ok
        else ("blocked" if "403" in seedance else "unknown"),
        "notes": ",".join(notes) if notes else "ok",
        "classic_img2video_usable": "yes"
        if classic_i2v_ok
        else ("untested" if not classic_i2v else "no"),
        # Keep this deliberately stricter than general FRW health: a dialogue
        # performance state needs both an upload credential and the exact i2i
        # template permission, not merely an adjacent video/template success.
        "i2i_capability": (
            "available"
            if classic_i2i_ok and probes.get("upload_token") == "ok"
            else (
                "blocked"
                if "403" in classic_i2i
                else ("untested" if not classic_i2i else "unusable")
            )
        ),
    }


def frw_i2i_capability(receipt: dict[str, Any] | None) -> str:
    """Return a fail-closed FRW i2i capability label from a canary receipt.

    Old receipts lack the exact still-to-still probe, so they stay ``untested``
    even if they prove FRW T2V or I2V works.
    """
    if not isinstance(receipt, dict):
        return "untested"
    declared = str(receipt.get("i2i_capability") or "").strip().lower()
    if declared in {"available", "blocked", "unusable", "untested"}:
        return declared
    return _classify(receipt).get("i2i_capability", "untested")


def run_canary(
    *,
    host: str = DEFAULT_HOST,
    img_url: str = DEFAULT_IMG,
    wait: bool = False,
    full: bool = False,
    poll_timeout: float = 180.0,
) -> dict[str, Any]:
    api_key, key_source = resolve_api_key()
    report: dict[str, Any] = {
        "probed_at": _now_iso(),
        "host": host.rstrip("/"),
        "key_source": key_source or "missing",
        "key_fingerprint": (api_key[:8] + "…" + api_key[-4:])
        if len(api_key) >= 12
        else "(missing)",
        "credits_total": None,
        "credits_remaining": None,
        "call_limit": None,
        "call_count": None,
        "seedance_i2v": None,
        "ltx_t2v": None,
        "ltx_i2v": None,
        "classic_text2image": None,
        "classic_img2image": None,
        "classic_img2video": None,
        "upload_token": None,
        "tasks": {},
        "recommended_l1": None,
        "recommended_l2": None,
        "seedance_permission": None,
        "i2i_capability": None,
        "notes": None,
        "ok": False,
    }

    if not api_key:
        report["error"] = "FRW_API_KEY not found (env or frwclaw .env)"
        return report

    # 1) balance
    http, body = _http_json("GET", f"{host.rstrip('/')}/api/frwapi/v1/balance", api_key=api_key)
    if http != 200 or not isinstance(body, dict) or not body.get("success"):
        report["error"] = f"balance_failed http={http} body={body}"
        report["balance"] = _status_label(http, body)
        return report
    data = body.get("data") or {}
    report["credits_total"] = data.get("creditsTotal")
    report["credits_remaining"] = data.get("creditsRemaining")
    report["call_limit"] = data.get("callLimit")
    report["call_count"] = data.get("callCount")
    report["balance"] = "ok"

    # 2) seedance-2-fast-i2v (permission canary — usually 403 or 201)
    http, body = _submit(
        host,
        api_key,
        TEMPLATES["seedance-2-fast-i2v"],
        {
            "prompt": "@Image1 canary blink soft motion",
            "imageUrls": [img_url],
            "aspectRatio": "9:16",
            "resolution": "720p",
            "duration": "5",
        },
    )
    report["seedance_i2v"] = _status_label(http, body)
    if http == 201 and isinstance(body, dict):
        report["tasks"]["seedance_i2v"] = (body.get("data") or {}).get("taskId")

    # 3) ltx-t2v
    http, body = _submit(
        host,
        api_key,
        TEMPLATES["ltx-t2v"],
        {
            "prompt": "canary soft ambient motion anime light",
            "width": "720",
            "height": "1280",
            "video_duration": "5",
            "video_fps": "24",
        },
    )
    report["ltx_t2v"] = _status_label(http, body)
    ltx_tid = None
    if http == 201 and isinstance(body, dict):
        ltx_tid = (body.get("data") or {}).get("taskId")
        report["tasks"]["ltx_t2v"] = ltx_tid

    if wait and ltx_tid:
        polled = _poll_task(host, api_key, str(ltx_tid), timeout_s=poll_timeout)
        report["ltx_t2v_poll"] = polled
        if polled.get("status") == "completed":
            report["ltx_t2v"] = "completed"
        elif polled.get("status") == "failed":
            report["ltx_t2v"] = f"failed:{polled.get('errorMessage')}"
        else:
            report["ltx_t2v"] = f"poll_{polled.get('status')}"

    # 4) upload token
    http, body = _http_json(
        "GET",
        f"{AUTH_HOST}/api/v1/user/thirdparty/auth/{api_key}",
        timeout=20.0,
    )
    if http == 200 and isinstance(body, dict) and (body.get("success") or body.get("data")):
        report["upload_token"] = "ok"
    else:
        report["upload_token"] = _status_label(http, body)

    # 5) full probes
    if full:
        http, body = _submit(
            host,
            api_key,
            TEMPLATES["classic-text2image"],
            {
                "prompt": "canary soft portrait light",
                "width": "720",
                "height": "1280",
                "n": "1",
            },
        )
        report["classic_text2image"] = _status_label(http, body)

        http, body = _submit(
            host,
            api_key,
            TEMPLATES["classic-img2image"],
            {
                "imageUrl": img_url,
                "prompt": "canary identity-preserving portrait turn",
                "negativePrompt": "",
                "model": "qwen",
                "width": "1024",
                "height": "1024",
                "n": "1",
                "seed": "0",
                "steps": "30",
                "cfgScale": "7.5",
                "sampler": "",
            },
        )
        report["classic_img2image"] = _status_label(http, body)
        if http == 201 and isinstance(body, dict):
            report["tasks"]["classic_img2image"] = (body.get("data") or {}).get("taskId")

        http, body = _submit(
            host,
            api_key,
            TEMPLATES["classic-img2video"],
            {
                "prompt": "canary subtle soft motion",
                "imageUrl": img_url,
                "width": "576",
                "height": "1024",
            },
        )
        report["classic_img2video"] = _status_label(http, body)
        if http == 201 and isinstance(body, dict):
            report["tasks"]["classic_img2video"] = (body.get("data") or {}).get("taskId")

        http, body = _submit(
            host,
            api_key,
            TEMPLATES["ltx-i2v"],
            {
                "prompt": "canary subtle blink",
                "image_url": img_url,
                "width": "720",
                "height": "1280",
                "video_duration": "5",
                "video_fps": "24",
            },
        )
        report["ltx_i2v"] = _status_label(http, body)

    cls = _classify(report)
    report.update(cls)

    # ok = balance ok and at least one motion path
    l1 = report["recommended_l1"]
    l2 = report["recommended_l2"]
    has_path = bool(l1) and bool(l2)
    report["ok"] = has_path and report.get("balance") == "ok"
    return report


def write_receipt(root: Path, report: dict[str, Any]) -> Path:
    receipts = root.expanduser().resolve() / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    path = receipts / "frw-key-capability.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="frw_canary",
        description="Probe FRW API key capability; write receipts/frw-key-capability.json",
    )
    p.add_argument("--root", default=None, help="Film root; write receipts/frw-key-capability.json")
    p.add_argument("--host", default=DEFAULT_HOST, help=f"FRW API host (default {DEFAULT_HOST})")
    p.add_argument("--img-url", default=DEFAULT_IMG, help="Public HTTPS image for i2v probes")
    p.add_argument(
        "--wait", action="store_true", help="Poll ltx-t2v to completed (uses credits if 201)"
    )
    p.add_argument("--full", action="store_true", help="Also probe classic T2I/I2V + ltx-i2v")
    p.add_argument("--poll-timeout", type=float, default=180.0, help="Seconds for --wait poll")
    p.add_argument(
        "--out",
        default=None,
        help="Also write JSON to this path (in addition to --root receipts)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_canary(
        host=args.host,
        img_url=args.img_url,
        wait=bool(args.wait),
        full=bool(args.full),
        poll_timeout=float(args.poll_timeout),
    )

    written: list[str] = []
    if args.root:
        path = write_receipt(Path(args.root), report)
        report["receipt_path"] = str(path)
        written.append(str(path))
    if args.out:
        outp = Path(args.out).expanduser().resolve()
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["out_path"] = str(outp)
        written.append(str(outp))

    # one-line JSON for agent (same family as frw dispatch protocol)
    print(
        json.dumps(
            {
                "protocol_version": "1.0",
                "user_reply": (
                    f"FRW canary {'OK' if report.get('ok') else 'FAIL'} · "
                    f"L1={report.get('recommended_l1')} L2={report.get('recommended_l2')} · "
                    f"seedance={report.get('seedance_i2v')} ltx_t2v={report.get('ltx_t2v')} · "
                    f"credits={report.get('credits_remaining')} · "
                    f"upload={report.get('upload_token')}"
                    + (f" · wrote={written[0]}" if written else "")
                ),
                "next_action": "ok" if report.get("ok") else "error",
                "done": True,
                "success": bool(report.get("ok")),
                "data": report,
            },
            ensure_ascii=False,
        )
    )

    if report.get("error") and report.get("balance") != "ok":
        return 2
    if not report.get("ok"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
