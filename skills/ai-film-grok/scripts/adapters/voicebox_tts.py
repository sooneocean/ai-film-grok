#!/usr/bin/env python3
"""Voicebox (local) TTS adapter for ai-film-grok.

Voicebox = open-source local AI voice studio (https://github.com/jamiepine/voicebox).
Requires the desktop app (or backend) listening on 127.0.0.1:17493 with at least
one voice profile.

Wire as first-class backend (preferred)::

  AIFILM_TTS_BACKEND=voicebox
  VOICEBOX_BASE_URL=http://127.0.0.1:17493
  VOICEBOX_PROFILE=<profile name or id>
  VOICEBOX_LANGUAGE=zh
  # optional: VOICEBOX_ENGINE=qwen|kokoro|chatterbox|...

Or via external argv::

  AIFILM_TTS_BACKEND=external
  AIFILM_TTS_ARGV=["python3","$HOME/.grok/skills/ai-film-grok/scripts/adapters/voicebox_tts.py",
                  "--text-file","{text_file}","--out","{out}","--voice","{voice}"]

CLI::

  python3 voicebox_tts.py --text-file line.txt --out out.wav --voice "MyClone"
  python3 voicebox_tts.py doctor
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE = "http://127.0.0.1:17493"
DEFAULT_LANGUAGE = "zh"
DEFAULT_ENGINE = "qwen"
# Long enough for cold model load on first generation
DEFAULT_TIMEOUT = 600
POLL_INTERVAL = 0.6
POLL_MAX_SEC = 600


def _load_config_env() -> None:
    cfg = (
        Path(__file__).resolve().parents[2] / "config.env"
        if (Path(__file__).resolve().parents[2] / "config.env").is_file()
        else Path.home() / ".grok/skills/ai-film-grok/config.env"
    )
    if not cfg.is_file():
        return
    for line in cfg.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def base_url() -> str:
    return (
        os.environ.get("VOICEBOX_BASE_URL") or os.environ.get("AIFILM_VOICEBOX_URL") or DEFAULT_BASE
    ).rstrip("/")


def default_profile() -> str:
    return (
        os.environ.get("VOICEBOX_PROFILE")
        or os.environ.get("VOICEBOX_PROFILE_ID")
        or os.environ.get("AIFILM_VOICEBOX_PROFILE")
        or ""
    ).strip()


def default_language() -> str:
    return (
        os.environ.get("VOICEBOX_LANGUAGE")
        or os.environ.get("AIFILM_VOICEBOX_LANGUAGE")
        or DEFAULT_LANGUAGE
    ).strip() or DEFAULT_LANGUAGE


def default_engine() -> str | None:
    eng = (
        os.environ.get("VOICEBOX_ENGINE") or os.environ.get("AIFILM_VOICEBOX_ENGINE") or ""
    ).strip()
    return eng or None


def _http_json(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: float = 30,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise SystemExit(f"voicebox HTTP {exc.code} {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"voicebox unreachable at {url}: {exc.reason}. "
            "Start Voicebox app (or backend on :17493)."
        ) from exc


def _http_bytes(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, method="GET", headers={"Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise SystemExit(f"voicebox download HTTP {exc.code}: {detail}") from exc


def _post_stream_wav(
    url: str,
    body: dict[str, Any],
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "audio/wav"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise SystemExit(f"voicebox stream HTTP {exc.code}: {detail}") from exc


def health() -> dict[str, Any]:
    try:
        obj = _http_json("GET", f"{base_url()}/health", timeout=5)
        return {"ok": True, "health": obj}
    except SystemExit as exc:
        return {"ok": False, "error": str(exc)}


def list_profiles() -> list[dict[str, Any]]:
    obj = _http_json("GET", f"{base_url()}/profiles", timeout=15)
    if not isinstance(obj, list):
        raise SystemExit(f"voicebox /profiles unexpected response: {type(obj)}")
    return obj


def resolve_profile_id(voice: str) -> tuple[str, str]:
    """Resolve profile name or id → (id, name)."""
    needle = (voice or default_profile()).strip()
    profiles = list_profiles()
    if not profiles:
        raise SystemExit("voicebox has no voice profiles — open the app, create/clone one first")
    if not needle:
        # Prefer non-import default: first non-import profile
        for p in profiles:
            if str(p.get("voice_type") or "") != "import":
                return str(p["id"]), str(p.get("name") or p["id"])
        p0 = profiles[0]
        return str(p0["id"]), str(p0.get("name") or p0["id"])

    # Exact id match
    for p in profiles:
        if str(p.get("id")) == needle:
            return str(p["id"]), str(p.get("name") or p["id"])
    # Case-insensitive name match
    low = needle.lower()
    for p in profiles:
        if str(p.get("name") or "").lower() == low:
            return str(p["id"]), str(p.get("name") or p["id"])
    # Prefix / contains
    hits = [p for p in profiles if low in str(p.get("name") or "").lower()]
    if len(hits) == 1:
        p = hits[0]
        return str(p["id"]), str(p.get("name") or p["id"])
    names = ", ".join(f"{p.get('name')}({p.get('id')})" for p in profiles[:12])
    raise SystemExit(f"voicebox profile {needle!r} not found. Available: {names}")


def _looks_like_wav(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def _ffmpeg_to_target(src: Path, dest: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "44100",
        "-sample_fmt",
        "s16",
        str(dest),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"ffmpeg convert failed: {(p.stderr or '')[-400:]}")


def _write_audio(data: bytes, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    suffix = out.suffix.lower()
    if suffix == ".wav" or _looks_like_wav(data):
        if suffix == ".wav":
            out.write_bytes(data)
            return out
        # requested .mp3 but we have wav → convert
        tmp = out.with_suffix(".wav")
        tmp.write_bytes(data)
        if suffix in {".mp3", ".m4a", ".aac"}:
            _ffmpeg_to_target(tmp, out)
            return out
        out.write_bytes(data)
        return out
    # opaque bytes — write as-is
    out.write_bytes(data)
    return out


def synthesize_stream(
    text: str,
    *,
    profile_id: str,
    language: str,
    engine: str | None = None,
    instruct: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    """Prefer POST /generate/stream → raw WAV bytes (no history pollution)."""
    body: dict[str, Any] = {
        "profile_id": profile_id,
        "text": text,
        "language": language,
        "normalize": True,
    }
    if engine:
        body["engine"] = engine
    if instruct:
        body["instruct"] = instruct
    return _post_stream_wav(f"{base_url()}/generate/stream", body, timeout=timeout)


def synthesize_async_poll(
    text: str,
    *,
    profile_id: str,
    language: str,
    engine: str | None = None,
    instruct: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    """Fallback: POST /generate → poll history → GET /audio/{id}."""
    body: dict[str, Any] = {
        "profile_id": profile_id,
        "text": text,
        "language": language,
        "normalize": True,
    }
    if engine:
        body["engine"] = engine
    if instruct:
        body["instruct"] = instruct
    gen = _http_json("POST", f"{base_url()}/generate", body=body, timeout=30)
    if not isinstance(gen, dict) or not gen.get("id"):
        raise SystemExit(f"voicebox /generate bad response: {gen!r}")
    gid = str(gen["id"])
    deadline = time.time() + min(timeout, POLL_MAX_SEC)
    last_status = gen.get("status") or "generating"
    while time.time() < deadline:
        row = _http_json("GET", f"{base_url()}/history/{gid}", timeout=15)
        if not isinstance(row, dict):
            time.sleep(POLL_INTERVAL)
            continue
        last_status = row.get("status") or last_status
        if last_status == "completed":
            return _http_bytes(f"{base_url()}/audio/{gid}", timeout=60)
        if last_status == "failed":
            raise SystemExit(f"voicebox generation failed: {row.get('error') or row}")
        time.sleep(POLL_INTERVAL)
    raise SystemExit(
        f"voicebox generation timed out after {timeout}s (last status={last_status!r}, id={gid})"
    )


def synthesize(
    text: str,
    out: Path,
    *,
    voice: str = "",
    language: str | None = None,
    engine: str | None = None,
    instruct: str | None = None,
    prefer_stream: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise SystemExit("empty text")
    lang = (language or default_language()).strip() or DEFAULT_LANGUAGE
    eng = engine if engine is not None else default_engine()
    pid, pname = resolve_profile_id(voice)
    audio: bytes | None = None
    mode = "stream"
    if prefer_stream:
        try:
            audio = synthesize_stream(
                text,
                profile_id=pid,
                language=lang,
                engine=eng,
                instruct=instruct,
                timeout=timeout,
            )
        except SystemExit:
            mode = "async_poll"
            audio = None
    if audio is None:
        mode = "async_poll"
        audio = synthesize_async_poll(
            text,
            profile_id=pid,
            language=lang,
            engine=eng,
            instruct=instruct,
            timeout=timeout,
        )
    if not audio or len(audio) < 200:
        raise SystemExit(f"voicebox returned empty/tiny audio ({len(audio) if audio else 0} bytes)")
    path = _write_audio(audio, out)
    return {
        "ok": True,
        "backend": "voicebox",
        "mode": mode,
        "profile_id": pid,
        "profile_name": pname,
        "language": lang,
        "engine": eng,
        "out": str(path),
        "bytes": len(audio),
        "chars": len(text),
        "base_url": base_url(),
    }


def doctor() -> dict[str, Any]:
    h = health()
    if not h.get("ok"):
        return {
            "ok": False,
            "base_url": base_url(),
            "error": h.get("error"),
            "hint": "Install/start Voicebox (https://github.com/jamiepine/voicebox); API default :17493",
        }
    try:
        profiles = list_profiles()
    except SystemExit as exc:
        return {"ok": False, "base_url": base_url(), "error": str(exc)}
    default = default_profile()
    resolved = None
    try:
        if default or profiles:
            pid, pname = resolve_profile_id(default)
            resolved = {"id": pid, "name": pname}
    except SystemExit as exc:
        resolved = {"error": str(exc)}
    return {
        "ok": bool(profiles) and (resolved is None or "id" in (resolved or {})),
        "base_url": base_url(),
        "profile_count": len(profiles),
        "profiles": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "language": p.get("language"),
                "voice_type": p.get("voice_type"),
            }
            for p in profiles[:20]
        ],
        "default_profile_env": default or None,
        "resolved_default": resolved,
        "language": default_language(),
        "engine": default_engine(),
    }


def main() -> int:
    _load_config_env()
    ap = argparse.ArgumentParser(description="Voicebox local TTS for ai-film-grok")
    ap.add_argument("cmd", nargs="?", default="synth", choices=["synth", "doctor", "profiles"])
    ap.add_argument("--text-file", default="")
    ap.add_argument("--text", default="")
    ap.add_argument("--out", default="", help="Output .wav or .mp3 path")
    ap.add_argument("--voice", default="", help="Voicebox profile name or id")
    ap.add_argument("--language", default="", help="zh|en|ja|…")
    ap.add_argument("--engine", default="", help="qwen|kokoro|chatterbox|…")
    ap.add_argument("--instruct", default="", help="Optional delivery instruction (Qwen)")
    ap.add_argument("--no-stream", action="store_true", help="Force async poll path")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = ap.parse_args()

    if args.cmd == "doctor":
        print(json.dumps(doctor(), ensure_ascii=False, indent=2))
        return 0 if doctor().get("ok") else 1
    if args.cmd == "profiles":
        print(json.dumps(list_profiles(), ensure_ascii=False, indent=2))
        return 0

    text = args.text.strip()
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit("--text or --text-file required")
    if not args.out:
        raise SystemExit("--out required")
    meta = synthesize(
        text,
        Path(args.out),
        voice=args.voice,
        language=args.language or None,
        engine=args.engine or None,
        instruct=args.instruct or None,
        prefer_stream=not args.no_stream,
        timeout=args.timeout,
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
