#!/usr/bin/env python3
"""Generate a local, non-verbal Higgs Audio performance candidate.

The private node calls this trusted adapter with a cue, desired duration and
seed.  It deliberately has no reference-audio argument: a future authorized
voice-reference workflow must be separate, auditable, and never cross the LAN
API as raw media.
"""

from __future__ import annotations

import argparse
import os
import random
from pathlib import Path


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _max_new_tokens(duration: float) -> int:
    """Constrain generation cost while retaining enough tokens for short takes."""
    return max(64, min(2048, round(duration * 50)))


def _system_prompt(cue: str) -> str:
    return (
        "Generate audio following instruction.\n\n"
        "<|scene_desc_start|>\n"
        "A single adult non-verbal performance is recorded in a quiet room. "
        "No intelligible words, no dialogue, no singing, no music, and no background effects. "
        f"Performance cue: {cue}\n"
        "<|scene_desc_end|>"
    )


def main() -> None:
    args = _args()
    cue = args.prompt.strip()
    if not 1 <= len(cue) <= 512:
        raise SystemExit("prompt must contain 1-512 characters")
    if not 1 <= args.duration <= 60:
        raise SystemExit("duration must be between 1 and 60 seconds")
    if isinstance(args.seed, bool):
        raise SystemExit("seed must be an integer")

    model_path = Path(
        os.environ.get(
            "HIGGS_PERFORMANCE_MODEL_PATH",
            r"C:\\aifilm-audio-node\\models\\higgs-v2-generation",
        )
    ).resolve()
    tokenizer_path = Path(
        os.environ.get(
            "HIGGS_PERFORMANCE_TOKENIZER_PATH",
            r"C:\\aifilm-audio-node\\models\\higgs-v2-tokenizer",
        )
    ).resolve()
    if not (model_path / "model.safetensors").is_file():
        raise SystemExit("Higgs generation checkpoint is unavailable")
    if not (tokenizer_path / "model.safetensors").is_file():
        raise SystemExit("Higgs audio tokenizer is unavailable")

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import numpy as np
    import soundfile as sf
    import torch
    from boson_multimodal.data_types import ChatMLSample, Message
    from boson_multimodal.serve.serve_engine import HiggsAudioServeEngine

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    engine = HiggsAudioServeEngine(str(model_path), str(tokenizer_path), device="cuda")
    result = engine.generate(
        chat_ml_sample=ChatMLSample(
            messages=[
                Message(role="system", content=_system_prompt(cue)),
                Message(role="user", content="Perform the requested non-verbal audio now."),
            ]
        ),
        max_new_tokens=_max_new_tokens(args.duration),
        temperature=0.45,
        top_p=0.95,
        top_k=50,
        stop_strings=["<|end_of_text|>", "<|eot_id|>"],
    )
    audio = np.asarray(result.audio, dtype=np.float32)
    maximum_samples = round(args.duration * result.sampling_rate)
    if audio.size <= 0:
        raise RuntimeError("Higgs generation did not return audio")
    audio = audio[:maximum_samples]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.out, audio, result.sampling_rate, subtype="PCM_16")


if __name__ == "__main__":
    main()
