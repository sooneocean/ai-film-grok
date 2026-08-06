#!/usr/bin/env python3
"""Qwen3-TTS adapter.

The adapter is optional and never imported by the default Edge path.  It uses
the official ``qwen-tts`` Python package when installed and writes a WAV file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--voice", default="")
    ap.add_argument("--performance-file", default="")
    args = ap.parse_args()
    try:
        import soundfile as sf  # type: ignore
        import torch  # type: ignore
        from qwen_tts import Qwen3TTSModel  # type: ignore
    except Exception as exc:
        raise SystemExit(
            f"Qwen3-TTS unavailable: install qwen-tts, torch, soundfile ({exc})"
        ) from exc

    from config_loader import get_config
    from performance_cue import compile_instruction, normalize_performance_cue

    cfg = get_config()
    text = Path(args.text_file).read_text(encoding="utf-8")
    cue = normalize_performance_cue(
        json.loads(Path(args.performance_file).read_text(encoding="utf-8"))
        if args.performance_file
        else None
    )
    device = (
        cfg.qwen3_tts_device
        if cfg.qwen3_tts_device != "auto"
        else ("cuda:0" if torch.cuda.is_available() else "cpu")
    )
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
    model = Qwen3TTSModel.from_pretrained(cfg.qwen3_tts_model, device_map=device, dtype=dtype)
    language = cue.get("language") or os.environ.get("QWEN3_TTS_LANGUAGE", "Chinese")
    voice = args.voice or os.environ.get("QWEN3_TTS_SPEAKER", "Vivian")
    instruction = compile_instruction(cue)
    if cfg.qwen3_tts_ref_audio:
        wavs, sr = model.generate_voice_clone(
            text=text,
            language=language,
            ref_audio=cfg.qwen3_tts_ref_audio,
            ref_text=cfg.qwen3_tts_ref_text,
            instruct=instruction,
        )
    elif "VoiceDesign" in cfg.qwen3_tts_model:
        wavs, sr = model.generate_voice_design(text=text, language=language, instruct=instruction)
    else:
        wavs, sr = model.generate_custom_voice(
            text=text, language=language, speaker=voice, instruct=instruction
        )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, wavs[0], sr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
