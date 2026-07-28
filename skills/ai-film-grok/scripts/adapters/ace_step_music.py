#!/usr/bin/env python3
"""Generate one approved-candidate instrumental track with local ACE-Step.

This is deliberately a small command adapter for the private audio node: the
node owns its model paths, while the caller supplies only prompt, duration,
seed, and output path.  It never fetches models during inference.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _args()
    prompt = args.prompt.strip()
    if not 1 <= len(prompt) <= 512:
        raise SystemExit("prompt must contain 1-512 characters")
    if not 10 <= args.duration <= 600:
        raise SystemExit("ACE-Step duration must be between 10 and 600 seconds")

    model_root = Path(
        os.environ.get("ACESTEP_CHECKPOINTS_DIR", r"C:\\aifilm-audio-node\\models\\ace-step")
    ).resolve()
    required_checkpoints = (
        "acestep-v15-turbo",
        "acestep-5Hz-lm-1.7B",
        "vae",
        "Qwen3-Embedding-0.6B",
    )
    if any(
        not any((model_root / checkpoint).rglob("*.safetensors"))
        for checkpoint in required_checkpoints
    ):
        raise SystemExit("ACE-Step checkpoints are unavailable")
    os.environ["ACESTEP_CHECKPOINTS_DIR"] = str(model_root)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler

    args.out.parent.mkdir(parents=True, exist_ok=True)
    work = args.out.parent / f".{args.out.stem}.ace-step-{args.seed}"
    work.mkdir(parents=True, exist_ok=True)
    dit = AceStepHandler()
    status, ready = dit.initialize_service(
        project_root="", config_path="acestep-v15-turbo", device="cuda"
    )
    if not ready:
        raise RuntimeError(f"ACE-Step initialization failed: {status}")
    lm = LLMHandler()
    lm.initialize(
        checkpoint_dir=str(model_root),
        lm_model_path="acestep-5Hz-lm-1.7B",
        backend="pt",
        device="cuda",
    )
    params = GenerationParams(
        task_type="text2music",
        caption=prompt,
        lyrics="[Instrumental]",
        instrumental=True,
        duration=args.duration,
        inference_steps=8,
        shift=3.0,
        thinking=False,
        seed=args.seed,
    )
    config = GenerationConfig(
        batch_size=1, use_random_seed=False, seeds=[args.seed], audio_format="wav"
    )
    result = generate_music(dit, lm, params, config, save_dir=str(work))
    if not result.success or not result.audios:
        raise RuntimeError(f"ACE-Step generation failed: {result.error or 'no audio returned'}")
    source = Path(str(result.audios[0].get("path") or ""))
    if not source.is_file():
        raise RuntimeError("ACE-Step generation did not write audio")
    shutil.copyfile(source, args.out)


if __name__ == "__main__":
    main()
