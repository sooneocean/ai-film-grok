"""Post-plate filter / plate-caption mode helpers (peeled from render_final · W4 residual)."""

from __future__ import annotations

import argparse

from final.errors import RenderError


def build_post_enhancement_vf_chain(
    enable_denoise: bool = True,
    enable_sharpen: bool = True,
    denoise_strength: str = "2.0:1.5:3.0:2.5",
    sharpen_strength: float = 0.35,
) -> str:
    """Build FFmpeg video filter chain for 3D temporal denoising and CAS sharpening."""
    filters = []
    if enable_denoise:
        filters.append(f"hqdn3d={denoise_strength}")
    if enable_sharpen:
        filters.append(f"cas=strength={sharpen_strength:.2f}")
    return ",".join(filters)


def resolve_subtitle_mode(args: argparse.Namespace) -> str:
    """Return the explicit plate-caption mode; visible captions belong to HyperFrames by default."""
    subs_mode = str(getattr(args, "subs", "off") or "off").strip().lower()
    if subs_mode not in {"burn", "off"}:
        raise RenderError("--subs must be burn|off")
    return subs_mode
