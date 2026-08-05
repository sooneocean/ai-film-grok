"""Film control-plane constants (shared by hub + cli clusters)."""

from __future__ import annotations

SCHEMA_VERSION = 2
MANIFEST_NAME = "manifest.json"
DIRECTOR_NOTES_NAME = "director_notes.json"
DEFAULT_FPS = 30
DEFAULT_WIDTH = 720
DEFAULT_HEIGHT = 1280  # 9:16; overridden by aspect
NATIVE_AUDIO_AUDIBLE_MIN_DB = -42.0
GATE_ORDER = (
    "brief",
    "style_locked",
    "spec",
    "canonical",
    "stills_complete",
    "clips_complete",
    "assembled",
    "final_complete",
    "desktop_exported",
)
EXPORT_METADATA_FILES = (
    "brief.json",
    "style-bible.json",
    "film-spec.json",
    "timeline.json",
    "manifest.json",
    "README.md",
    "post-plan.json",
)
