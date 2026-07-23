#!/usr/bin/env python3
"""Minimal sound spotting plan: validate + expand to applied mix events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SPOT_EVENT_TYPES = frozenset(
    {"mute", "sfx_accent", "duck", "music_in", "music_out", "fade_in", "fade_out"}
)
SFX_KINDS = frozenset({"heartbeat", "whoosh", "chime", "impact", "breath", "generic"})
# Canonical BGM moods (render_final / make_sfx_bed)
SOUND_MOODS = frozenset({"playful", "dark", "warm", "rnb", "sensual"})
# Aliases → canonical (Kei 2026-07-16: user wants R&B/Soul seductive, not horror dark)
SOUND_MOOD_ALIASES = {
    "r&b": "rnb",
    "rnb": "rnb",
    "soul": "rnb",
    "neo-soul": "rnb",
    "neosoul": "rnb",
    "seductive": "rnb",
    "sexy": "rnb",
    "ecchi": "rnb",
    "sensual": "sensual",  # same bed family as rnb in render_final
    "late-night": "rnb",
    "latenight": "rnb",
    "horror": "dark",
    "thriller": "dark",
    "scary": "dark",
}
# tone / title keywords that imply 色气 → never leave mood on dark
ECCHI_TONE_HINTS = (
    "色气",
    "里番",
    "同人",
    "诱惑",
    "后宫",
    "情欲",
    "擦边",
    "ecchi",
    "sensual",
    "seductive",
    "harem",
    "r18",
    "r-18",
)

# Horror/thriller tone keywords — detected BEFORE ecchi so a horror storyteller
# film gets "dark" not "rnb". Found by genre migration test (2026-07-22):
# default_sound_plan_for_film gave horror films rnb because vo_mode=storyteller
# overrode the tone signal.
HORROR_TONE_HINTS = (
    "恐怖",
    "惊悚",
    "horror",
    "thriller",
    "scary",
    "creepy",
    "诡异",
    "悬疑",  # suspense-thriller adjacent
    "suspense",
)


class SoundPlanError(ValueError):
    pass


def validate_audio_tracks_contract(
    spec: dict[str, Any],
    *,
    audio_dir: Path | None = None,
    require_artifacts: bool = False,
) -> dict[str, Any]:
    """Validate the optional dual-track contract without breaking old specs."""
    strict = bool(spec.get("audio_tracks_strict"))
    sound_plan = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
    tracks = spec.get("audio_tracks")
    if tracks is None:
        tracks = sound_plan.get("audio_tracks")
    warnings: list[str] = []
    errors: list[str] = []
    if tracks is None:
        warnings.append("audio_tracks missing; using renderer defaults")
        tracks = {}
    elif not isinstance(tracks, dict):
        errors.append("audio_tracks must be an object")
        tracks = {}

    music = tracks.get("music") or tracks.get("bgm")
    if strict:
        for name in ("dialogue", "sfx"):
            if not isinstance(tracks.get(name), dict):
                errors.append(f"audio_tracks.{name} is required")
        if not isinstance(music, dict):
            errors.append("audio_tracks.music or audio_tracks.bgm is required")
        for name, item in (("sfx", tracks.get("sfx")), ("music", music)):
            if (
                isinstance(item, dict)
                and not str(item.get("source") or item.get("license") or "").strip()
            ):
                errors.append(f"audio_tracks.{name}.source or license is required")
    elif not isinstance(music, dict):
        warnings.append("audio_tracks.music missing; renderer will generate procedural BGM")

    result: dict[str, Any] = {"strict": strict, "tracks": tracks, "warnings": warnings}
    if require_artifacts and audio_dir is not None:
        expected = {
            name: audio_dir / filename
            for name, filename in (
                ("bgm", "bgm_stereo.wav"),
                ("sfx", "sfx_stereo.wav"),
                ("mixed", "mixed.wav"),
                ("mix_report", "mix_report.json"),
            )
        }
        missing = [name for name, path in expected.items() if not path.is_file()]
        if missing:
            errors.append("audio artifacts missing: " + ", ".join(missing))
        report = expected["mix_report"]
        if report.is_file():
            try:
                report_obj = json.loads(report.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                errors.append(f"mix_report.json unreadable: {exc}")
            else:
                artifacts = report_obj.get("artifacts") if isinstance(report_obj, dict) else None
                if not isinstance(artifacts, dict):
                    errors.append("mix_report.artifacts is required")
                else:
                    for name in ("bgm", "sfx", "mixed"):
                        item = artifacts.get(name)
                        if not isinstance(item, dict) or not item.get("sha256"):
                            errors.append(f"mix_report.artifacts.{name}.sha256 is required")
        result["artifacts"] = {name: str(path) for name, path in expected.items()}
    if errors and strict:
        raise SoundPlanError("audio_tracks_strict: " + "; ".join(errors))
    if errors:
        warnings.extend(errors)
    result["errors"] = errors
    return result


# VO sidechain-compress defaults (FFmpeg sidechaincompress on BGM bed)
# rnb: slightly longer release so groove returns in narration pauses (色气「呼吸感」)
SIDECHAIN_DEFAULT: dict[str, float] = {
    "threshold": 0.05,
    "ratio": 4.0,
    "attack_ms": 20.0,
    "release_ms": 550.0,
}
SIDECHAIN_RNB: dict[str, float] = {
    "threshold": 0.045,
    "ratio": 4.5,
    "attack_ms": 15.0,
    "release_ms": 880.0,
}


def resolve_sidechain(
    plan: dict[str, Any] | None = None,
    *,
    mood: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Resolve sidechain duck params for VO→BGM.

    Priority: explicit overrides (CLI) > sound_plan.sidechain > mood preset (rnb/sensual)
    > SIDECHAIN_DEFAULT.
    """
    mood_l = str(mood or (plan or {}).get("mood") or "rnb").lower()
    if mood_l in {"rnb", "r&b", "soul", "sensual", "seductive", "ecchi", "sexy"}:
        base = dict(SIDECHAIN_RNB)
    else:
        base = dict(SIDECHAIN_DEFAULT)

    sc = (plan or {}).get("sidechain") if isinstance(plan, dict) else None
    if isinstance(sc, dict):
        for key, alt in (
            ("threshold", "threshold"),
            ("ratio", "ratio"),
            ("attack_ms", "attack"),
            ("release_ms", "release"),
        ):
            # accept attack/release without _ms
            val = sc.get(key)
            if val is None and key.endswith("_ms"):
                val = sc.get(alt)
            if val is not None:
                try:
                    base[key] = float(val)
                except (TypeError, ValueError) as exc:
                    raise SoundPlanError(f"sound_plan.sidechain.{key} invalid: {val!r}") from exc

    if overrides:
        for key in ("threshold", "ratio", "attack_ms", "release_ms"):
            if overrides.get(key) is not None:
                try:
                    base[key] = float(overrides[key])
                except (TypeError, ValueError) as exc:
                    raise SoundPlanError(
                        f"sidechain override {key} invalid: {overrides[key]!r}"
                    ) from exc

    # clamp sane ranges
    base["threshold"] = max(0.001, min(1.0, base["threshold"]))
    base["ratio"] = max(1.0, min(20.0, base["ratio"]))
    base["attack_ms"] = max(1.0, min(500.0, base["attack_ms"]))
    base["release_ms"] = max(20.0, min(3000.0, base["release_ms"]))
    return base


def sidechain_filter_fragment(sc: dict[str, float]) -> str:
    """FFmpeg sidechaincompress options string (no surrounding brackets)."""
    return (
        f"sidechaincompress=threshold={sc['threshold']:.4f}:"
        f"ratio={sc['ratio']:.3f}:"
        f"attack={sc['attack_ms']:.1f}:"
        f"release={sc['release_ms']:.1f}:level_sc=1"
    )


# Shortform loudness (Phase G): target ~-16 LUFS; auto-correct only when out of band
DEFAULT_TARGET_LUFS = -16.0
LOUDNORM_LOUD_CEILING = -12.0  # louder than this → pull down
LOUDNORM_QUIET_FLOOR = -22.0  # quieter than this → lift
LOUDNORM_MODES = frozenset({"off", "auto", "on"})


def resolve_loudnorm(
    plan: dict[str, Any] | None = None,
    *,
    mode: str | None = None,
    target_lufs: float | None = None,
) -> dict[str, Any]:
    """Resolve loudnorm policy for mixed.wav.

    - off: never rewrite mix
    - auto (default): apply only when integrated LUFS outside [-22, -12]
    - on: always normalize toward target_lufs
    """
    plan = plan if isinstance(plan, dict) else {}
    raw_mode = mode if mode is not None else plan.get("loudnorm", "auto")
    if isinstance(raw_mode, bool):
        raw_mode = "on" if raw_mode else "off"
    mode_s = str(raw_mode or "auto").strip().lower()
    if mode_s in {"true", "force", "always", "yes", "1"}:
        mode_s = "on"
    if mode_s in {"false", "no", "0", "never"}:
        mode_s = "off"
    if mode_s not in LOUDNORM_MODES:
        raise SoundPlanError(f"loudnorm mode must be off|auto|on; got {raw_mode!r}")
    tgt = target_lufs
    if tgt is None and plan.get("target_lufs") is not None:
        try:
            tgt = float(plan["target_lufs"])
        except (TypeError, ValueError) as exc:
            raise SoundPlanError(f"target_lufs invalid: {plan.get('target_lufs')!r}") from exc
    if tgt is None:
        tgt = DEFAULT_TARGET_LUFS
    tgt = float(tgt)
    # sane shortform range
    tgt = max(-24.0, min(-10.0, tgt))
    return {
        "mode": mode_s,
        "target_lufs": tgt,
        "loud_ceiling": LOUDNORM_LOUD_CEILING,
        "quiet_floor": LOUDNORM_QUIET_FLOOR,
    }


def should_apply_loudnorm(
    policy: dict[str, Any],
    measured_lufs: float | None,
) -> tuple[bool, str]:
    """Return (apply?, reason)."""
    mode = str(policy.get("mode") or "auto")
    if mode == "off":
        return False, "loudnorm=off"
    if mode == "on":
        return True, "loudnorm=on (force)"
    # auto
    if measured_lufs is None:
        return False, "auto: no measurement"
    lo = float(policy.get("quiet_floor", LOUDNORM_QUIET_FLOOR))
    hi = float(policy.get("loud_ceiling", LOUDNORM_LOUD_CEILING))
    if measured_lufs > hi:
        return True, f"auto: too loud ({measured_lufs:.1f} > {hi:.1f} LUFS)"
    if measured_lufs < lo:
        return True, f"auto: too quiet ({measured_lufs:.1f} < {lo:.1f} LUFS)"
    return False, f"auto: in band ({measured_lufs:.1f} LUFS)"


# Phase H: local licensed BGM templates (user places files; skill never ships copyrighted packs)
MUSIC_TEMPLATE_EXTS = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg")
MUSIC_TEMPLATE_MODES = frozenset({"off", "auto", "on"})


def _first_existing_music(candidates: list[Any]) -> Any | None:
    found = _list_existing_music(candidates)
    return found[0] if found else None


def _list_existing_music(candidates: list[Any]) -> list[Any]:
    """Unique existing music files in candidate order (size > 100 B)."""
    from pathlib import Path

    out: list[Any] = []
    seen: set[str] = set()
    for c in candidates:
        p = Path(c)
        try:
            key = str(p.resolve()) if p.is_file() else ""
        except OSError:
            continue
        if not key or key in seen:
            continue
        try:
            if p.stat().st_size > 100:
                seen.add(key)
                out.append(p)
        except OSError:
            continue
    return out


def _pick_music_from_pool(pool: list[Any], *, seed: int | None = None) -> Any | None:
    """Anti-fatigue: rotate among multiple beds instead of always the first file."""
    if not pool:
        return None
    if len(pool) == 1 or seed is None:
        return pool[0]
    idx = int(seed) % len(pool)
    return pool[idx]


def _license_sidecar_for(music_path: Any) -> str | None:
    """Read audio/foo.license.txt or foo.wav.license.txt if present."""
    from pathlib import Path

    p = Path(music_path)
    for side in (
        p.with_suffix(p.suffix + ".license.txt"),
        p.with_suffix(".license.txt"),
        p.parent / f"{p.stem}.license.txt",
        p.parent / "LICENSE.txt",
        p.parent / "license.txt",
    ):
        if side.is_file():
            try:
                text = side.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    return text[:500]
            except OSError:
                continue
    return None


def resolve_music_template(
    root: Any,
    *,
    mood: str = "rnb",
    plan: dict[str, Any] | None = None,
    music_arg: str | None = None,
    mode: str | None = None,
    music_license: str | None = None,
    seed: int | None = None,
) -> dict[str, Any] | None:
    """Resolve optional local BGM file for final.

    Returns None → use procedural bed.
    Returns {path, license_note, source, mood, mode, pool_size?, pool_index?}.

    Search order (auto/on, when --music not set):
      1. sound_plan.music_file (relative to film root)
      2. audio/bgm.* / audio/music.*
      3. audio/templates/{mood}.*  + audio/templates/{mood}/*.*  (pool)
      4. audio/templates/default.*
      5. skill library assets/bgm/{mood}/bed.* + assets/bgm/{mood}/*.*  (pool)

    When multiple files match (pool), pick by ``seed % len(pool)`` so films
    don't always get the same bed.wav.
    """
    from pathlib import Path

    root = Path(root).expanduser().resolve()
    plan = plan if isinstance(plan, dict) else {}
    mood_l = normalize_sound_mood(mood or plan.get("mood") or "rnb")

    raw_mode = mode if mode is not None else plan.get("music_template", "auto")
    if isinstance(raw_mode, bool):
        raw_mode = "on" if raw_mode else "off"
    mode_s = str(raw_mode or "auto").strip().lower()
    if mode_s in {"true", "yes", "force", "1"}:
        mode_s = "on"
    if mode_s in {"false", "no", "0", "never"}:
        mode_s = "off"
    if mode_s not in MUSIC_TEMPLATE_MODES:
        raise SoundPlanError(f"music_template mode must be off|auto|on; got {raw_mode!r}")

    # Explicit --music always wins
    if music_arg:
        p = Path(music_arg).expanduser()
        if not p.is_file():
            # try relative to film root
            alt = root / music_arg
            p = alt if alt.is_file() else p
        if not p.is_file():
            raise SoundPlanError(f"--music file not found: {music_arg}")
        lic = (
            (music_license or "").strip()
            or _license_sidecar_for(p)
            or ("user-supplied file (set --music-license for commercial claims)")
        )
        return {
            "path": str(p.resolve()),
            "license_note": lic,
            "source": "cli_music",
            "mood": mood_l,
            "mode": mode_s,
        }

    if mode_s == "off":
        return None

    film_candidates: list[Path] = []
    skill_candidates: list[Path] = []
    # 1) sound_plan.music_file
    mf = plan.get("music_file") or plan.get("bgm_file")
    if isinstance(mf, str) and mf.strip():
        rel = mf.strip()
        film_candidates.append(root / rel)
        film_candidates.append(Path(rel).expanduser())

    audio = root / "audio"
    # 2) audio/bgm.* audio/music.*
    for stem in ("bgm", "music", "bed"):
        for ext in MUSIC_TEMPLATE_EXTS:
            film_candidates.append(audio / f"{stem}{ext}")
    # 3) mood-named templates + pool dirs
    mood_aliases = {
        "rnb": ("rnb", "soul", "sensual", "seductive", "ecchi"),
        "sensual": ("sensual", "rnb", "soul"),
        "warm": ("warm",),
        "playful": ("playful",),
        "dark": ("dark", "horror"),
    }
    names = mood_aliases.get(mood_l, (mood_l,))
    for name in names:
        for ext in MUSIC_TEMPLATE_EXTS:
            film_candidates.append(audio / "templates" / f"{name}{ext}")
            film_candidates.append(audio / "templates" / name / f"bed{ext}")
        # pool: audio/templates/{name}/*.*
        pool_dir = audio / "templates" / name
        if pool_dir.is_dir():
            for ext in MUSIC_TEMPLATE_EXTS:
                film_candidates.extend(sorted(pool_dir.glob(f"*{ext}")))
    # 4) default template
    for ext in MUSIC_TEMPLATE_EXTS:
        film_candidates.append(audio / "templates" / f"default{ext}")

    # 5) skill-level shared library (user-placed licensed beds) + pool
    skill_bgm = Path(__file__).resolve().parents[1] / "assets" / "bgm"
    for name in names:
        for ext in MUSIC_TEMPLATE_EXTS:
            skill_candidates.append(skill_bgm / name / f"bed{ext}")
            skill_candidates.append(skill_bgm / f"{name}{ext}")
        mood_dir = skill_bgm / name
        if mood_dir.is_dir():
            for ext in MUSIC_TEMPLATE_EXTS:
                skill_candidates.extend(sorted(mood_dir.glob(f"*{ext}")))
    for ext in MUSIC_TEMPLATE_EXTS:
        skill_candidates.append(skill_bgm / f"default{ext}")
        skill_candidates.append(skill_bgm / "default" / f"bed{ext}")

    film_pool = _list_existing_music(film_candidates)
    skill_pool = _list_existing_music(skill_candidates)
    if film_pool:
        pool = film_pool
        source = "local_template"
    elif skill_pool:
        pool = skill_pool
        source = "skill_library"
    else:
        pool = []
        source = "local_template"

    found = _pick_music_from_pool(pool, seed=seed)
    if found is None:
        if mode_s == "on":
            raise SoundPlanError(
                "music_template=on but no local BGM found. Place a file at "
                f"audio/bgm.wav or audio/templates/{mood_l}.wav under {root}, "
                f"or skill assets/bgm/{mood_l}/bed.wav (or multiple beds in that folder), "
                "or pass --music /path/to.wav --music-license '…'"
            )
        return None

    pool_index = 0
    try:
        pool_index = pool.index(found)
    except ValueError:
        pool_index = 0

    lic = (
        (music_license or "").strip()
        or _license_sidecar_for(found)
        or (
            f"{source} path={found.name}; "
            "not a commercial license grant — add *.license.txt or --music-license"
        )
    )
    rel: str | None
    try:
        rel = str(found.relative_to(root)) if found.is_relative_to(root) else str(found)
    except (ValueError, AttributeError):
        rel = str(found)
    return {
        "path": str(found.resolve()),
        "license_note": lic,
        "source": source,
        "mood": mood_l,
        "mode": mode_s,
        "relative": rel,
        "pool_size": len(pool),
        "pool_index": pool_index,
    }


def normalize_sound_mood(value: object) -> str:
    """Map free-text mood to a renderable canonical mood."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "rnb"
    raw = str(value).strip().lower().replace(" ", "").replace("_", "-")
    if raw in SOUND_MOOD_ALIASES:
        return SOUND_MOOD_ALIASES[raw]
    if raw in SOUND_MOODS:
        return raw
    # partial match
    if "soul" in raw or "r&b" in raw or "rnb" in raw:
        return "rnb"
    if "dark" in raw or "horror" in raw:
        return "dark"
    if "warm" in raw:
        return "warm"
    if "play" in raw:
        return "playful"
    raise SoundPlanError(
        f"sound_plan.mood unknown: {value!r}. Use one of {sorted(SOUND_MOODS)} "
        f"(aliases: soul/seductive/ecchi → rnb; horror → dark)"
    )


def tone_implies_ecchi(
    tone: str | None, title: str | None = None, description: str | None = None
) -> bool:
    blob = " ".join(x for x in (tone or "", title or "", description or "") if x).lower()
    return any(h.lower() in blob for h in ECCHI_TONE_HINTS)


def tone_implies_horror(
    tone: str | None, title: str | None = None, description: str | None = None
) -> bool:
    """Detect horror/thriller before ecchi — a horror storyteller film
    needs 'dark', not the storyteller-default 'rnb'.

    Found by genre migration test (2026-07-22): default_sound_plan_for_film
    gave horror films rnb because vo_mode=storyteller overrode the tone signal.
    """
    blob = " ".join(x for x in (tone or "", title or "", description or "") if x).lower()
    return any(h.lower() in blob for h in HORROR_TONE_HINTS)


def default_sound_plan_for_film(
    *,
    vo_mode: str = "storyteller",
    tone: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Default bed for new films.

    Priority: horror tone → dark (before storyteller→rnb); ecchi → rnb;
    else storyteller → rnb, character → warm. Genre migration test
    (2026-07-22) proved storyteller default must not mask horror tone.
    """
    if tone_implies_horror(tone, title, description):
        mood = "dark"
    elif tone_implies_ecchi(tone, title, description) or vo_mode in ("storyteller", "hybrid"):
        mood = "rnb"
    else:
        mood = "warm"
    return {
        "mood": mood,
        "bed": True,
        "events": [],
        "auto_sfx": True,
        "loudnorm": "auto",
        "target_lufs": DEFAULT_TARGET_LUFS,
    }


def validate_sound_plan(
    raw: object,
    *,
    tone: str | None = None,
    title: str | None = None,
    description: str | None = None,
    vo_mode: str | None = None,
) -> dict[str, Any] | None:
    """Validate optional film-spec.sound_plan. None if absent.

    Product rule (2026-07-16 Kei): 色气片默认 late-night R&B/Soul（rnb/sensual），
    禁止把 dark 恐怖铺底当默认；若 tone 偏色气却写了 dark → 自动改 rnb 并记录。
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SoundPlanError("sound_plan must be an object")
    mood_in = raw.get("mood", "rnb")
    mood = normalize_sound_mood(mood_in)
    notes: list[str] = []
    if mood == "dark" and tone_implies_ecchi(tone, title, description):
        notes.append(
            f"sound_plan.mood dark→rnb (ecchi/sensual tone; dark is horror-only). was {mood_in!r}"
        )
        mood = "rnb"
    bed = raw.get("bed", True)
    if not isinstance(bed, bool):
        raise SoundPlanError("sound_plan.bed must be boolean")
    events_in = raw.get("events", [])
    if events_in is None:
        events_in = []
    if not isinstance(events_in, list):
        raise SoundPlanError("sound_plan.events must be an array")
    events: list[dict[str, Any]] = []
    for i, ev in enumerate(events_in):
        if not isinstance(ev, dict):
            raise SoundPlanError(f"sound_plan.events[{i}] must be an object")
        et = str(ev.get("type") or "").strip().lower()
        if et not in SPOT_EVENT_TYPES:
            raise SoundPlanError(
                f"sound_plan.events[{i}].type must be one of {sorted(SPOT_EVENT_TYPES)}"
            )
        item: dict[str, Any] = {"type": et}
        if ev.get("shot_id") is not None:
            sid = str(ev.get("shot_id")).strip()
            if not sid:
                raise SoundPlanError(f"sound_plan.events[{i}].shot_id empty")
            item["shot_id"] = sid
        if et == "mute":
            dur = float(ev.get("duration_sec", 1.0))
            if dur <= 0 or dur > 30:
                raise SoundPlanError(f"sound_plan.events[{i}].duration_sec out of range")
            item["duration_sec"] = dur
        if et == "sfx_accent":
            kind = str(ev.get("kind") or "generic").strip().lower()
            if kind not in SFX_KINDS:
                raise SoundPlanError(
                    f"sound_plan.events[{i}].kind must be one of {sorted(SFX_KINDS)}"
                )
            item["kind"] = kind
        if et == "duck":
            item["depth"] = float(ev.get("depth", 0.35))
        if ev.get("at_sec") is not None:
            item["at_sec"] = float(ev["at_sec"])
        events.append(item)
    out: dict[str, Any] = {
        "mood": mood,
        "bed": bed,
        "events": events,
    }
    if notes:
        out["_notes"] = notes
    # default auto_sfx on unless author disabled
    if "auto_sfx" not in out:
        out["auto_sfx"] = True
    return out


def apply_mute_windows_to_samples(
    samples: Any,
    *,
    sr: int,
    events: list[dict[str, Any]],
) -> Any:
    """Zero/duck BGM samples in mute/duck windows (numpy array in/out, float mono preferred)."""
    import numpy as np

    out = np.array(samples, dtype=np.float64, copy=True)
    n = len(out)
    for ev in events:
        if ev.get("type") != "mute":
            continue
        a = int(float(ev["at_sec"]) * sr)
        b = int(float(ev.get("end_sec", ev["at_sec"] + ev.get("duration_sec", 1.0))) * sr)
        a = max(0, min(n, a))
        b = max(0, min(n, b))
        if b > a:
            out[a:b] *= 0.0
    # duck: partial attenuation
    for ev in events:
        if ev.get("type") != "duck":
            continue
        a = int(float(ev["at_sec"]) * sr)
        dur = float(ev.get("duration_sec", 2.0))
        b = int((float(ev["at_sec"]) + dur) * sr)
        a = max(0, min(n, a))
        b = max(0, min(n, b))
        depth = float(ev.get("depth", 0.35))
        gain = max(0.0, 1.0 - depth)
        if b > a:
            out[a:b] *= gain
    return out


# dramatic_function → default sfx_accent kind (色气/漫剧 light touch)
_BEAT_SFX_KIND = {
    "hook": "whoosh",
    "approach": "whoosh",
    "sensory": "heartbeat",
    "reaction": "chime",
    "action": "impact",
    "afterglow": "breath",
    "bridge": "generic",
}

# heat_phase → adult flesh accent (v1.10.2)
_HEAT_SFX_KIND = {
    "setup": "whoosh",
    "foreplay": "breath",
    "act": "impact",
    "climax": "impact",
    "afterglow": "breath",
    "bridge": "generic",
}


def _shot_heat_phase(shot: dict[str, Any]) -> str:
    hp = str(shot.get("heat_phase") or "").strip().lower()
    if hp:
        return hp
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    hp = str(dsl.get("heat_phase") or "").strip().lower()
    return hp


def _kind_from_shot_cues(shot: dict[str, Any]) -> str | None:
    """Map shot sound_cues / _sfx_kinds_from_cues to primary accent kind."""
    kinds = shot.get("_sfx_kinds_from_cues")
    if isinstance(kinds, list) and kinds:
        k = str(kinds[0]).strip().lower()
        if k in SFX_KINDS:
            return k
    cues = shot.get("sound_cues")
    if isinstance(cues, list):
        for c in cues:
            cl = str(c).strip().lower()
            if cl in {"impact", "thud", "颠"}:
                return "impact"
            if cl in {"breath", "喘", "娇喘", "moan"}:
                return "breath"
            if cl in {"heartbeat", "心跳"}:
                return "heartbeat"
            if cl in {"whoosh"}:
                return "whoosh"
            if cl in {"leather", "wet"}:
                return "generic"
    return None


def suggest_auto_sfx_events(
    shots: list[dict[str, Any]],
    *,
    max_events: int = 12,
    heat_scale: str | None = None,
) -> list[dict[str, Any]]:
    """When author left events empty, place one accent per shot from beat/heat."""
    heat = (heat_scale or "").strip().lower()
    adult = heat in {"max", "hot"}
    events: list[dict[str, Any]] = []
    for shot in shots:
        if not isinstance(shot, dict) or not shot.get("id"):
            continue
        beat = str(shot.get("dramatic_function") or "bridge").strip().lower()
        ph = _shot_heat_phase(shot)
        kind = _kind_from_shot_cues(shot)
        if not kind and adult and ph in _HEAT_SFX_KIND:
            kind = _HEAT_SFX_KIND[ph]
        if not kind:
            kind = _BEAT_SFX_KIND.get(beat, "generic")
        item: dict[str, Any] = {
            "type": "sfx_accent",
            "shot_id": str(shot["id"]),
            "kind": kind,
            "auto": True,
        }

        try:
            from acoustic_policy import resolve_spatial_pan

            framing = shot.get("dsl", {}).get("framing") or shot.get("framing") or ""
            pan = resolve_spatial_pan(framing)
            item["pan"] = pan
        except ImportError:
            pass

        if kind != "whoosh":
            # act/climax flesh hits later in plate (rhythm peak)
            item["at_offset_sec"] = 0.35 if ph in {"act", "climax"} else 0.18
        if adult and ph in {"act", "climax"}:
            item["sex_sfx"] = True

        events.append(item)

        # Phase 3: Continuous Foley Injection for High Heat/Motion
        if adult and ph in {"act", "climax", "foreplay"}:
            events.append(
                {
                    "type": "sfx_accent",
                    "shot_id": str(shot["id"]),
                    "kind": "foley_cloth",
                    "auto": True,
                    "at_offset_sec": 0.05,
                    "pan": item.get("pan", 0.0),
                }
            )

        if len(events) >= max_events:
            break
    return events


def inject_sex_sfx_from_shots(
    plan: dict[str, Any] | None,
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
) -> dict[str, Any] | None:
    """Ensure act/climax shots have flesh sfx_accent (merge, do not wipe author events).

    Uses shot.sound_cues / heat_phase. Skip when auto_sfx is false.
    """
    if not plan or not isinstance(plan, dict):
        return plan
    if plan.get("auto_sfx") is False or plan.get("auto_sex_sfx") is False:
        return plan
    heat = (heat_scale or "").strip().lower()
    if heat not in {"max", "hot"}:
        return plan
    events = list(plan.get("events") or [])
    covered = {
        str(e.get("shot_id"))
        for e in events
        if isinstance(e, dict) and e.get("type") == "sfx_accent" and e.get("shot_id")
    }
    added = 0
    for shot in shots:
        if not isinstance(shot, dict) or not shot.get("id"):
            continue
        sid = str(shot["id"])
        ph = _shot_heat_phase(shot)
        if ph not in {"act", "climax", "foreplay"}:
            continue
        if sid in covered:
            continue
        kind = _kind_from_shot_cues(shot) or _HEAT_SFX_KIND.get(ph, "impact")
        try:
            from acoustic_policy import resolve_spatial_pan

            framing = shot.get("dsl", {}).get("framing") or shot.get("framing") or ""
            pan = resolve_spatial_pan(framing)
        except ImportError:
            pan = 0.0

        events.append(
            {
                "type": "sfx_accent",
                "shot_id": sid,
                "kind": kind,
                "auto": True,
                "sex_sfx": True,
                "at_offset_sec": 0.35 if ph in {"act", "climax"} else 0.2,
                "pan": pan,
            }
        )
        # Add continuous foley
        events.append(
            {
                "type": "sfx_accent",
                "shot_id": sid,
                "kind": "foley_cloth",
                "auto": True,
                "at_offset_sec": 0.05,
                "pan": pan,
            }
        )
        covered.add(sid)
        added += 1
    if not added:
        return plan
    plan = {**plan, "events": events}
    notes = list(plan.get("_notes") or [])
    notes.append(f"sex_sfx: injected {added} flesh accent(s) for act/climax/foreplay")
    plan["_notes"] = notes
    return plan


def inject_auto_sfx_if_empty(
    plan: dict[str, Any] | None,
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
) -> dict[str, Any] | None:
    """If plan has no sfx_accent and auto_sfx is not false, inject beat/heat accents."""
    if not plan or not isinstance(plan, dict):
        return plan
    if plan.get("auto_sfx") is False:
        return plan
    events = list(plan.get("events") or [])
    if any(isinstance(e, dict) and e.get("type") == "sfx_accent" for e in events):
        # still merge sex accents onto act shots missing coverage
        return inject_sex_sfx_from_shots(plan, shots, heat_scale=heat_scale)
    auto = suggest_auto_sfx_events(shots, heat_scale=heat_scale)
    if not auto:
        return plan
    plan = {**plan, "events": events + auto}
    notes = list(plan.get("_notes") or [])
    notes.append(f"auto_sfx: injected {len(auto)} accent(s) from beat/heat")
    plan["_notes"] = notes
    return plan


def sfx_clip_for_kind(kind: str, *, amp: float = 0.2) -> Any:
    """Render one procedural SFX clip (float mono) for a sound_plan kind."""
    import numpy as np

    kind = (kind or "generic").strip().lower()
    try:
        from make_sfx_bed import (  # type: ignore
            footstep,
            giggle_chime,
            heartbeat,
            soft_hat,
            soft_hit,
            sparkle,
            whoosh,
        )
    except Exception:
        # minimal fallbacks
        sr = 44100
        n = int(sr * 0.2)
        t = np.linspace(0, 0.2, n, endpoint=False)
        return (amp * np.sin(2 * np.pi * 440 * t) * np.linspace(1, 0, n)).astype(np.float64)

    if kind == "heartbeat":
        return heartbeat(amp=amp * 0.9)
    if kind == "whoosh":
        return whoosh(0.28, amp=amp * 0.85)
    if kind == "chime":
        return giggle_chime(amp=amp * 0.75)
    if kind == "impact":
        return soft_hit(amp=amp)
    if kind == "breath":
        # soft air puff — pad/align different-length primitives
        a = soft_hat(amp=amp * 0.55, open_=True) * 0.7
        b = footstep(amp=amp * 0.25)
        n = max(len(a), len(b))
        out = np.zeros(n, dtype=np.float64)
        out[: len(a)] += a
        out[: len(b)] += b
        return out
    if kind == "foley_cloth":
        # Simulate continuous cloth rustle with low-passed noise
        n = int(sr * 1.5)
        t = np.linspace(0, 1.5, n, endpoint=False)
        noise = np.random.uniform(-1, 1, n)
        env = np.sin(np.pi * t / 1.5) ** 2
        return (amp * 0.4 * noise * env).astype(np.float64)
    # generic
    return sparkle(amp=amp * 0.7)


def apply_sfx_accents_to_samples(
    samples: Any,
    *,
    sr: int,
    events: list[dict[str, Any]],
    level: float = 0.55,
) -> Any:
    """Overlay sfx_accent clips onto mono or stereo float bed. Returns float array of same shape."""
    import numpy as np

    out = np.array(samples, dtype=np.float64, copy=True)
    is_stereo = out.ndim > 1 and out.shape[1] == 2
    n = len(out)
    placed = 0
    for ev in events:
        if ev.get("type") != "sfx_accent":
            continue
        kind = str(ev.get("kind") or "generic")
        clip = np.asarray(sfx_clip_for_kind(kind, amp=0.22 * float(level)), dtype=np.float64)
        if clip.ndim > 1:
            clip = clip[:, 0]

        at = float(ev.get("at_sec") or 0.0)
        pan = float(ev.get("pan") or 0.0)

        i0 = int(at * sr)
        if i0 >= n or i0 < 0:
            continue
        i1 = min(n, i0 + len(clip))
        seg = clip[: i1 - i0]

        if is_stereo:
            # Simple constant power pan
            angle = (pan + 1.0) * np.pi / 4.0
            left_gain = np.cos(angle)
            right_gain = np.sin(angle)
            out[i0:i1, 0] += seg * left_gain
            out[i0:i1, 1] += seg * right_gain
        else:
            out[i0:i1] += seg

        placed += 1
        if ev is not None:
            ev["overlay_applied"] = True
            ev["overlay_samples"] = int(len(seg))

    # soft peak protect
    peak = float(np.max(np.abs(out))) + 1e-9
    if peak > 0.98:
        out *= 0.95 / peak
    return out


def expand_sound_events(
    plan: dict[str, Any] | None,
    *,
    shot_starts: dict[str, float],
    total_duration: float,
) -> dict[str, Any]:
    """Expand shot-relative spotting into absolute timeline events for mix report / apply.

    Supports optional ``at_offset_sec`` on events (added to shot start or at_sec).
    """
    if not plan:
        return {
            "mood": None,
            "bed": True,
            "applied_events": [],
            "total_duration": float(total_duration),
        }
    applied: list[dict[str, Any]] = []
    for ev in plan.get("events") or []:
        et = ev["type"]
        start = float(ev["at_sec"]) if ev.get("at_sec") is not None else None
        sid = ev.get("shot_id")
        if start is None and sid:
            if sid not in shot_starts:
                raise SoundPlanError(f"sound_plan event shot_id unknown: {sid}")
            start = float(shot_starts[sid])
        if start is None:
            start = 0.0
        if ev.get("at_offset_sec") is not None:
            start = float(start) + float(ev["at_offset_sec"])
        start = max(0.0, min(float(total_duration), start))
        item = {
            "type": et,
            "at_sec": round(start, 3),
            "shot_id": sid,
            "applied": True,
            "auto": bool(ev.get("auto")),
        }
        if et == "mute":
            dur = float(ev.get("duration_sec", 1.0))
            item["duration_sec"] = dur
            item["end_sec"] = round(min(total_duration, start + dur), 3)
            item["effect"] = "bed_gain_0"
        elif et == "sfx_accent":
            item["kind"] = ev.get("kind", "generic")
            item["effect"] = f"overlay_sfx:{item['kind']}"
        elif et == "duck":
            item["depth"] = float(ev.get("depth", 0.35))
            item["duration_sec"] = float(ev.get("duration_sec", 2.0))
            item["effect"] = "bed_sidechain_duck"

        if "pan" in ev:
            item["pan"] = float(ev["pan"])

        applied.append(item)
    return {
        "mood": plan.get("mood"),
        "bed": bool(plan.get("bed", True)),
        "applied_events": applied,
        "total_duration": float(total_duration),
        "event_count": len(applied),
        "auto_sfx_notes": list(plan.get("_notes") or []),
    }


def quantize_timeline_to_beat(
    timeline: list[dict[str, Any]], bpm: float = 76.0, *, quantize_step_sec: float | None = None
) -> list[dict[str, Any]]:
    """Quantize timeline boundary points to the nearest musical beat/downbeat grid."""
    if not timeline:
        return timeline
    if quantize_step_sec is None:
        # half-bar (2 beats) step at target BPM
        beat_sec = 60.0 / max(30.0, float(bpm))
        quantize_step_sec = beat_sec * 2.0

    quantized = []
    for item in timeline:
        st = float(item["start_sec"])
        ed = float(item["end_sec"])
        # Keep 0.0 fixed for absolute film start
        q_st = 0.0 if st <= 0.01 else round(st / quantize_step_sec) * quantize_step_sec
        q_ed = round(ed / quantize_step_sec) * quantize_step_sec
        if q_ed <= q_st:
            q_ed = q_st + quantize_step_sec
        c = item.copy()
        c["start_sec"] = round(q_st, 3)
        c["end_sec"] = round(q_ed, 3)
        quantized.append(c)
    return quantized


def build_mood_timeline(
    shots: list[dict[str, Any]],
    *,
    shot_starts: dict[str, float],
    shot_ends: dict[str, float],
    default_mood: str = "rnb",
    bpm: float = 76.0,
    quantize: bool = True,
) -> list[dict[str, Any]]:
    """Build a time-based mood map by analyzing the dramatic curve of shots."""
    if not shots:
        return [{"start_sec": 0.0, "end_sec": 0.0, "mood": default_mood}]

    timeline = []
    for shot in shots:
        sid = str(shot.get("id"))
        if sid not in shot_starts or sid not in shot_ends:
            continue

        st = float(shot_starts[sid])
        ed = float(shot_ends[sid])
        if ed <= st:
            continue

        # Determine mood from dramatic function and heat phase
        func = (
            str(
                shot.get("dramatic_function")
                or (shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}).get(
                    "dramatic_function"
                )
                or ""
            )
            .strip()
            .lower()
        )
        hp = _shot_heat_phase(shot)

        mood = default_mood
        if hp in {"act", "climax", "foreplay"} or func == "climax":
            mood = "rnb" if default_mood != "dark" else "dark"
        elif func in {"buildup", "rising_action", "crisis", "suspense"}:
            mood = "dark"
        elif func in {"intro", "establishing", "hook"}:
            mood = "ambient"
        elif func in {"resolution", "falling_action", "afterglow"}:
            mood = "warm"
        else:
            mood = default_mood

        timeline.append(
            {
                "start_sec": st,
                "end_sec": ed,
                "mood": mood,
                "dramatic_function": func,
                "heat_phase": hp,
            }
        )

    # Merge adjacent identical moods
    if not timeline:
        return [{"start_sec": 0.0, "end_sec": 0.0, "mood": default_mood}]

    merged = []
    timeline.sort(key=lambda x: x["start_sec"])
    curr = timeline[0].copy()

    for item in timeline[1:]:
        if item["mood"] == curr["mood"] and item["start_sec"] <= curr["end_sec"] + 0.1:
            curr["end_sec"] = max(curr["end_sec"], item["end_sec"])
        else:
            merged.append(curr)
            curr = item.copy()
    merged.append(curr)

    if quantize and bpm > 0:
        return quantize_timeline_to_beat(merged, bpm)

    return merged
