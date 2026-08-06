#!/usr/bin/env python3
"""Acoustic policies for spatial audio and environmental reverb mapping."""


def resolve_acoustic_space(location_tags: list[str]) -> dict:
    """Map semantic location tags to DSP parameters (reverb tail, wetness, EQ)."""
    if not location_tags:
        location_tags = []
    tags = " ".join(t.lower() for t in location_tags)

    if "bathroom" in tags or "hallway" in tags or "cave" in tags or "shower" in tags:
        return {"reverb_time": 2.5, "wet_level": 0.4, "lowpass": 6000, "highpass": 150}
    elif "outdoor" in tags or "street" in tags or "forest" in tags or "balcony" in tags:
        return {"reverb_time": 0.5, "wet_level": 0.1, "lowpass": 8000, "highpass": 300}
    elif "bedroom" in tags or "intimate" in tags or "office" in tags or "bed" in tags:
        return {"reverb_time": 0.8, "wet_level": 0.15, "lowpass": 4000, "highpass": 80}

    # Default (classroom, generic indoor)
    return {"reverb_time": 1.2, "wet_level": 0.2, "lowpass": 5000, "highpass": 100}


def resolve_spatial_pan(framing: str) -> float:
    """Map visual framing tags to a stereo pan value [-1.0, 1.0]."""
    if not framing:
        return 0.0
    f = framing.lower()
    if "left" in f:
        if "extreme" in f or "far" in f:
            return -0.85
        return -0.45
    elif "right" in f:
        if "extreme" in f or "far" in f:
            return 0.85
        return 0.45
    return 0.0
