#!/usr/bin/env python3
"""ElevenLabs TTS adapter for ai-film-grok (external backend).

Wire:
  export ELEVENLABS_API_KEY=...
  export ELEVENLABS_VOICE_ID=cgSgspJ2msm6clMCkdW9   # optional; or pass --voice
  export AIFILM_TTS_BACKEND=external
  export AIFILM_TTS_ARGV='["python3","$HOME/.grok/skills/ai-film-grok/scripts/adapters/elevenlabs_tts.py","--text-file","{text_file}","--out","{out}","--voice","{voice}"]'

Reads key from env or skill config.env (not inherited via minimal_subprocess_env —
this adapter reloads config itself).
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_VOICE = "cgSgspJ2msm6clMCkdW9"  # Jessica — young, cute, playful
DEFAULT_MODEL = "eleven_multilingual_v2"
API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def _load_config_env() -> None:
    cfg = (Path(__file__).resolve().parents[2] / "config.env" if (Path(__file__).resolve().parents[2] / "config.env").is_file() else Path.home() / ".grok/skills/ai-film-grok/config.env")
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


def _api_key() -> str:
    key = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY not set (put in config.env chmod 600)")
    return key


def _synthesize(text: str, voice_id: str, model: str) -> bytes:
    url = API_URL.format(voice_id=voice_id)
    body = json.dumps(
        {
            "text": text,
            "model_id": model,
            "voice_settings": {
                "stability": 0.42,
                "similarity_boost": 0.78,
                "style": 0.55,
                "use_speaker_boost": True,
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "xi-api-key": _api_key(),
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise SystemExit(f"elevenlabs HTTP {exc.code}: {detail}") from exc


def _mp3_to_wav(mp3: Path, wav: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(mp3),
        "-ac",
        "1",
        "-ar",
        "44100",
        "-sample_fmt",
        "s16",
        str(wav),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"ffmpeg mp3→wav failed: {p.stderr[-300:]}")


def main() -> int:
    _load_config_env()
    ap = argparse.ArgumentParser(description="ElevenLabs TTS for ai-film-grok")
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--out", required=True, help="Output .wav or .mp3 path")
    ap.add_argument("--voice", default="", help="ElevenLabs voice_id")
    ap.add_argument("--model", default="", help="Model id override")
    args = ap.parse_args()

    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit("empty text")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    voice = (args.voice or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE).strip()
    model = (args.model or os.environ.get("ELEVENLABS_MODEL") or DEFAULT_MODEL).strip()

    audio = _synthesize(text, voice, model)
    # Always land a wav for render_final (it converts mp3→wav already, but wav is safest)
    if out.suffix.lower() == ".wav":
        mp3 = out.with_suffix(".mp3")
        mp3.write_bytes(audio)
        _mp3_to_wav(mp3, out)
    else:
        out.write_bytes(audio)
        if out.suffix.lower() == ".mp3":
            wav = out.with_suffix(".wav")
            _mp3_to_wav(out, wav)
    print(json.dumps({"ok": True, "voice": voice, "model": model, "out": str(out), "chars": len(text)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
