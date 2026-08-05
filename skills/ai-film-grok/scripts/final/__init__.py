"""Final delivery leaf helpers (W4 peel from render_final).

Import preferred: ``from final.caption_text import write_srt``.
``render_final`` re-exports the public surface for hard-compat.
"""

from __future__ import annotations

from final.caption_text import (
    build_subtitle_cues_for_shots,
    caption_text_for_shot,
    flatten_shots,
    is_character_speech_shot,
    narration_for_shot,
    split_units,
    spoken_text_for_shot,
    unit_timings,
    validate_linear_narration,
    write_srt,
)
from final.errors import RenderError
from final.media_ops import (
    apply_dialogue_broll_visual,
    concat_audio_segments,
    concat_videos,
    pdur,
    stable_path_for_ffmpeg_filter,
    stretch_clip,
)
from final.voice import (
    tts_backend_for_shot,
    validate_voice_language_locks,
    voice_for_shot,
)

__all__ = [
    "RenderError",
    "apply_dialogue_broll_visual",
    "build_subtitle_cues_for_shots",
    "caption_text_for_shot",
    "concat_audio_segments",
    "concat_videos",
    "flatten_shots",
    "is_character_speech_shot",
    "narration_for_shot",
    "pdur",
    "split_units",
    "spoken_text_for_shot",
    "stable_path_for_ffmpeg_filter",
    "stretch_clip",
    "tts_backend_for_shot",
    "unit_timings",
    "validate_linear_narration",
    "validate_voice_language_locks",
    "voice_for_shot",
    "write_srt",
]
