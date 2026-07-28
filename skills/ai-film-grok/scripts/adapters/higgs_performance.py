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
        f"{_scene_text(cue)}\n"
        "<|scene_desc_end|>"
    )


def _scene_text(cue: str) -> str:
    return (
        "A single adult non-verbal performance is recorded in a quiet room. "
        "No intelligible words, no dialogue, no singing, no music, and no background effects. "
        f"Performance cue: {cue}"
    )


def _require_files(root: Path, names: tuple[str, ...], label: str) -> None:
    missing = [name for name in names if not (root / name).is_file()]
    if missing:
        raise SystemExit(f"{label} is incomplete: {', '.join(missing)}")


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
    _require_files(
        model_path,
        (
            "model.safetensors",
            "config.json",
            "processor_config.json",
            "tokenizer_config.json",
            "tokenizer.json",
            "chat_template.jinja",
        ),
        "Higgs generation model",
    )
    tokenizer_path = Path(
        os.environ.get(
            "HIGGS_PERFORMANCE_TOKENIZER_PATH",
            r"C:\\aifilm-audio-node\\models\\higgs-v2-tokenizer",
        )
    ).resolve()
    _require_files(
        tokenizer_path,
        ("model.safetensors", "config.json", "preprocessor_config.json"),
        "Higgs audio tokenizer",
    )

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import numpy as np
    import soundfile as sf
    import torch
    from transformers import AutoProcessor, HiggsAudioV2ForConditionalGeneration

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    processor = AutoProcessor.from_pretrained(str(model_path), local_files_only=True)
    model = HiggsAudioV2ForConditionalGeneration.from_pretrained(
        str(model_path),
        torch_dtype=torch.bfloat16,
        local_files_only=True,
    ).to("cuda")
    # The processor owns a separate DAC decoder; it must share the model device.
    processor.audio_tokenizer.to(model.device)
    conversation = [
        {
            "role": "system",
            "content": [{"type": "text", "text": "Generate audio following instruction."}],
        },
        {"role": "scene", "content": [{"type": "text", "text": _scene_text(cue)}]},
        {
            "role": "user",
            "content": [{"type": "text", "text": "Perform the requested non-verbal audio now."}],
        },
    ]
    inputs = processor.apply_chat_template(
        conversation,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        sampling_rate=24000,
        return_tensors="pt",
    ).to(model.device)
    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=_max_new_tokens(args.duration),
            do_sample=True,
            temperature=0.45,
            top_p=0.95,
            top_k=50,
        )
    decoded = processor.batch_decode(outputs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    processor.save_audio(decoded, str(args.out))
    audio, sampling_rate = sf.read(args.out, dtype="float32")
    maximum_samples = round(args.duration * sampling_rate)
    if audio.size <= 0:
        raise RuntimeError("Higgs generation did not return audio")
    sf.write(args.out, audio[:maximum_samples], sampling_rate, subtype="PCM_16")


if __name__ == "__main__":
    main()
