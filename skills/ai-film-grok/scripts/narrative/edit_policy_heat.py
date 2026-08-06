#!/usr/bin/env python3
"""Heat arc / wardrobe / sex / VO spice policies.

Extracted from edit_policy.py (C4 · 2026-08-04) so the core stretch/transition
surface stays smaller. Public symbols re-exported by edit_policy for back-compat.
"""

from __future__ import annotations

# Cycle-free leaf — do not import edit_policy at module load (edit_policy re-exports us).
from edit_policy_shared import PolicyError  # noqa: F401
from heat_arc_lint import (  # noqa: F401
    _merge_sub_issues,
    _shot_duration_sec,
    lint_heat_arc,
)
from heat_coitus import (  # noqa: F401
    _SEX_ARC_FOREPLAY_MARKERS,
    _SEX_ARC_PENETRATION_MARKERS,
    _SEX_ARC_RELEASE_MARKERS,
    COITUS_BEAT_DEFAULT_POSE,
    COITUS_BEATS,
    COITUS_REQUIRED_BEATS,
    SEX_ARC_BEATS,
    SEX_ARC_REQUIRED,
    SEX_POSES,
    _shot_has_penetration_verb,
    _shot_has_release_marker,
    _shot_visual_pose_blob,
    lint_coitus_grammar,
    lint_sex_arc,
    lint_sex_pose_variety,
    resolve_coitus_beat,
    resolve_sex_arc_beat,
    resolve_sex_pose,
    shot_coitus_pseudo_only,
    shot_coitus_readable,
)
from heat_impact import (  # noqa: F401
    _ECCHI_COMPLETE,
    _ECCHI_DISTANCE,
    _ECCHI_DOUBLE,
    _ECCHI_POWER,
    _ECCHI_SENSORY,
    _ECCHI_WARDROBE,
    ECCHI_CHECKLIST_ITEMS,
    _is_detail_cu_shot,
    _shot_size_rank,
    apply_impact_boost_patches,
    compute_erotic_impact_score,
    lint_ecchi_checklist,
    lint_montage_craft,
    lint_sex_detail_cu,
    lint_size_ladder,
    lint_vo_motion_align,
    suggest_impact_boost_actions,
)
from heat_multi import (  # noqa: F401
    _MALE_CAST_IDS,
    _MULTI_HEROINE_PROMPT_MARKERS,
    lint_multi_heroine,
    resolve_heroine_cast_mode,
)

# --- Heat arc / multi-heroine (adult max iron · 2026-07-24) ---
# Adult max IRON: meat-ratio high, heat max, undress/expose when possible.
# Sex duration + intimacy + setup + bare peak are hard on heat_scale=max
# (write-spec via sex_floor_strict / sex_wardrobe_strict / heat_arc_strict).
# M4: phase/scale constants + helpers live in heat_phase (re-export hard-compat)
from heat_phase import (  # noqa: F401
    _DRAMATIC_TO_HEAT_PHASE,
    ADVISORY_MAX_INTIMACY_RATIO,
    ADVISORY_MAX_SETUP_RATIO,
    ADVISORY_MAX_SEX_DURATION_RATIO,
    DEFAULT_BARE_PEAK_REQUIRED,
    DEFAULT_SEX_DURATION_FLOOR,
    DEFAULT_SHOT_DURATION_SEC,
    EXTREME_INTIMACY_FLOOR,
    EXTREME_SETUP_CEILING,
    HARDCORE_SEX_DURATION_TARGET,
    HEAT_PHASE_ESCALATION_RANK,
    HEAT_PHASES,
    HEAT_SCALES,
    HOT_SEX_DURATION_FLOOR,
    INTIMACY_PHASES,
    MAX_PRE_CLIMAX_PLATEAU_SHOTS,
    SEX_PHASES,
    apply_heat_phase_defaults,
    heat_phase_escalation_rank,
    infer_heat_phase,
    lint_heat_escalation_challenge,
    normalize_heat_phase,
    normalize_heat_scale,
)
from heat_spice import (  # noqa: F401
    _NAR_EXTREME_MARKERS,
    _NAR_LITERARY_ONLY_HINTS,
    _NAR_MILD_ONLY_MARKERS,
    _NAR_SEX_VERB_MARKERS,
    _NAR_SPICE_MARKERS,
    _TEMPLATE_NAR_POLLUTION_MARKERS,
    HARDCORE_CRAFT_SPINE,
    SPICE_LEVELS,
    apply_vo_spice_auto,
    is_template_nar_pollution,
    lint_sex_vo_spice,
    lint_user_source_fidelity,
    nar_has_extreme_spice,
    nar_has_sex_verb,
    nar_has_spice,
    normalize_spice_level,
    suggest_vo_lines,
)
from heat_wardrobe import (  # noqa: F401
    _EXPOSED_WARDROBE_MARKERS,
    _FULL_DRESS_MARKERS,
    _UNDRESS_ACTION_MARKERS,
    _WARDROBE_START_POSE_HINT,
    _WARDROBE_SUBJECT_MUST_INCLUDE,
    PHASE_WARDROBE_FLOOR,
    SEX_WARDROBE_OK,
    SEX_WARDROBE_STRONG,
    WARDROBE_STATES,
    WARDROBE_UNDRESS_RANK,
    _ensure_start_pose_wardrobe,
    _shot_visual_blob,
    _write_shot_wardrobe_state,
    apply_wardrobe_continuity,
    lint_both_undress,
    lint_sex_wardrobe,
    normalize_wardrobe_state,
    resolve_partner_wardrobe_state,
    resolve_wardrobe_state,
    shot_has_undress_action,
    wardrobe_undress_rank,
)
