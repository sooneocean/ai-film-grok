#!/usr/bin/env python3
"""Grok OAuth SDK surface for ai-film-grok (Grok Build / grok login session).

Priority path: OAuth from ~/.grok/auth.json (SuperGrok subscription quota via
api.x.ai). Fallback: XAI_API_KEY when AIFILM_GROK_AUTH=api_key or auto+no auth.

Capabilities (all zero third-party deps — stdlib only):
  chat          — Grok 4.5 chat/completions (+ optional JSON mode)
  image         — text-to-image  POST /v1/images/generations
  image-edit    — image edit     POST /v1/images/edits  (data URL / public URL)
  video / i2v   — POST /v1/videos/generations + poll GET /v1/videos/{id}
  tts           — POST /v1/tts + GET /v1/tts/voices  (speech tags supported)
  doctor        — models + capability flags (no secrets)

CLI:
  python3 grok_oauth.py doctor
  python3 grok_oauth.py chat --prompt "…"
  python3 grok_oauth.py image --prompt "…" --out still.png
  python3 grok_oauth.py image-edit --image in.png --prompt "…" --out out.png
  python3 grok_oauth.py video --image kf.png --prompt "…" --out clip.mp4 --wait
  python3 grok_oauth.py tts --text "你好" --out vo.mp3 --language zh
  python3 grok_oauth.py voices
  python3 grok_oauth.py refresh

Never prints tokens. Prefer Grok Build native image_gen/image_to_video in-session;
this module is for batch / offline / dispatch machine path.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import mimetypes
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config_loader import get_config
from generation_usage import (
    GenerationUsageError,
    accept_generation,
    finish_generation,
    normalize_usage,
    start_generation,
)

DEFAULT_AUTH_PATH = Path.home() / ".grok" / "auth.json"
DEFAULT_API_BASE = "https://api.x.ai/v1"
DEFAULT_OIDC_ISSUER = "https://auth.x.ai"
# refresh if fewer than this many seconds remain
REFRESH_SKEW_SEC = 300

DEFAULT_CHAT_MODEL = "grok-4.5"
DEFAULT_IMAGE_MODEL = "grok-imagine-image"
DEFAULT_IMAGE_QUALITY_MODEL = "grok-imagine-image-quality"
DEFAULT_VIDEO_MODEL = "grok-imagine-video"
DEFAULT_VIDEO_MODEL_15 = "grok-imagine-video-1.5"
DEFAULT_TTS_VOICE = "eve"
DEFAULT_TTS_LANGUAGE = "zh"

# Video poll defaults (async job)
VIDEO_POLL_INTERVAL_SEC = 2.5
VIDEO_POLL_TIMEOUT_SEC = 600


class GrokOAuthError(RuntimeError):
    pass


def _start_usage(
    root: Path | str | None,
    *,
    operation: str,
    model: str,
    shot_id: str = "",
    job_id: str = "",
    input_hash: str = "",
) -> str | None:
    if root is None:
        return None
    try:
        return start_generation(
            root,
            operation=operation,
            provider="xai",
            model=model,
            shot_id=shot_id,
            job_id=job_id,
            input_hash=input_hash,
        )
    except GenerationUsageError as exc:
        raise GrokOAuthError(f"usage tracking failed before provider request: {exc}") from exc


def _finish_usage(
    root: Path | str | None,
    generation_id: str | None,
    *,
    status: str,
    usage: object = None,
    provider_request_id: str = "",
    output: Path | str | None = None,
) -> None:
    if root is None or generation_id is None:
        return
    normalized = normalize_usage(usage)
    try:
        finish_generation(
            root,
            generation_id,
            status=status,
            usage=normalized,
            measurement=("provider_exact" if "cost_in_usd_ticks" in normalized else "unknown"),
            provider_request_id=provider_request_id,
            output=output,
        )
    except GenerationUsageError as exc:
        raise GrokOAuthError(f"usage tracking failed after provider request: {exc}") from exc


def auth_path() -> Path:
    raw = get_config().grok_auth_path.strip()
    return Path(raw).expanduser() if raw else DEFAULT_AUTH_PATH


def api_base() -> str:
    return get_config().grok_api_base.rstrip("/")


def _jwt_payload(token: str) -> dict[str, Any]:
    if token.count(".") != 2:
        return {}
    mid = token.split(".")[1]
    pad = "=" * ((4 - len(mid) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(mid + pad)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _parse_expires_at(entry: dict[str, Any], token: str) -> float | None:
    """Return unix exp if known."""
    exp_field = entry.get("expires_at")
    if isinstance(exp_field, (int, float)):
        return float(exp_field)
    if isinstance(exp_field, str) and exp_field.strip():
        s = exp_field.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s).timestamp()
        except ValueError:
            pass
    payload = _jwt_payload(token)
    if payload.get("exp"):
        try:
            return float(payload["exp"])
        except (TypeError, ValueError):
            pass
    return None


def load_auth_entry(path: Path | None = None) -> tuple[str, dict[str, Any]]:
    """Return (storage_key, entry dict)."""
    p = path or auth_path()
    if not p.is_file():
        raise GrokOAuthError(f"auth.json missing: {p} — run: grok login")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GrokOAuthError(f"cannot read auth.json: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise GrokOAuthError("auth.json empty or invalid")
    # Prefer OIDC entries with key
    best: tuple[str, dict[str, Any]] | None = None
    for k, v in data.items():
        if not isinstance(v, dict) or not v.get("key"):
            continue
        if v.get("auth_mode") == "oidc" or v.get("refresh_token") or "auth.x.ai" in str(k):
            best = (str(k), v)
            break
        if best is None:
            best = (str(k), v)
    if not best:
        raise GrokOAuthError("auth.json has no usable access token key — run: grok login")
    return best


def _save_auth_entry(storage_key: str, entry: dict[str, Any], path: Path | None = None) -> None:
    p = path or auth_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}
    data[storage_key] = entry
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)
    with contextlib.suppress(OSError):
        os.chmod(p, 0o600)


def refresh_access_token(entry: dict[str, Any]) -> dict[str, Any]:
    """OIDC refresh_token grant → updated entry fields."""
    refresh = (entry.get("refresh_token") or "").strip()
    if not refresh:
        raise GrokOAuthError("no refresh_token — run: grok login")
    client_id = (entry.get("oidc_client_id") or "").strip()
    issuer = (entry.get("oidc_issuer") or DEFAULT_OIDC_ISSUER).rstrip("/")
    # discover token endpoint
    token_url = f"{issuer}/oauth2/token"
    try:
        with urllib.request.urlopen(
            f"{issuer}/.well-known/openid-configuration", timeout=15
        ) as resp:
            conf = json.loads(resp.read().decode())
            if conf.get("token_endpoint"):
                token_url = str(conf["token_endpoint"])
    except Exception:  # noqa: BLE001
        pass
    form = {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
    }
    if client_id:
        form["client_id"] = client_id
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        token_url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise GrokOAuthError(f"token refresh failed HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise GrokOAuthError(f"token refresh failed: {exc}") from exc
    access = (body.get("access_token") or "").strip()
    if not access:
        raise GrokOAuthError("refresh response missing access_token")
    entry = dict(entry)
    entry["key"] = access
    if body.get("refresh_token"):
        entry["refresh_token"] = body["refresh_token"]
    expires_in = body.get("expires_in")
    if expires_in:
        try:
            exp_ts = time.time() + float(expires_in)
            entry["expires_at"] = (
                datetime.fromtimestamp(exp_ts, tz=UTC).isoformat().replace("+00:00", "Z")
            )
        except (TypeError, ValueError):
            pass
    return entry


def get_access_token(*, force_refresh: bool = False, persist: bool = True) -> dict[str, Any]:
    """Return {token, source, expires_at, auth_mode, email, scopes, refreshed} — no raw dump helpers."""
    cfg = get_config()
    mode = cfg.grok_auth.strip().lower()
    api_key = cfg.xai_api_key.strip()
    if mode == "api_key" or (mode == "auto" and api_key and not auth_path().is_file()):
        if not api_key:
            raise GrokOAuthError("AIFILM_GROK_AUTH=api_key but XAI_API_KEY empty")
        return {
            "token": api_key,
            "source": "env:XAI_API_KEY",
            "auth_mode": "api_key",
            "expires_at": None,
            "email": None,
            "scopes": None,
            "refreshed": False,
            "api_base": api_base(),
        }

    storage_key, entry = load_auth_entry()
    token = str(entry.get("key") or "")
    exp = _parse_expires_at(entry, token)
    now = time.time()
    need_refresh = force_refresh or (exp is not None and exp - now < REFRESH_SKEW_SEC)
    refreshed = False
    if need_refresh and entry.get("refresh_token"):
        entry = refresh_access_token(entry)
        token = str(entry.get("key") or "")
        exp = _parse_expires_at(entry, token)
        refreshed = True
        if persist:
            _save_auth_entry(storage_key, entry)
    if not token:
        raise GrokOAuthError("empty access token after load/refresh")
    payload = _jwt_payload(token)
    return {
        "token": token,
        "source": "oauth:auth.json",
        "auth_mode": entry.get("auth_mode") or "oidc",
        "expires_at": entry.get("expires_at"),
        "expires_ts": exp,
        "ttl_sec": int(exp - now) if exp else None,
        "email": entry.get("email"),
        "scopes": payload.get("scope"),
        "tier": payload.get("tier"),
        "refreshed": refreshed,
        "api_base": api_base(),
        "storage_key": storage_key[:40] + "…",
    }


def _http_json(
    method: str,
    url: str,
    *,
    token: str,
    body: dict[str, Any] | None = None,
    timeout: float = 120,
) -> Any:
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "aifilm-grok-oauth/1.1",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise GrokOAuthError(f"HTTP {exc.code} {url}: {detail}") from exc
    except Exception as exc:
        raise GrokOAuthError(f"request failed {url}: {exc}") from exc


def _http_bytes(
    method: str,
    url: str,
    *,
    token: str,
    body: dict[str, Any] | None = None,
    timeout: float = 180,
    accept: str = "*/*",
) -> tuple[bytes, str]:
    """Return (body_bytes, content_type)."""
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "User-Agent": "aifilm-grok-oauth/1.1",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get("Content-Type") or ""
            return resp.read(), ct
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise GrokOAuthError(f"HTTP {exc.code} {url}: {detail}") from exc
    except Exception as exc:
        raise GrokOAuthError(f"request failed {url}: {exc}") from exc


def _download_url(url: str, out: Path, *, timeout: float = 180) -> Path:
    """Download a generated artifact with curl and atomically publish it."""
    out = Path(out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(f".{out.name}.{secrets.token_hex(16)}.partial")
    command = [
        "curl",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "30",
        "--max-time",
        str(timeout),
        "--user-agent",
        "aifilm-grok-oauth/1.1",
        "--output",
        str(partial),
        "--url",
        str(url),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        partial.unlink(missing_ok=True)
        raise GrokOAuthError(f"artifact download failed: {exc}") from exc
    if result.returncode != 0:
        partial.unlink(missing_ok=True)
        detail = (result.stderr or result.stdout or "curl failed").strip()[:500]
        raise GrokOAuthError(f"artifact download failed: {detail}")
    if not partial.is_file():
        raise GrokOAuthError("artifact download failed: curl produced no output")
    partial.replace(out)
    return out


def file_to_data_url(path: Path | str) -> str:
    """Local image/video → data:…;base64,… for Imagine API inputs."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise GrokOAuthError(f"media file missing: {p}")
    mime, _ = mimetypes.guess_type(str(p))
    if not mime:
        suffix = p.suffix.lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".mp4": "video/mp4",
            ".webm": "video/webm",
        }.get(suffix, "application/octet-stream")
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _image_input_object(image: str | Path) -> dict[str, str]:
    """Build API image object from path, public URL, or data URL."""
    s = str(image).strip()
    if s.startswith("data:") or s.startswith("http://") or s.startswith("https://"):
        return {"url": s}
    return {"url": file_to_data_url(s)}


def _local_image_sha256(image: str | Path | None) -> str | None:
    """Hash local media for receipts without storing its path or data URL."""
    if image is None:
        return None
    raw = str(image).strip()
    if raw.startswith(("data:", "http://", "https://")):
        return None
    path = Path(raw).expanduser()
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── Probe ──────────────────────────────────────────────────────────────


def probe(*, deep: bool = False) -> dict[str, Any]:
    """Safe readiness report (no secrets). deep=True lightly probes TTS voices list."""
    out: dict[str, Any] = {
        "ok": False,
        "auth_path": str(auth_path()),
        "auth_present": auth_path().is_file(),
        "api_base": api_base(),
        "mode": get_config().grok_auth or "auto",
        "pack": {
            "chat": True,
            "image_gen": True,
            "image_edit": True,
            "video_i2v": True,
            "tts": True,
            "stt": False,  # OAuth team may lack; not wired as film default
            "voice_agent": False,  # WebSocket realtime — not film pipeline
            "native_lipsync": False,  # no Grok native lipsync; use TTS timestamps + local/FRW
        },
    }
    try:
        tok = get_access_token(force_refresh=False, persist=True)
    except GrokOAuthError as exc:
        out["error"] = str(exc)
        out["hint"] = "grok login   # browser OAuth; tokens → ~/.grok/auth.json"
        return out
    out.update(
        {
            "source": tok.get("source"),
            "auth_mode": tok.get("auth_mode"),
            "email": tok.get("email"),
            "ttl_sec": tok.get("ttl_sec"),
            "expires_at": tok.get("expires_at"),
            "refreshed": tok.get("refreshed"),
            "scopes": tok.get("scopes"),
            "tier": tok.get("tier"),
        }
    )
    # models probe
    try:
        models = _http_json("GET", f"{tok['api_base']}/models", token=tok["token"], timeout=20)
        ids = []
        if isinstance(models, dict):
            for item in models.get("data") or []:
                if isinstance(item, dict) and item.get("id"):
                    ids.append(str(item["id"]))
        out["models"] = ids
        out["has_chat"] = any("grok" in m and "imagine" not in m for m in ids) or any(
            m.startswith("grok-") for m in ids
        )
        out["has_imagine_image"] = any("imagine-image" in m for m in ids)
        out["has_imagine_video"] = any("imagine-video" in m for m in ids)
        out["has_imagine_video_15"] = any("imagine-video-1.5" in m for m in ids)
        out["ok"] = bool(ids) or tok.get("source") == "env:XAI_API_KEY"
    except GrokOAuthError as exc:
        out["error"] = str(exc)
        out["ok"] = False
        return out

    # TTS probe (list voices — cheap)
    if deep or get_config().grok_probe_tts:
        try:
            voices = tts_list_voices()
            out["has_tts"] = bool(voices.get("ok"))
            out["tts_voice_count"] = voices.get("count")
            out["tts_sample_voices"] = (voices.get("voice_ids") or [])[:8]
        except GrokOAuthError as exc:
            out["has_tts"] = False
            out["tts_error"] = str(exc)[:200]
    else:
        # OAuth SuperGrok can hit /v1/tts (verified); flag optimistic when chat ok
        out["has_tts"] = bool(out.get("ok"))
        out["tts_probe"] = "skipped (set deep=1 or AIFILM_GROK_PROBE_TTS=1)"

    out["recommended"] = {
        "chat_model": get_config().grok_chat_model or DEFAULT_CHAT_MODEL,
        "image_model": get_config().grok_image_model or DEFAULT_IMAGE_MODEL,
        "video_model": get_config().grok_video_model or DEFAULT_VIDEO_MODEL,
        "tts_voice": get_config().grok_tts_voice or DEFAULT_TTS_VOICE,
        "tts_language": get_config().grok_tts_language or DEFAULT_TTS_LANGUAGE,
        "i2v_note": "batch: aifilm grok-oauth video --image kf.png --wait; session: image_to_video",
        "tts_note": "film default remains edge; grok TTS is opt-in (tts_backend=grok / --backend grok)",
    }
    return out


# ── Chat ───────────────────────────────────────────────────────────────


def chat_completion(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.4,
    json_mode: bool = False,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tok = get_access_token()
    model = model or get_config().grok_chat_model or DEFAULT_CHAT_MODEL
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    resp = _http_json(
        "POST",
        f"{tok['api_base']}/chat/completions",
        token=tok["token"],
        body=body,
        timeout=180,
    )
    content = ""
    tool_calls: list[Any] = []
    if isinstance(resp, dict):
        choices = resp.get("choices") or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            content = str(msg.get("content") or "")
            tool_calls = list(msg.get("tool_calls") or [])
    return {
        "ok": bool(content) or bool(tool_calls),
        "model": model,
        "content": content,
        "tool_calls": tool_calls,
        "source": tok.get("source"),
        "usage": (resp or {}).get("usage") if isinstance(resp, dict) else None,
        "json_mode": json_mode,
    }


# ── Images ─────────────────────────────────────────────────────────────


def images_generate(
    prompt: str,
    *,
    out: Path,
    model: str | None = None,
    aspect_ratio: str | None = "9:16",
    resolution: str | None = None,
    n: int = 1,
    usage_root: Path | str | None = None,
    shot_id: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    """Text-to-image via api.x.ai (OAuth). Prefer Grok Build image_gen in-session."""
    tok = get_access_token()
    model = model or get_config().grok_image_model or DEFAULT_IMAGE_MODEL
    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": max(1, int(n)),
        "response_format": "url",
    }
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if resolution:
        body["resolution"] = resolution
    generation_id = _start_usage(
        usage_root,
        operation="t2i",
        model=model,
        shot_id=shot_id,
        job_id=job_id,
    )
    try:
        try:
            resp = _http_json(
                "POST",
                f"{tok['api_base']}/images/generations",
                token=tok["token"],
                body=body,
                timeout=180,
            )
        except GrokOAuthError:
            _finish_usage(usage_root, generation_id, status="failed")
            body.pop("aspect_ratio", None)
            body.pop("resolution", None)
            generation_id = _start_usage(
                usage_root,
                operation="t2i",
                model=model,
                shot_id=shot_id,
                job_id=job_id,
            )
            resp = _http_json(
                "POST",
                f"{tok['api_base']}/images/generations",
                token=tok["token"],
                body=body,
                timeout=180,
            )
    except GrokOAuthError:
        _finish_usage(usage_root, generation_id, status="failed")
        raise
    url = None
    if isinstance(resp, dict):
        data = resp.get("data") or []
        if data and isinstance(data[0], dict):
            url = data[0].get("url") or (
                f"data:image/png;base64,{data[0]['b64_json']}" if data[0].get("b64_json") else None
            )
    if not url:
        _finish_usage(
            usage_root,
            generation_id,
            status="failed",
            usage=(resp or {}).get("usage") if isinstance(resp, dict) else None,
        )
        raise GrokOAuthError(f"image response missing url: {str(resp)[:200]}")
    out = Path(out).expanduser().resolve()
    normalized_usage = normalize_usage(
        (resp or {}).get("usage") if isinstance(resp, dict) else None
    )
    try:
        if str(url).startswith("data:"):
            # data URL path
            _, _, b64 = str(url).partition(",")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(base64.b64decode(b64))
        else:
            _download_url(str(url), out)
    except Exception:
        # Provider completion is still billable when only the local download fails.
        _finish_usage(
            usage_root,
            generation_id,
            status="succeeded",
            usage=normalized_usage,
        )
        raise
    _finish_usage(
        usage_root,
        generation_id,
        status="succeeded",
        usage=normalized_usage,
        output=out,
    )
    return {
        "ok": out.is_file() and out.stat().st_size > 100,
        "path": str(out),
        "bytes": out.stat().st_size,
        "model": model,
        "source": tok.get("source"),
        "operation": "images.generations",
        "generation_id": generation_id,
        "usage": normalized_usage,
    }


def images_edit(
    prompt: str,
    *,
    image: str | Path,
    out: Path,
    model: str | None = None,
    aspect_ratio: str | None = None,
    extra_images: list[str | Path] | None = None,
    usage_root: Path | str | None = None,
    shot_id: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    """Image edit / multi-ref edit via POST /v1/images/edits (JSON + data URL)."""
    tok = get_access_token()
    model = model or get_config().grok_image_model or DEFAULT_IMAGE_MODEL
    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "image": _image_input_object(image),
        "n": 1,
        "response_format": "url",
    }
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if extra_images:
        # multi-image edit: some APIs accept images[] — try common shape
        body["images"] = [_image_input_object(x) for x in extra_images]
    generation_id = _start_usage(
        usage_root,
        operation="image_edit",
        model=model,
        shot_id=shot_id,
        job_id=job_id,
    )
    try:
        try:
            resp = _http_json(
                "POST",
                f"{tok['api_base']}/images/edits",
                token=tok["token"],
                body=body,
                timeout=180,
            )
        except GrokOAuthError as exc:
            _finish_usage(usage_root, generation_id, status="failed")
            # retry without multi-image / aspect if rejected
            if "images" not in body and "aspect_ratio" not in body:
                raise exc
            body.pop("images", None)
            body.pop("aspect_ratio", None)
            generation_id = _start_usage(
                usage_root,
                operation="image_edit",
                model=model,
                shot_id=shot_id,
                job_id=job_id,
            )
            resp = _http_json(
                "POST",
                f"{tok['api_base']}/images/edits",
                token=tok["token"],
                body=body,
                timeout=180,
            )
    except GrokOAuthError:
        _finish_usage(usage_root, generation_id, status="failed")
        raise
    url = None
    if isinstance(resp, dict):
        data = resp.get("data") or []
        if data and isinstance(data[0], dict):
            url = data[0].get("url")
            if not url and data[0].get("b64_json"):
                url = f"data:image/png;base64,{data[0]['b64_json']}"
    if not url:
        _finish_usage(
            usage_root,
            generation_id,
            status="failed",
            usage=(resp or {}).get("usage") if isinstance(resp, dict) else None,
        )
        raise GrokOAuthError(f"image-edit response missing url: {str(resp)[:200]}")
    out = Path(out).expanduser().resolve()
    normalized_usage = normalize_usage(
        (resp or {}).get("usage") if isinstance(resp, dict) else None
    )
    try:
        if str(url).startswith("data:"):
            _, _, b64 = str(url).partition(",")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(base64.b64decode(b64))
        else:
            _download_url(str(url), out)
    except Exception:
        _finish_usage(
            usage_root,
            generation_id,
            status="succeeded",
            usage=normalized_usage,
        )
        raise
    _finish_usage(
        usage_root,
        generation_id,
        status="succeeded",
        usage=normalized_usage,
        output=out,
    )
    return {
        "ok": out.is_file() and out.stat().st_size > 100,
        "path": str(out),
        "bytes": out.stat().st_size,
        "model": model,
        "source": tok.get("source"),
        "operation": "images.edits",
        "input": str(image),
        "generation_id": generation_id,
        "usage": normalized_usage,
    }


# ── Video (I2V / T2V) ──────────────────────────────────────────────────


def video_submit(
    prompt: str | None = None,
    *,
    image: str | Path | None = None,
    model: str | None = None,
    duration: int = 6,
    aspect_ratio: str | None = "9:16",
    resolution: str | None = "720p",
    reference_images: list[str | Path] | None = None,
    usage_root: Path | str | None = None,
    shot_id: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    """Submit async video job. Returns {request_id, …}. Does not wait."""
    tok = get_access_token()
    model = model or get_config().grok_video_model or DEFAULT_VIDEO_MODEL
    body: dict[str, Any] = {
        "model": model,
        "duration": int(duration),
    }
    if prompt:
        body["prompt"] = prompt
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if resolution:
        body["resolution"] = resolution
    if image is not None:
        body["image"] = _image_input_object(image)
    if reference_images:
        body["reference_images"] = [_image_input_object(x) for x in reference_images]
    if not body.get("prompt") and not body.get("image") and not body.get("reference_images"):
        raise GrokOAuthError("video_submit needs prompt and/or image / reference_images")
    # grok-imagine-video-1.5 is I2V-only
    if "1.5" in model and not body.get("image") and not body.get("reference_images"):
        raise GrokOAuthError(
            f"model {model} is image-to-video only — pass --image (see docs.x.ai Imagine Video 1.5)"
        )
    input_provenance = {
        "keyframe_sha256": _local_image_sha256(image),
        "reference_image_sha256s": [
            digest
            for ref in reference_images or []
            if (digest := _local_image_sha256(ref)) is not None
        ],
    }
    input_hash = hashlib.sha256(
        json.dumps(input_provenance, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    generation_id = _start_usage(
        usage_root,
        operation="i2v" if image is not None or reference_images else "t2v",
        model=model,
        shot_id=shot_id,
        job_id=job_id,
        input_hash=input_hash,
    )
    try:
        resp = _http_json(
            "POST",
            f"{tok['api_base']}/videos/generations",
            token=tok["token"],
            body=body,
            timeout=120,
        )
    except GrokOAuthError:
        _finish_usage(usage_root, generation_id, status="failed")
        raise
    rid = (resp or {}).get("request_id") if isinstance(resp, dict) else None
    if not rid:
        _finish_usage(
            usage_root,
            generation_id,
            status="failed",
            usage=(resp or {}).get("usage") if isinstance(resp, dict) else None,
        )
        raise GrokOAuthError(f"video submit missing request_id: {str(resp)[:200]}")
    if usage_root is not None and generation_id is not None:
        try:
            accept_generation(
                usage_root,
                generation_id,
                provider_request_id=str(rid),
                usage=(resp or {}).get("usage") if isinstance(resp, dict) else None,
            )
        except GenerationUsageError as exc:
            raise GrokOAuthError(f"usage tracking failed after video submit: {exc}") from exc
    return {
        "ok": True,
        "request_id": str(rid),
        "model": model,
        "duration": int(duration),
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "source": tok.get("source"),
        "has_image": image is not None,
        "input_provenance": input_provenance,
        "operation": "videos.generations",
        "generation_id": generation_id,
        "usage": normalize_usage((resp or {}).get("usage") if isinstance(resp, dict) else None),
    }


def video_status(
    request_id: str,
    *,
    usage_root: Path | str | None = None,
    generation_id: str | None = None,
) -> dict[str, Any]:
    tok = get_access_token()
    resp = _http_json(
        "GET",
        f"{tok['api_base']}/videos/{request_id}",
        token=tok["token"],
        timeout=60,
    )
    if not isinstance(resp, dict):
        raise GrokOAuthError(f"empty video status for {request_id}")
    status = str(resp.get("status") or "")
    video = resp.get("video") if isinstance(resp.get("video"), dict) else {}
    normalized_usage = normalize_usage(resp.get("usage"))
    result = {
        "ok": status in {"done", "pending", "processing"} or bool(status),
        "request_id": request_id,
        "status": status,
        "progress": resp.get("progress"),
        "model": resp.get("model"),
        "error": resp.get("error"),
        "video_url": (video or {}).get("url"),
        "video_duration": (video or {}).get("duration"),
        "respect_moderation": (video or {}).get("respect_moderation"),
        "usage": normalized_usage,
        "raw_keys": list(resp.keys()),
        "generation_id": generation_id,
    }
    moderated = (
        status == "done"
        and not result.get("respect_moderation", True)
        and not result.get("video_url")
    )
    if moderated:
        _finish_usage(
            usage_root,
            generation_id,
            status="moderated",
            usage=normalized_usage,
            provider_request_id=request_id,
        )
    elif status == "done":
        _finish_usage(
            usage_root,
            generation_id,
            status="succeeded",
            usage=normalized_usage,
            provider_request_id=request_id,
        )
    elif status in {"failed", "error"}:
        _finish_usage(
            usage_root,
            generation_id,
            status="failed",
            usage=normalized_usage,
            provider_request_id=request_id,
        )
    return result


def video_wait(
    request_id: str,
    *,
    out: Path | None = None,
    timeout_sec: float = VIDEO_POLL_TIMEOUT_SEC,
    poll_interval: float = VIDEO_POLL_INTERVAL_SEC,
    usage_root: Path | str | None = None,
    generation_id: str | None = None,
) -> dict[str, Any]:
    """Poll until done/failed; optionally download MP4 to out."""
    deadline = time.time() + max(30.0, float(timeout_sec))
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = video_status(
            request_id,
            usage_root=usage_root,
            generation_id=generation_id,
        )
        st = str(last.get("status") or "")
        if st == "done":
            break
        if st in {"failed", "error"}:
            err = last.get("error")
            raise GrokOAuthError(f"video job failed {request_id}: {err}")
        time.sleep(max(0.5, float(poll_interval)))
    else:
        raise GrokOAuthError(
            f"video poll timeout ({timeout_sec}s) request_id={request_id} last={last.get('status')}"
        )
    if not last.get("respect_moderation", True) and not last.get("video_url"):
        raise GrokOAuthError(f"video moderated / empty url request_id={request_id}")
    result = dict(last)
    result["ok"] = True
    if out is not None:
        url = last.get("video_url")
        if not url:
            raise GrokOAuthError(f"video done but no url: {request_id}")
        path = _download_url(str(url), Path(out))
        result["path"] = str(path)
        result["bytes"] = path.stat().st_size
        result["ok"] = path.is_file() and path.stat().st_size > 1000
    return result


def video_generate(
    prompt: str | None = None,
    *,
    image: str | Path | None = None,
    out: Path,
    model: str | None = None,
    duration: int = 6,
    aspect_ratio: str | None = "9:16",
    resolution: str | None = "720p",
    reference_images: list[str | Path] | None = None,
    timeout_sec: float = VIDEO_POLL_TIMEOUT_SEC,
    usage_root: Path | str | None = None,
    shot_id: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    """Submit + wait + download. Primary batch I2V path for grok_primary offline."""
    sub = video_submit(
        prompt,
        image=image,
        model=model,
        duration=duration,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        reference_images=reference_images,
        usage_root=usage_root,
        shot_id=shot_id,
        job_id=job_id,
    )
    done = video_wait(
        sub["request_id"],
        out=out,
        timeout_sec=timeout_sec,
        usage_root=usage_root,
        generation_id=sub.get("generation_id"),
    )
    done.update(
        {
            "model": sub.get("model"),
            "source": sub.get("source"),
            "operation": "videos.generations",
            "has_image": sub.get("has_image"),
            "request_id": sub["request_id"],
        }
    )
    return done


# ── TTS ────────────────────────────────────────────────────────────────


def tts_list_voices() -> dict[str, Any]:
    tok = get_access_token()
    resp = _http_json(
        "GET",
        f"{tok['api_base']}/tts/voices",
        token=tok["token"],
        timeout=30,
    )
    voices = []
    if isinstance(resp, dict):
        voices = list(resp.get("voices") or [])
    ids = [str(v.get("voice_id")) for v in voices if isinstance(v, dict) and v.get("voice_id")]
    return {
        "ok": bool(ids),
        "count": len(ids),
        "voice_ids": ids,
        "voices": voices,
        "source": tok.get("source"),
    }


def tts_speak(
    text: str,
    *,
    out: Path,
    voice_id: str | None = None,
    language: str | None = None,
    speed: float | None = None,
    with_timestamps: bool = False,
    codec: str = "mp3",
    sample_rate: int | None = None,
    bit_rate: int | None = None,
    usage_root: Path | str | None = None,
    shot_id: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    """Grok TTS via POST /v1/tts. Supports speech tags in text. Opt-in film backend.

    Speech tags examples: [pause] [laugh] <whisper>…</whisper>
    Character timestamps (with_timestamps=True) help caption/lipsync alignment.
    """
    if not (text or "").strip():
        raise GrokOAuthError("tts text is empty")
    tok = get_access_token()
    voice_id = voice_id or get_config().grok_tts_voice or DEFAULT_TTS_VOICE
    language = language or get_config().grok_tts_language or DEFAULT_TTS_LANGUAGE
    body: dict[str, Any] = {
        "text": text,
        "voice_id": voice_id,
        "language": language,
    }
    if speed is not None:
        body["speed"] = float(speed)
    if with_timestamps:
        body["with_timestamps"] = True
    ofmt: dict[str, Any] = {"codec": codec}
    if sample_rate:
        ofmt["sample_rate"] = int(sample_rate)
    if bit_rate:
        ofmt["bit_rate"] = int(bit_rate)
    if codec != "mp3" or sample_rate or bit_rate:
        body["output_format"] = ofmt

    generation_id = _start_usage(
        usage_root,
        operation="tts",
        model="grok-tts",
        shot_id=shot_id,
        job_id=job_id,
    )
    try:
        raw, ct = _http_bytes(
            "POST",
            f"{tok['api_base']}/tts",
            token=tok["token"],
            body=body,
            timeout=180,
            accept="application/json, audio/*, */*",
        )
    except GrokOAuthError:
        _finish_usage(usage_root, generation_id, status="failed")
        raise
    out = Path(out).expanduser().resolve()
    timestamps = None
    duration = None
    payload_usage: object = None
    audio_bytes: bytes
    if "application/json" in (ct or "") or (raw[:1] == b"{"):
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            _finish_usage(usage_root, generation_id, status="failed")
            raise GrokOAuthError(f"tts json parse failed: {exc}") from exc
        audio_b64 = payload.get("audio")
        payload_usage = payload.get("usage")
        if not audio_b64:
            _finish_usage(
                usage_root,
                generation_id,
                status="failed",
                usage=payload.get("usage"),
            )
            raise GrokOAuthError(f"tts json missing audio: {str(payload)[:200]}")
        try:
            audio_bytes = base64.b64decode(audio_b64)
        except (TypeError, ValueError) as exc:
            _finish_usage(
                usage_root,
                generation_id,
                status="failed",
                usage=payload_usage,
            )
            raise GrokOAuthError(f"tts audio decode failed: {exc}") from exc
        timestamps = payload.get("audio_timestamps")
        duration = payload.get("duration")
    else:
        if len(raw) < 200:
            _finish_usage(usage_root, generation_id, status="failed")
            raise GrokOAuthError(f"tts audio too small ({len(raw)}B): {raw[:80]!r}")
        audio_bytes = raw
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(audio_bytes)
    except OSError as exc:
        _finish_usage(
            usage_root,
            generation_id,
            status="failed",
            usage=payload_usage,
        )
        raise GrokOAuthError(f"tts output write failed: {exc}") from exc

    result: dict[str, Any] = {
        "ok": out.is_file() and out.stat().st_size > 200,
        "path": str(out),
        "bytes": out.stat().st_size,
        "voice_id": voice_id,
        "language": language,
        "source": tok.get("source"),
        "operation": "tts",
        "content_type": ct,
        "with_timestamps": bool(with_timestamps),
        "generation_id": generation_id,
        "usage": normalize_usage(payload_usage),
    }
    _finish_usage(
        usage_root,
        generation_id,
        status="succeeded",
        usage=payload_usage,
        output=out,
    )
    if duration is not None:
        result["duration"] = duration
    if timestamps is not None:
        result["audio_timestamps"] = timestamps
        # sidecar for lipsync / caption tools
        side = out.with_suffix(out.suffix + ".timestamps.json")
        side.write_text(
            json.dumps(
                {"duration": duration, "audio_timestamps": timestamps, "voice_id": voice_id},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        result["timestamps_path"] = str(side)
    return result


# ── CLI ────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="grok_oauth",
        description="Grok OAuth pack: chat / image / image-edit / video(i2v) / tts",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="Probe OAuth + models (no secrets)")
    d.add_argument("--deep", action="store_true", help="Also probe TTS voices list")

    ch = sub.add_parser("chat", help="One-shot chat completion")
    ch.add_argument("--prompt", required=True)
    ch.add_argument("--model", default=None)
    ch.add_argument("--system", default=None)
    ch.add_argument(
        "--json", action="store_true", dest="json_mode", help="response_format=json_object"
    )

    im = sub.add_parser("image", help="Text-to-image (prefer in-session image_gen)")
    im.add_argument("--prompt", required=True)
    im.add_argument("--out", required=True)
    im.add_argument("--model", default=None)
    im.add_argument("--aspect", default="9:16")
    im.add_argument("--resolution", default=None, help="1k | 2k when supported")
    im.add_argument("--root", default=None)
    im.add_argument("--shot-id", default="")
    im.add_argument("--job-id", default="")

    ie = sub.add_parser("image-edit", help="Image edit via /v1/images/edits")
    ie.add_argument("--image", required=True, help="local path | data URL | public URL")
    ie.add_argument("--prompt", required=True)
    ie.add_argument("--out", required=True)
    ie.add_argument("--model", default=None)
    ie.add_argument("--aspect", default=None)
    ie.add_argument("--ref", action="append", default=[], help="extra reference image (repeatable)")
    ie.add_argument("--root", default=None)
    ie.add_argument("--shot-id", default="")
    ie.add_argument("--job-id", default="")

    vid = sub.add_parser("video", help="I2V/T2V via /v1/videos/generations (+ optional --wait)")
    vid.add_argument("--prompt", default=None)
    vid.add_argument("--image", default=None, help="still for I2V (local path preferred)")
    vid.add_argument("--out", default=None, help="mp4 path (required with --wait)")
    vid.add_argument("--model", default=None)
    vid.add_argument("--duration", type=int, default=6)
    vid.add_argument("--aspect", default="9:16")
    vid.add_argument("--resolution", default="720p", choices=["480p", "720p", "1080p"])
    vid.add_argument("--wait", action="store_true", help="poll until done and download")
    vid.add_argument("--timeout", type=float, default=VIDEO_POLL_TIMEOUT_SEC)
    vid.add_argument("--ref", action="append", default=[], help="reference image for R2V")
    vid.add_argument("--root", default=None)
    vid.add_argument("--shot-id", default="")
    vid.add_argument("--job-id", default="")

    pol = sub.add_parser("video-status", help="Poll a video request_id")
    pol.add_argument("--request-id", required=True)
    pol.add_argument("--out", default=None, help="if done, download here")
    pol.add_argument("--wait", action="store_true")
    pol.add_argument("--timeout", type=float, default=VIDEO_POLL_TIMEOUT_SEC)
    pol.add_argument("--root", default=None)
    pol.add_argument("--generation-id", default=None)

    tt = sub.add_parser("tts", help="Grok TTS (/v1/tts) — opt-in film backend")
    tt.add_argument("--text", default=None)
    tt.add_argument("--text-file", default=None)
    tt.add_argument("--out", required=True)
    tt.add_argument("--voice", default=None, dest="voice_id")
    tt.add_argument("--language", default=None)
    tt.add_argument("--speed", type=float, default=None)
    tt.add_argument("--timestamps", action="store_true", help="character timestamps sidecar")
    tt.add_argument("--codec", default="mp3")
    tt.add_argument("--root", default=None)
    tt.add_argument("--shot-id", default="")
    tt.add_argument("--job-id", default="")

    sub.add_parser("voices", help="List Grok TTS voices")
    sub.add_parser("refresh", help="Force token refresh and persist auth.json")

    args = p.parse_args(argv)

    try:
        if args.cmd == "doctor":
            rep = probe(deep=bool(getattr(args, "deep", False)))
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0 if rep.get("ok") else 1
        if args.cmd == "refresh":
            tok = get_access_token(force_refresh=True, persist=True)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "refreshed": tok.get("refreshed"),
                        "ttl_sec": tok.get("ttl_sec"),
                        "expires_at": tok.get("expires_at"),
                        "source": tok.get("source"),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.cmd == "chat":
            print(
                json.dumps(
                    chat_completion(
                        args.prompt,
                        model=args.model,
                        system=args.system,
                        json_mode=bool(args.json_mode),
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.cmd == "image":
            print(
                json.dumps(
                    images_generate(
                        args.prompt,
                        out=Path(args.out),
                        model=args.model,
                        aspect_ratio=args.aspect,
                        resolution=args.resolution,
                        usage_root=args.root,
                        shot_id=args.shot_id,
                        job_id=args.job_id,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.cmd == "image-edit":
            print(
                json.dumps(
                    images_edit(
                        args.prompt,
                        image=args.image,
                        out=Path(args.out),
                        model=args.model,
                        aspect_ratio=args.aspect,
                        extra_images=list(args.ref or []) or None,
                        usage_root=args.root,
                        shot_id=args.shot_id,
                        job_id=args.job_id,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.cmd == "video":
            refs = list(args.ref or []) or None
            if args.wait:
                if not args.out:
                    raise GrokOAuthError("video --wait requires --out")
                print(
                    json.dumps(
                        video_generate(
                            args.prompt,
                            image=args.image,
                            out=Path(args.out),
                            model=args.model,
                            duration=args.duration,
                            aspect_ratio=args.aspect,
                            resolution=args.resolution,
                            reference_images=refs,
                            timeout_sec=args.timeout,
                            usage_root=args.root,
                            shot_id=args.shot_id,
                            job_id=args.job_id,
                        ),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(
                    json.dumps(
                        video_submit(
                            args.prompt,
                            image=args.image,
                            model=args.model,
                            duration=args.duration,
                            aspect_ratio=args.aspect,
                            resolution=args.resolution,
                            reference_images=refs,
                            usage_root=args.root,
                            shot_id=args.shot_id,
                            job_id=args.job_id,
                        ),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return 0
        if args.cmd == "video-status":
            if args.wait or args.out:
                print(
                    json.dumps(
                        video_wait(
                            args.request_id,
                            out=Path(args.out) if args.out else None,
                            timeout_sec=args.timeout,
                            usage_root=args.root,
                            generation_id=args.generation_id,
                        ),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(
                    json.dumps(
                        video_status(
                            args.request_id,
                            usage_root=args.root,
                            generation_id=args.generation_id,
                        ),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return 0
        if args.cmd == "tts":
            text = args.text
            if args.text_file:
                text = Path(args.text_file).expanduser().read_text(encoding="utf-8")
            if not text:
                raise GrokOAuthError("tts requires --text or --text-file")
            print(
                json.dumps(
                    tts_speak(
                        text,
                        out=Path(args.out),
                        voice_id=args.voice_id,
                        language=args.language,
                        speed=args.speed,
                        with_timestamps=bool(args.timestamps),
                        codec=args.codec,
                        usage_root=args.root,
                        shot_id=args.shot_id,
                        job_id=args.job_id,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.cmd == "voices":
            print(json.dumps(tts_list_voices(), ensure_ascii=False, indent=2))
            return 0
    except GrokOAuthError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
