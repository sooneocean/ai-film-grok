#!/usr/bin/env python3
"""Normalize one local VibeVoice-ASR transcription for the QA sidecar.

Run this script from a Python environment where the official microsoft/VibeVoice
checkout and its ASR dependencies are installed. It performs no network calls;
the model path must already exist locally.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _required_file(value: str, *, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    return path


def _segments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("VibeVoice-ASR returned no structured segments")
    output: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        try:
            start = float(item.get("start_time"))
            end = float(item.get("end_time"))
        except (TypeError, ValueError):
            continue
        if text and start >= 0 and end >= start:
            output.append(
                {
                    "speaker": str(item.get("speaker_id") or "unknown"),
                    "start": start,
                    "end": end,
                    "text": text,
                }
            )
    if not output:
        raise ValueError("VibeVoice-ASR returned no usable structured segments")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run local VibeVoice-ASR and write normalized JSON"
    )
    parser.add_argument("--audio", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--model-path", required=True, help="Already-downloaded local model directory"
    )
    parser.add_argument("--device", default="cuda", choices=("cuda", "cpu", "mps", "xpu", "auto"))
    parser.add_argument("--max-new-tokens", type=int, default=32768)
    args = parser.parse_args()

    audio = _required_file(args.audio, label="audio")
    model_path = Path(args.model_path).expanduser().resolve()
    if model_path.is_symlink() or not model_path.is_dir():
        raise ValueError("model path must be an already-downloaded non-symlink directory")
    out = Path(args.out).expanduser()
    if out.is_symlink() or out.suffix.lower() != ".json":
        raise ValueError("out must be a non-symlink JSON path")

    # The host may globally enable hf_transfer without installing it. This
    # adapter only needs the upstream tokenizer files, so use Hub's safe HTTP path.
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
    import torch
    from vibevoice.modular.modeling_vibevoice_asr import VibeVoiceASRForConditionalGeneration
    from vibevoice.processor.vibevoice_asr_processor import VibeVoiceASRProcessor

    dtype = torch.bfloat16 if args.device == "cuda" else torch.float32
    processor = VibeVoiceASRProcessor.from_pretrained(
        str(model_path), language_model_pretrained_name="Qwen/Qwen2.5-7B"
    )
    model = VibeVoiceASRForConditionalGeneration.from_pretrained(
        str(model_path),
        dtype=dtype,
        device_map=args.device if args.device == "auto" else None,
        attn_implementation="sdpa",
        trust_remote_code=True,
    )
    if args.device != "auto":
        model = model.to(args.device)
    model.eval()
    device = next(model.parameters()).device
    inputs = processor(
        audio=[str(audio)], sampling_rate=None, return_tensors="pt", add_generation_prompt=True
    )
    inputs = {
        key: value.to(device) if isinstance(value, torch.Tensor) else value
        for key, value in inputs.items()
    }
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=args.max_new_tokens,
            pad_token_id=processor.pad_id,
            eos_token_id=processor.tokenizer.eos_token_id,
            do_sample=False,
        )
    generated = output_ids[0, inputs["input_ids"].shape[1] :]
    text = processor.decode(generated, skip_special_tokens=True)
    segments = _segments(processor.post_process_transcription(text))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"segments": segments}, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
