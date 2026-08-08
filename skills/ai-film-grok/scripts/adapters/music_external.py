#!/usr/bin/env python3
"""External AI music adapter for ai-film-grok (BGM quality upgrade).

Wire (config.env):
  AIFILM_MUSIC_ARGV=["python3","$HOME/.grok/skills/ai-film-grok/scripts/adapters/music_external.py",
    "--out","{out}","--duration","{duration}","--mood","{mood}","--seed","{seed}","--prompt","{prompt}"]
  # Optional HTTP backend (ACE-Step / community server):
  MUSIC_GEN_BASE_URL=http://127.0.0.1:7860
  MUSIC_GEN_ENDPOINT=/generate
  # MUSIC_GEN_LICENSE=ACE-Step MIT — verify before commercial claim
  # AIFILM_MUSIC_REQUIRE=1   # fail final if gen fails (default: fall back to procedural)

  python3 music_external.py doctor
  python3 music_external.py --out /tmp/bgm.wav --duration 30 --mood rnb --prompt "late night rnb instrumental"

Place many royalty-free beds in assets/bgm/rnb/*.wav for pool rotation without AI.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from config_loader import get_config

_CFG = get_config()

MIN_BYTES = 500


def _base() -> str:
    return _CFG.music_gen_base_url.rstrip("/")


def _endpoint() -> str:
    ep = _CFG.music_gen_endpoint.strip()
    return ep if ep.startswith("/") else f"/{ep}"


def doctor() -> int:
    base = _base()
    print(f"MUSIC_GEN_BASE_URL={base}")
    print(f"MUSIC_GEN_ENDPOINT={_endpoint()}")
    url = f"{base}/"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            print(f"GET / → HTTP {resp.status}")
            print("ok: server reachable")
            return 0
    except urllib.error.HTTPError as exc:
        if exc.code in {404, 405, 422}:
            print(f"GET / → HTTP {exc.code} (server up)")
            print("ok: server reachable")
            return 0
        print(f"fail: HTTP {exc.code}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"fail: unreachable ({exc})")
        print("hint: start ACE-Step / music API, or put beds in assets/bgm/rnb/")
        return 1


def _http_generate(prompt: str, duration: float, mood: str, seed: int, out: Path) -> None:
    url = f"{_base()}{_endpoint()}"
    payload = {
        "prompt": prompt,
        "duration": duration,
        "mood": mood,
        "seed": seed,
        "instrumental": True,
        "lyrics": "",
    }
    extra = _CFG.music_gen_extra_json.strip()
    if extra:
        with contextlib.suppress(json.JSONDecodeError):
            payload.update(json.loads(extra))
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "audio/wav, audio/mpeg, application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=float(_CFG.music_timeout)) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"music_gen HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"music_gen unreachable at {url}: {exc}") from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    if "application/json" in ctype:
        obj = json.loads(raw.decode("utf-8"))
        # common: path / url / audio b64
        if obj.get("path") and Path(str(obj["path"])).is_file():
            raw = Path(str(obj["path"])).read_bytes()
        elif obj.get("url"):
            with urllib.request.urlopen(str(obj["url"]), timeout=120) as r2:
                raw = r2.read()
        elif obj.get("audio") or obj.get("audio_base64"):
            import base64

            raw = base64.b64decode(obj.get("audio") or obj.get("audio_base64"))
        else:
            raise SystemExit(f"music_gen JSON missing audio: keys={list(obj)[:12]}")

    tmp = out.with_suffix(".bin")
    tmp.write_bytes(raw)
    if len(raw) >= 12 and raw[:4] == b"RIFF":
        out.write_bytes(raw)
        tmp.unlink(missing_ok=True)
        return
    # ffmpeg normalize to wav mono/stereo pcm
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(tmp),
        "-t",
        f"{duration:.3f}",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(out),
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"ffmpeg music normalize timed out after {exc.timeout}s") from exc
    tmp.unlink(missing_ok=True)
    if p.returncode != 0 or not out.is_file() or out.stat().st_size < MIN_BYTES:
        raise SystemExit(f"ffmpeg music normalize failed: {(p.stderr or '')[-300:]}")


class MusicExternalProvider:
    """Registry-facing surface for the optional external BGM backend."""

    def resolve_bed(
        self,
        out: Path,
        duration: float,
        mood: str = "rnb",
        seed: int = 0,
        prompt: str = "",
    ) -> Path:
        chosen_prompt = prompt.strip() or (
            f"instrumental {mood} background music, soft cinematic, no vocals"
        )
        _http_generate(chosen_prompt, float(duration), mood, int(seed), out)
        return out


def main() -> int:
    ap = argparse.ArgumentParser(description="External AI music for ai-film-grok BGM")
    ap.add_argument("command", nargs="?", default="", help="doctor")
    ap.add_argument("--out", default="")
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--mood", default="rnb")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--title", default="")
    args = ap.parse_args()

    if args.command == "doctor":
        return doctor()

    if not args.out:
        raise SystemExit("usage: music_external.py doctor | --out … --duration …")
    prompt = (args.prompt or "").strip() or (
        f"instrumental {args.mood} background music, soft cinematic, no vocals"
    )
    if args.title:
        prompt = f"{prompt}, for film {args.title}"
    _http_generate(prompt, float(args.duration), args.mood, int(args.seed), Path(args.out))
    print(f"music_external ok → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
