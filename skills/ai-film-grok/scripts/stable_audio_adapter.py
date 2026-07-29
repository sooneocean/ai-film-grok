#!/usr/bin/env python3
"""Pinned local Stable Audio Open renderer for private candidate ambience."""

from __future__ import annotations

import argparse
import gc
import hashlib
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pinned_local_model(args: argparse.Namespace) -> Path:
    model_root_input = Path(args.model_root).expanduser()
    checkpoint_input = Path(args.checkpoint).expanduser()
    adapter = Path(__file__)
    if model_root_input.is_symlink() or checkpoint_input.is_symlink() or adapter.is_symlink():
        raise SystemExit("model, checkpoint, and adapter paths must not be symlinks")
    model_root = model_root_input.resolve(strict=True)
    checkpoint = checkpoint_input.resolve(strict=True)
    if not model_root.is_dir() or not checkpoint.is_file():
        raise SystemExit("local model root and checkpoint are required")
    try:
        checkpoint.relative_to(model_root)
    except ValueError as exc:
        raise SystemExit("checkpoint must be inside model root") from exc
    if _sha256(checkpoint) != args.expected_checkpoint_sha256.lower():
        raise SystemExit("checkpoint SHA-256 mismatch")
    if _sha256(adapter) != args.expected_adapter_sha256.lower():
        raise SystemExit("adapter SHA-256 mismatch")
    return model_root


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--expected-checkpoint-sha256", required=True)
    parser.add_argument("--expected-adapter-sha256", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--steps", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.duration <= 47:
        raise SystemExit("duration must be 1-47 seconds")
    model_root = _pinned_local_model(args)
    import torch
    import torchaudio
    from einops import rearrange
    from stable_audio_tools import get_pretrained_model
    from stable_audio_tools.inference.generation import generate_diffusion_cond

    model, config = get_pretrained_model(str(model_root))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device).eval().requires_grad_(False)
    sample_rate = int(config["sample_rate"])
    sample_size = int(config["sample_size"])
    conditioning = [{"prompt": args.prompt, "seconds_start": 0, "seconds_total": args.duration}]
    audio = generate_diffusion_cond(
        model=model,
        conditioning=conditioning,
        negative_conditioning=None,
        steps=args.steps,
        cfg_scale=6.0,
        batch_size=1,
        sample_size=sample_size,
        seed=args.seed,
        device=device,
        sampler_type="dpmpp-3m-sde",
        sigma_min=0.03,
        sigma_max=1000.0,
    )
    audio = audio[:, :, : round(args.duration * sample_rate)]
    audio = rearrange(audio, "b d n -> d (b n)").to(torch.float32).clamp(-1, 1).cpu()
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(destination), audio, sample_rate, encoding="PCM_S", bits_per_sample=16)
    del model, audio
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
