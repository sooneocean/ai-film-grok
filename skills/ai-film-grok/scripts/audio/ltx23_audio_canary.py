#!/usr/bin/env python3
"""Compile the experimental LTX-2.3 audio-conditioned I2V pilot workflow.

Migrated from scripts/ltx23_audio_canary.py into the audio package (P3-1).
_ROOT depth adjusted: this file now lives at scripts/audio/, so three .parent
steps reach the skill package root that owns templates/.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_TEMPLATE = _ROOT / "templates" / "comfy" / "ltx23-native-i2v-pilot-api.json"


def compile_audio_conditioned_workflow(
    *, image_name: str, audio_name: str, prompt: str, seed: int, frames: int, filename_prefix: str
) -> dict[str, dict]:
    """Bind a supplied voice track into the initial LTX AV latent.

    This is an audio-conditioned I2V experiment, not a claim that LTX is a
    dedicated phoneme-to-mouth model.
    """
    if not image_name or not audio_name or not prompt or not filename_prefix:
        raise ValueError("image, audio, prompt, and filename prefix are required")
    if not 9 <= frames <= 241 or (frames - 1) % 8:
        raise ValueError("frames must be 8n+1 between 9 and 241")

    graph = json.loads(_TEMPLATE.read_text(encoding="utf-8"))
    graph["source"]["inputs"]["image"] = image_name
    graph["303"]["inputs"]["text"] = prompt
    graph["277"]["inputs"]["noise_seed"] = seed
    graph["save"]["inputs"]["filename_prefix"] = filename_prefix
    graph["295"]["inputs"]["length"] = frames
    graph["305"]["inputs"]["frames_number"] = frames
    graph["audio_source"] = {"class_type": "LoadAudio", "inputs": {"audio": audio_name}}
    graph["audio_encode"] = {
        "class_type": "LTXVAudioVAEEncode",
        "inputs": {"audio": ["audio_source", 0], "audio_vae": ["279", 0]},
    }
    graph["318"]["inputs"]["audio_latent"] = ["audio_encode", 0]
    return graph


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-name", required=True)
    parser.add_argument("--audio-name", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--frames", type=int, required=True)
    parser.add_argument("--filename-prefix", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    graph = compile_audio_conditioned_workflow(
        image_name=args.image_name,
        audio_name=args.audio_name,
        prompt=args.prompt,
        seed=args.seed,
        frames=args.frames,
        filename_prefix=args.filename_prefix,
    )
    args.out.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
