#!/usr/bin/env python3
"""A/B TTS rehearse: same nar line through multiple backends → receipts/tts-ab/.

  aifilm tts-ab --root <film> --shot shot01 --backends edge,voicebox

Does not change film-spec tts_backend. Skips unready backends with status=skip.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from util import read_json

AUDIO_DIR_REL = "receipts/tts-ab"
MANIFEST_NAME = "manifest.json"


class TTSAbError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _shot_nar(spec: dict[str, Any], shot_id: str) -> tuple[str, str]:
    """Return (nar_text, vo_voice_default)."""
    voice = str(spec.get("vo_voice") or "zh-CN-XiaoxiaoNeural")
    for shot in spec.get("shots") or []:
        if not isinstance(shot, dict):
            continue
        if str(shot.get("id") or shot.get("shot_id") or "") != shot_id:
            continue
        nar = str(shot.get("nar") or shot.get("narration") or "").strip()
        if not nar:
            raise TTSAbError(f"shot {shot_id!r} has empty nar")
        sv = shot.get("vo_voice") or shot.get("voice")
        if sv:
            voice = str(sv)
        return nar, voice
    raise TTSAbError(f"shot_id {shot_id!r} not found in film-spec")


def _safe_name(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s)[:80]


def run_tts_ab(
    root: Path,
    *,
    shot_id: str,
    backends: list[str],
    voice: str | None = None,
    text: str | None = None,
    spec_path: Path | None = None,
) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise TTSAbError(f"root not a directory: {root}")

    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    from tts_backend import TTSError, probe, synthesize  # type: ignore

    sp = Path(spec_path).expanduser().resolve() if spec_path else (root / "film-spec.json")
    nar = (text or "").strip()
    use_voice = (voice or "").strip()
    if not nar:
        if not sp.is_file():
            raise TTSAbError(f"film-spec missing: {sp} (or pass --text)")
        spec = read_json(sp) or {}
        nar, default_voice = _shot_nar(spec, shot_id)
        if not use_voice:
            use_voice = default_voice
    if not use_voice:
        use_voice = "zh-CN-XiaoxiaoNeural"

    info = probe()
    out_dir = root / AUDIO_DIR_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for be in backends:
        be_l = str(be).strip().lower()
        if not be_l:
            continue
        entry: dict[str, Any] = {
            "backend": be_l,
            "status": "pending",
            "path": None,
            "error": None,
            "voice": use_voice,
        }
        ready_map = info.get("ready") or info.get("backends") or {}
        # edge always "ready" if import ok
        is_ready = (
            bool(ready_map.get(be_l))
            if be_l != "edge"
            else bool((info.get("backends") or {}).get("edge", True))
        )
        if be_l == "voicebox":
            is_ready = bool(info.get("voicebox_ok") or (info.get("backends") or {}).get("voicebox"))
        if be_l == "auto":
            entry["status"] = "skip"
            entry["error"] = "auto not allowed in tts-ab; list concrete backends"
            results.append(entry)
            continue
        if not is_ready:
            entry["status"] = "skip"
            entry["error"] = f"backend {be_l!r} not ready" + (
                f": {info.get('voicebox_error')}" if be_l == "voicebox" else ""
            )
            results.append(entry)
            continue

        out_path = out_dir / f"{_safe_name(shot_id)}-{_safe_name(be_l)}.wav"
        # edge writes mp3 often — keep extension flexible via synthesize path
        if be_l == "edge":
            out_path = out_dir / f"{_safe_name(shot_id)}-{_safe_name(be_l)}.mp3"
        try:
            # voicebox rejects Neural names — synthesize handles strip
            synth = synthesize(
                nar,
                out_path,
                backend=be_l,
                voice=use_voice,
                allow_network_fallback=False,
            )
            # synthesize may write .mp3 even if we asked wav
            final_path = Path(synth.get("path") or out_path)
            if not final_path.is_file() or final_path.stat().st_size < 200:
                raise TTSError(f"empty/tiny audio: {final_path}")
            entry["status"] = "ok"
            entry["path"] = str(final_path)
            entry["voice"] = synth.get("voice") or use_voice
            entry["used_backend"] = synth.get("backend")
            entry["bytes"] = final_path.stat().st_size
        except Exception as exc:  # noqa: BLE001 — record per-backend
            entry["status"] = "fail"
            entry["error"] = str(exc)[:400]
        results.append(entry)

    ok_n = sum(1 for r in results if r.get("status") == "ok")
    manifest = {
        "ok": ok_n > 0,
        "kind": "ai-film-tts-ab",
        "schema_version": 1,
        "at": utc_now(),
        "root": str(root),
        "shot_id": shot_id,
        "nar": nar,
        "nar_chars": len(nar),
        "backends_requested": backends,
        "results": results,
        "audio_dir": str(out_dir),
        "note": "Compare ears; lock vo_voice / VOICEBOX_PROFILE before final. Does not change film-spec.",
    }
    man_path = out_dir / MANIFEST_NAME
    # merge into shot-specific manifest name to avoid clobbering multi-shot
    man_path = out_dir / f"manifest-{_safe_name(shot_id)}.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(man_path)
    return manifest


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="tts_ab", description="A/B TTS comparison for one shot")
    p.add_argument("--root", required=True)
    p.add_argument("--shot", "--shot-id", dest="shot_id", required=True)
    p.add_argument(
        "--backends",
        default="edge,voicebox",
        help="Comma-separated backends (default edge,voicebox)",
    )
    p.add_argument("--voice", default=None)
    p.add_argument("--text", default=None, help="Override nar text")
    p.add_argument("--spec", default=None)
    args = p.parse_args(argv)
    backends = [b.strip() for b in str(args.backends).split(",") if b.strip()]
    try:
        man = run_tts_ab(
            Path(args.root),
            shot_id=str(args.shot_id),
            backends=backends,
            voice=args.voice,
            text=args.text,
            spec_path=Path(args.spec) if args.spec else None,
        )
    except TTSAbError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(man, ensure_ascii=False, indent=2))
    return 0 if man.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
