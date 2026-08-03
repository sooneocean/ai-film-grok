"""story.normalize public API — re-exports from story_plan.

This module provides a clean, dedicated entry point for the
story normalization pipeline. All heavy logic lives in story_plan.py;
this module re-exports the public functions for consumers that only
need normalization (not the full planning pipeline).
"""

from __future__ import annotations

# Re-export the core normalization function
from story_plan import (
    _character_candidates as _character_candidates,
)
from story_plan import (
    _clip_nar as _clip_nar,
)
from story_plan import (
    _dialogue_blocks as _dialogue_blocks,
)
from story_plan import (
    _draft_story_contract as _draft_story_contract,
)
from story_plan import (
    _episode_chunks as _episode_chunks,
)
from story_plan import (
    _extract_plot_point_candidates as _extract_plot_point_candidates,
)
from story_plan import (
    _location_candidates as _location_candidates,
)
from story_plan import (
    _scene_chunks as _scene_chunks,
)
from story_plan import (
    _sentences as _sentences,
)
from story_plan import (
    detect_genre as detect_genre,
)
from story_plan import (
    detect_heat_signals as detect_heat_signals,
)
from story_plan import (
    normalize_story as normalize_story,
)
from story_plan import (
    select_beat_spine as select_beat_spine,
)

__all__ = [
    "normalize_story",
    "detect_genre",
    "detect_heat_signals",
    "select_beat_spine",
    "_draft_story_contract",
    "_extract_plot_point_candidates",
    "_character_candidates",
    "_location_candidates",
    "_dialogue_blocks",
    "_scene_chunks",
    "_episode_chunks",
    "_sentences",
    "_clip_nar",
]
