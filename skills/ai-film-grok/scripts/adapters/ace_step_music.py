#!/usr/bin/env python3
"""Generate one approved-candidate instrumental track with local ACE-Step.

This is deliberately a small command adapter for the private audio node: the
node owns its model paths, while the caller supplies only prompt, duration,
seed, and output path.  It never fetches models during inference.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt")
    parser.add_argument("--duration", type=float)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--request-json", type=Path)
    parser.add_argument("--out-dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = _args()
    request: dict[str, object]
    if args.request_json:
        if not args.out_dir:
            raise SystemExit("--request-json requires --out-dir")
        raw = json.loads(args.request_json.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise SystemExit("batch request must be an object")
        request = raw
    else:
        if args.prompt is None or args.duration is None or args.seed is None or args.out is None:
            raise SystemExit("single mode requires --prompt --duration --seed --out")
        request = {
            "prompt": args.prompt,
            "duration": args.duration,
            "batch_size": 1,
            "seeds": [args.seed],
        }
    prompt = str(request.get("prompt") or "").strip()
    if not 1 <= len(prompt) <= 512:
        raise SystemExit("prompt must contain 1-512 characters")
    duration = float(request.get("duration") or 0)
    if not 10 <= duration <= 600:
        raise SystemExit("ACE-Step duration must be between 10 and 600 seconds")
    batch_size = int(request.get("batch_size") or 0)
    seeds = [int(seed) for seed in request.get("seeds") or []]  # type: ignore[arg-type]
    if not 1 <= batch_size <= 8 or len(seeds) != batch_size or len(set(seeds)) != batch_size:
        raise SystemExit("ACE-Step batch requires 1-8 unique seeds")
    task_type = str(request.get("task_type") or "text2music")
    if task_type not in {"text2music", "cover", "repaint"}:
        raise SystemExit("ACE-Step task_type must be text2music|cover|repaint")
    reference_audio = str(request.get("reference_audio") or "").strip()
    if task_type != "text2music" and not reference_audio:
        raise SystemExit("ACE-Step cover/repaint requires reference_audio")

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

    output_dir = args.out_dir or args.out.parent  # type: ignore[union-attr]
    output_dir.mkdir(parents=True, exist_ok=True)
    work = output_dir / f".ace-step-{seeds[0]}"
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
        task_type=task_type,
        caption=prompt,
        lyrics="[Instrumental]",
        instrumental=True,
        duration=duration,
        bpm=int(request["bpm"]) if request.get("bpm") is not None else None,
        keyscale=str(request.get("keyscale") or ""),
        timesignature=str(request.get("timesignature") or ""),
        src_audio=reference_audio or None,
        audio_cover_strength=float(request.get("cover_strength") or 0.7),
        repainting_start=float(request.get("repainting_start") or 0.0),
        repainting_end=float(request.get("repainting_end") or -1.0),
        inference_steps=8,
        shift=3.0,
        thinking=False,
        seed=seeds[0],
    )
    config = GenerationConfig(
        batch_size=batch_size, use_random_seed=False, seeds=seeds, audio_format="wav"
    )
    result = generate_music(dit, lm, params, config, save_dir=str(work))
    if not result.success or not result.audios:
        raise RuntimeError(f"ACE-Step generation failed: {result.error or 'no audio returned'}")
    if len(result.audios) != batch_size:
        raise RuntimeError("ACE-Step generation returned an incomplete batch")
    for index, audio in enumerate(result.audios):
        source = Path(str(audio.get("path") or ""))
        if not source.is_file():
            raise RuntimeError("ACE-Step generation did not write audio")
        target = args.out if args.out is not None else output_dir / f"{index:02d}.wav"
        shutil.copyfile(source, target)


if __name__ == "__main__":
    main()
