#!/usr/bin/env python3
"""Film-spec public facade (W7) — constants + profile + validate re-exports.

Internal peels: film_spec_profile · film_spec_sex_floor · film_spec_constants · film_spec_validate.
"""

from __future__ import annotations

# Profile / I2V resolve (R3a) — lives at scripts root historically
from film_spec_profile import (  # noqa: F401
    DEFAULT_H3_CONFIG,
    FRW_I2V_FRW_ONLY_LIFEBOAT,
    H3_AUDIO_POLICIES,
    I2V_PROFILES,
    I2V_PROVIDERS,
    default_frw_video_model,
    default_i2v_provider,
    frw_i2v_fallback_chain,
    resolve_h3_config,
    resolve_i2v_profile,
)

# Constants leaf (M1)
try:
    from plan.film_spec_constants import *  # noqa: F403
except ImportError:  # pragma: no cover
    from film_spec_constants import *  # type: ignore  # noqa: F403

# Validate leaf (M1)
try:
    from plan.film_spec_validate import (  # noqa: F401
        DIRECTOR_BOARD_FIELDS,  # noqa: F401
        PERFORMANCE_FIELDS,  # noqa: F401
        FilmSpecError,
        _is_unauthored,
        _required_text,
        _validate_dialogue_drama_shot,
        estimate_nar_vo_sec,
        iter_film_spec_shots,
        lint_director_board,
        lint_performance,
        validate_director_intent,
        validate_dramatic_function,
        validate_film_spec,
        validate_nar_budget,
        zero_narration_gate,
    )
except ImportError:  # pragma: no cover
    from film_spec_validate import (  # type: ignore  # noqa: F401
        DIRECTOR_BOARD_FIELDS,  # noqa: F401
        PERFORMANCE_FIELDS,  # noqa: F401
        FilmSpecError,
        _is_unauthored,
        _required_text,
        _validate_dialogue_drama_shot,
        estimate_nar_vo_sec,
        iter_film_spec_shots,
        lint_director_board,
        lint_performance,
        validate_director_intent,
        validate_dramatic_function,
        validate_film_spec,
        validate_nar_budget,
        zero_narration_gate,
    )

# Sex floor already peeled
try:
    from plan.film_spec_sex_floor import (  # noqa: F401
        SexFloorError,
        apply_sex_duration_floor,
        resolve_sex_floor_strict,
    )
except ImportError:  # pragma: no cover
    from film_spec_sex_floor import (  # type: ignore  # noqa: F401
        SexFloorError,
        apply_sex_duration_floor,
        resolve_sex_floor_strict,
    )

__all__ = [
    "FilmSpecError",
    "SexFloorError",
    "apply_sex_duration_floor",
    "resolve_sex_floor_strict",
    "validate_film_spec",
    "validate_director_intent",
    "iter_film_spec_shots",
    "estimate_nar_vo_sec",
    "validate_nar_budget",
    "zero_narration_gate",
    "lint_performance",
    "lint_director_board",
    "validate_dramatic_function",
    "DEFAULT_DURATION_SEC",
    "DEFAULT_I2V_PROVIDER",
    "VO_MODES",
    "resolve_i2v_profile",
    "default_i2v_provider",
    "resolve_h3_config",
]
