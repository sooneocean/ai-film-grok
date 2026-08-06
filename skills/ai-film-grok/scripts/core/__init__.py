"""Shared film runtime — IO, emit, gates, media helpers.

Extracted from aifilm_grok so cli_* modules do not lazy-import the hub for
basic film I/O (breaks the cli ↔ hub cycle for W1 module refactor).

Hard-compat: aifilm_grok re-exports these symbols.
"""

from __future__ import annotations

from core.constants import (
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    DIRECTOR_NOTES_NAME,
    EXPORT_METADATA_FILES,
    GATE_ORDER,
    MANIFEST_NAME,
    NATIVE_AUDIO_AUDIBLE_MIN_DB,
    SCHEMA_VERSION,
)
from core.emit import emit
from core.film_io import (
    director_notes_path,
    empty_manifest,
    ensure_tree,
    film_dirs,
    load_director_notes,
    load_manifest,
    save_director_notes,
    save_manifest,
)
from core.gates import recompute_gates
from core.media_ops import (
    _auto_promote_last_to_next,
    _register_media,
    media_duration,
    normalize_clip,
    parse_max_volume_db,
    parse_mean_volume_db,
    parse_volume_stats,
    probe_native_audio_mean_volume,
    probe_volume_stats,
)
from core.paths import film_output_path, record_file_matches, valid_shot_id, which_npx_safe

__all__ = [
    "DEFAULT_FPS",
    "DEFAULT_HEIGHT",
    "DEFAULT_WIDTH",
    "DIRECTOR_NOTES_NAME",
    "EXPORT_METADATA_FILES",
    "GATE_ORDER",
    "MANIFEST_NAME",
    "NATIVE_AUDIO_AUDIBLE_MIN_DB",
    "SCHEMA_VERSION",
    "_auto_promote_last_to_next",
    "_register_media",
    "director_notes_path",
    "emit",
    "empty_manifest",
    "ensure_tree",
    "film_dirs",
    "film_output_path",
    "load_director_notes",
    "load_manifest",
    "media_duration",
    "normalize_clip",
    "parse_max_volume_db",
    "parse_mean_volume_db",
    "parse_volume_stats",
    "probe_native_audio_mean_volume",
    "probe_volume_stats",
    "recompute_gates",
    "record_file_matches",
    "save_director_notes",
    "save_manifest",
    "valid_shot_id",
    "which_npx_safe",
]
