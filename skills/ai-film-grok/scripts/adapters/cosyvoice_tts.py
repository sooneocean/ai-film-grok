#!/usr/bin/env python3
"""CosyVoice 2 HTTP adapter for ai-film-grok (external backend).

Production path for Chinese storyteller quality upgrade (Apache 2.0, zero-shot ref).
Default remains edge in the skill; use this when you want local CN naturalness.

Wire (skill config.env, chmod 600):
  AIFILM_TTS_BACKEND=external
  COSYVOICE_BASE_URL=http://127.0.0.1:9880
  COSYVOICE_REF_WAV=/path/to/storyteller-ref.wav   # one character = one ref hash
  # COSYVOICE_SPEAKER=default
  # COSYVOICE_ENDPOINT=/tts
  AIFILM_TTS_ARGV=["python3","$HOME/.grok/skills/ai-film-grok/scripts/adapters/cosyvoice_tts.py","--text-file","{text_file}","--out","{out}","--voice","{voice}"]

film-spec:
  "tts_backend": "external",
  "vo_voice": "storyteller-ref-v1",
  "tts_allow_network_fallback": false

Requires a running CosyVoice (or CosyVoice2) HTTP server that accepts JSON and
returns audio bytes (wav/mp3). Community servers differ — set COSYVOICE_ENDPOINT
and COSYVOICE_PAYLOAD_STYLE if needed.

  python3 cosyvoice_tts.py doctor
  python3 cosyvoice_tts.py --text "话说那天夜里……" --out /tmp/cv-test.wav
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from config_loader import get_config

_CFG = get_config()

DEFAULT_BASE = "http://127.0.0.1:9880"
DEFAULT_ENDPOINT = "/tts"
# payload styles: shengwang | funaudio | openaiish
DEFAULT_STYLE = "shengwang"
MIN_AUDIO_BYTES = 500


def _base_url() -> str:
    return _CFG.cosyvoice_base_url.rstrip("/")


def _endpoint() -> str:
    ep = _CFG.cosyvoice_endpoint.strip()
    if not ep.startswith("/"):
        ep = "/" + ep
    return ep


def _style() -> str:
    return _CFG.cosyvoice_payload_style.strip().lower()


def _ref_wav() -> Path | None:
    raw = _CFG.cosyvoice_ref_wav.strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_file() else None


def _speaker(voice: str) -> str:
    return (voice or "").strip() or (_CFG.cosyvoice_speaker or "").strip() or "default"


def _build_payload(text: str, speaker: str, ref: Path | None) -> dict:
    style = _style()
    lang = _CFG.cosyvoice_language
    if style == "openaiish":
        body: dict = {"input": text, "voice": speaker, "model": "cosyvoice"}
        if ref is not None:
            body["reference_id"] = str(ref)
        return body
    if style == "funaudio":
        # Common FunAudioLLM / community zero-shot shape
        body = {
            "tts_text": text,
            "mode": "zero_shot" if ref is not None else "sft",
            "speaker": speaker,
            "language": lang,
        }
        if ref is not None:
            body["prompt_wav"] = str(ref)
            body["prompt_text"] = _CFG.cosyvoice_prompt_text
        return body
    # shengwang blog / simple API
    body = {"text": text, "speaker": speaker, "language": lang}
    if ref is not None:
        body["ref_wav"] = str(ref)
        # some servers want base64 inline
        if _CFG.cosyvoice_ref_as_b64:
            body["ref_audio_b64"] = base64.b64encode(ref.read_bytes()).decode("ascii")
    return body


def _http_post_audio(url: str, payload: dict, timeout: float = 120.0) -> bytes:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "audio/wav, audio/mpeg, application/json, */*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"cosyvoice HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"cosyvoice unreachable at {url}: {exc}. "
            "Start CosyVoice API (e.g. python api.py --port 9880) or fix COSYVOICE_BASE_URL."
        ) from exc

    if "application/json" in ctype:
        try:
            obj = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"cosyvoice returned invalid JSON: {exc}") from exc
        # common shapes: {audio: b64}, {data: b64}, {url: ...}
        b64 = obj.get("audio") or obj.get("data") or obj.get("audio_base64")
        if isinstance(b64, str) and b64:
            return base64.b64decode(b64)
        if obj.get("url"):
            with urllib.request.urlopen(str(obj["url"]), timeout=timeout) as r2:
                return r2.read()
        raise SystemExit(f"cosyvoice JSON has no audio field: keys={list(obj)[:12]}")
    return raw


def _looks_like_wav(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def _to_wav(raw: bytes, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if len(raw) < MIN_AUDIO_BYTES:
        raise SystemExit(f"cosyvoice empty/short audio ({len(raw)} B)")
    if _looks_like_wav(raw):
        out.write_bytes(raw)
        return
    tmp = out.with_suffix(out.suffix + ".bin")
    tmp.write_bytes(raw)
    # mp3 or unknown → ffmpeg
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(tmp),
        "-ac",
        "1",
        "-ar",
        "44100",
        "-sample_fmt",
        "s16",
        str(out),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if p.returncode != 0 or not out.is_file() or out.stat().st_size < MIN_AUDIO_BYTES:
        raise SystemExit(f"ffmpeg → wav failed: {(p.stderr or '')[-400:]}")


def doctor() -> int:
    base = _base_url()
    ref = _ref_wav()
    print(f"COSYVOICE_BASE_URL={base}")
    print(f"COSYVOICE_ENDPOINT={_endpoint()}")
    print(f"COSYVOICE_PAYLOAD_STYLE={_style()}")
    print(f"COSYVOICE_REF_WAV={ref or '(not set — sft/default speaker only)'}")
    # health: try GET /health or / then POST dry is too heavy; just TCP-ish GET root
    for path in ("/health", "/", _endpoint()):
        url = f"{base}{path}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                print(f"GET {path} → HTTP {resp.status}")
                print("ok: server reachable")
                return 0
        except urllib.error.HTTPError as exc:
            # 405 on POST-only endpoint still means server up
            if exc.code in {404, 405, 422, 400}:
                print(f"GET {path} → HTTP {exc.code} (server up)")
                print("ok: server reachable")
                return 0
        except Exception:
            continue
    print("fail: cannot reach CosyVoice server")
    return 1


def synthesize(text: str, out: Path, voice: str) -> None:
    text = text.strip()
    if not text:
        raise SystemExit("empty text")
    if voice and voice.startswith("zh-CN-") and "Neural" in voice:
        raise SystemExit(
            f"refusing Edge Neural name as CosyVoice voice: {voice!r}. "
            "Use speaker id or leave empty + COSYVOICE_SPEAKER / COSYVOICE_REF_WAV."
        )
    ref = _ref_wav()
    speaker = _speaker(voice)
    url = f"{_base_url()}{_endpoint()}"
    payload = _build_payload(text, speaker, ref)
    raw = _http_post_audio(url, payload)
    _to_wav(raw, out)
    print(f"cosyvoice ok → {out} ({out.stat().st_size} B) speaker={speaker} ref={ref or '-'}")


class CosyVoiceTTSProvider:
    """Adapter-registry compatibility surface for the existing CosyVoice client."""

    def synthesize(self, text: str, out: Path, voice: str = "") -> None:
        synthesize(text, out, voice)


def main() -> int:
    p = argparse.ArgumentParser(description="CosyVoice HTTP TTS for ai-film-grok")
    p.add_argument("command", nargs="?", default="", help="doctor (optional)")
    p.add_argument("--text", default="")
    p.add_argument("--text-file", default="")
    p.add_argument("--out", default="")
    p.add_argument("--voice", default="", help="speaker id (not Edge Neural name)")
    p.add_argument("--ref", default="", help="override COSYVOICE_REF_WAV for this call")
    args = p.parse_args()

    if args.command == "doctor":
        return doctor()

    if args.ref:
        os.environ["COSYVOICE_REF_WAV"] = args.ref

    text = Path(args.text_file).read_text(encoding="utf-8") if args.text_file else args.text
    if not args.out:
        raise SystemExit("usage: cosyvoice_tts.py doctor | --text … --out …")
    synthesize(text, Path(args.out), args.voice)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
