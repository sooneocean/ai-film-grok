import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Path used by motion spine film-spec load (root may be Path | str).


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _dedupe_csv(value: str) -> str:
    """Keep ordered negative constraints while dropping exact repeated tokens."""
    seen: set[str] = set()
    kept: list[str] = []
    for item in value.split(","):
        normalized = item.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            kept.append(normalized)
    return ", ".join(kept)


def _prompt_metrics(prompt: str) -> dict[str, int]:
    """Expose a conservative local estimate; providers remain the billing authority."""
    characters = len(prompt)
    return {
        "characters": characters,
        "estimated_input_tokens": (characters + 3) // 4,
    }


class PromptConflictError(Exception):
    pass


class PromptInjector:
    def __init__(self, bible: dict[str, Any], template_version: str = "T2I"):
        self.bible = bible
        self.template_version = template_version

    def detect_conflict(self, lock_text: str, shot_text: str) -> bool:
        """
        Advanced conflict detection:
        Checks multiple axes (hair color, eye color, time of day, environment).
        """
        lock_lower = lock_text.lower()
        shot_lower = shot_text.lower()

        conflict_groups = {
            "hair color": [
                "white hair",
                "blonde hair",
                "black hair",
                "brown hair",
                "red hair",
                "blue hair",
                "pink hair",
                "silver hair",
                "purple hair",
                "green hair",
            ],
            "eye color": [
                "blue eyes",
                "red eyes",
                "green eyes",
                "brown eyes",
                "black eyes",
                "purple eyes",
            ],
            "time of day": ["daytime", "night", "morning", "evening", "sunset"],
            "environment": ["indoors", "outdoors", "outside", "inside"],
        }

        for _group_name, traits in conflict_groups.items():
            for trait in traits:
                if trait in lock_lower and any(t in shot_lower for t in traits if t != trait):
                    return True
        return False

    @staticmethod
    def _wardrobe_state_of(shot: dict[str, Any]) -> str:
        return (
            str(shot.get("wardrobe_state") or (shot.get("dsl") or {}).get("wardrobe_state") or "")
            .strip()
            .lower()
        )

    @staticmethod
    def _costume_continuity_line(w_lock: str) -> str:
        return (
            f"Costume continuity HARD: wardrobe_state={w_lock}; "
            "OPEN already at this undress level (same as previous shot or more undressed); "
            "NEVER re-dress, NEVER fully clothed, NEVER put clothes/armor back on; "
            "clothes discarded stay discarded"
        )

    @staticmethod
    def _get_heat_escalation_tokens(heat_phase: str, coitus_beat: str) -> str:
        """Return intensity-boosting descriptors based on the erotic arc.

        Arc: Setup -> Build-up -> Act (Piston) -> Climax (Release)
        """
        # Intensity levels: 1 (mild) to 4 (extreme)
        # Mapping: heat_phase + coitus_beat -> descriptors
        escalation_map = {
            "setup": {
                "default": "tense atmosphere, heavy breathing, lingering gaze",
                "approach": "trembling anticipation, electric skin contact",
            },
            "foreplay": {
                "default": "aroused skin, moisture, desperate touch, soft moans",
                "entry": "edge of climax, urgent desire, slow spreading",
            },
            "act": {
                "default": "deep rhythmic thrusting, skin slapping, wet friction, heavy panting",
                "union": "tight lock, deep pelvis sink, rhythmic grinding",
                "rhythm": "rapid piston motion, vigorous thrusting, sweat-slicked skin, intense hip travel",
                "lock": "clutching tight, deep penetration, trembling thighs",
            },
            "climax": {
                "default": "extreme ecstasy, back arching, uncontrollable shaking, blurred vision",
                "finish": "explosive release, peak orgasm, fluid exchange, total surrender",
                "release": "shuddering release, heavy gasping, peak pleasure",
            },
        }

        phase_data = escalation_map.get(heat_phase, {})
        # Prefer specific coitus_beat over default for that phase
        return phase_data.get(coitus_beat, phase_data.get("default", ""))

    @staticmethod
    def _identity_for_wardrobe(
        identity: str, wardrobe_state: str, shot: dict[str, Any] | None = None
    ) -> str:
        out = identity or ""
        if wardrobe_state not in {"partial", "undressed", "bare"} and not (
            isinstance(shot, dict) and isinstance(shot.get("character_states"), dict)
        ):
            return identity
        # Keep face/hair/eyes; drop outfit-complete language that fights undress ladder
        bad = (
            "full stage costume",
            "full costume",
            "full wardrobe",
            "fully clothed",
            "complete outfit",
            "armor intact",
            "全装",
            "衣着整齐",
        )
        out = identity
        low = out.lower()
        for b in bad:
            if b in low:
                # case-insensitive soft remove
                import re

                out = re.sub(re.escape(b), "", out, flags=re.IGNORECASE)
                low = out.lower()
        extra = {
            "partial": " [NOW partial undress — shirt open/disordered, NOT full dress]",
            "undressed": " [NOW undressed — main outfit off, bare skin readable, NOT full dress]",
            "bare": " [NOW bare/exposed — clothes discarded, NEVER re-clothe]",
        }.get(wardrobe_state, "")

        # Multi-axis character physical state tag formatting
        c_states = (
            shot.get("character_states")
            if isinstance(shot, dict) and isinstance(shot.get("character_states"), dict)
            else {}
        )
        state_tags = []
        if c_states.get("hair") and c_states["hair"] != "neat":
            state_tags.append(f"hair: {c_states['hair']}")
        if c_states.get("skin") and c_states["skin"] != "normal":
            state_tags.append(f"skin: {c_states['skin']}")
        if c_states.get("arousal") and c_states["arousal"] != "calm":
            state_tags.append(f"state: {c_states['arousal']}")

        gaze = (
            (shot.get("gaze_target") or shot.get("gazeTarget") or "")
            if isinstance(shot, dict)
            else ""
        )
        if gaze:
            state_tags.append(f"gaze: {gaze.replace('_', ' ')}")

        if state_tags:
            extra += f" [{'; '.join(state_tags)}]"

        return (out.strip(" ,;") + extra).strip()

    def assemble(self, shot: dict[str, Any], root: Path) -> dict[str, Any]:
        """
        Assemble the prompt strictly following priority:
        1. Signature / Visual Style
        2. Location / Lighting
        3. Character Lock & Wardrobe Lock
        4. Continuity State (+ undress ladder never re-dress)
        5. Shot-Specific Action
        6. Negative Constraints (--no ...)
        """
        parts = []

        # 1. Signature / Visual Style (+ medium fingerprint hard lock)
        fp = (
            self.bible.get("style_fingerprint")
            if isinstance(self.bible.get("style_fingerprint"), dict)
            else {}
        )
        medium_key = str(fp.get("medium_key") or "").strip()
        if medium_key or fp.get("medium"):
            parts.append(
                f"MEDIUM LOCK: {fp.get('medium') or medium_key} — NEVER switch medium mid-film"
            )
        if fp.get("still_hint"):
            parts.append(f"Style medium: {fp['still_hint']}")
        sig = self.bible.get("signature_block", "")
        if sig:
            parts.append(f"Style: {sig}")
        # Prefer bible agent prefix tokens when present (input-ref style-lock)
        prefix = str(self.bible.get("agent_still_prompt_prefix") or "").strip()
        # Avoid double-dumping full prefix (can exceed budget); only identity lines if huge
        if prefix and len(prefix) < 900 and "MEDIUM LOCK" not in " ".join(parts):
            parts.insert(0, prefix.split("\n")[0])

        # 2. Location / Lighting
        lighting = self.bible.get("lighting", "") or str(fp.get("lighting") or "")
        if lighting:
            parts.append(f"Lighting: {lighting}")

        # 3. Character Lock & Wardrobe Lock
        heroine_ids = shot.get("heroine_ids", ["hero"])
        # Also honor dsl.cast / focal heroine keys if heroine_ids default-only
        dsl0 = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        cast_ids = dsl0.get("cast") if isinstance(dsl0.get("cast"), list) else []
        if cast_ids and heroine_ids == ["hero"]:
            heroine_ids = [str(c) for c in cast_ids if c]
        characters = self.bible.get("characters", {})

        wardrobe_state = self._wardrobe_state_of(shot) or "default"
        wardrobe_state_id = shot.get("wardrobe_state_id") or dsl0.get("wardrobe_state_id")
        wardrobe_state_id = str(wardrobe_state_id).strip() if wardrobe_state_id else None
        char_locks = []
        state_photo_paths: list[str] = []
        state_photo_records: list[dict[str, Any]] = []
        try:
            from visual_bible import resolve_state_photo
        except Exception:
            try:
                from visual_bible import resolve_state_photo  # type: ignore
            except Exception:
                resolve_state_photo = None  # type: ignore

        for hid in heroine_ids:
            char_info = characters.get(hid, {})
            identity = char_info.get("identity", "")
            if not identity and hid in {"hero", "fufu", "astra", "xide"}:
                identity = self.bible.get("identity_lock", "")
            identity = self._identity_for_wardrobe(identity, wardrobe_state, shot=shot)

            # P1-1: prefer structured cast_locks over free-text identity
            cast_lock = self.bible.get("cast_locks", {})
            cl = cast_lock.get(hid, {}) if isinstance(cast_lock, dict) else {}
            if cl.get("identity_lock_tokens"):
                # Structured lock takes precedence — includes face/hair/eyes
                identity = cl["identity_lock_tokens"]

            wardrobe_raw = (
                self.bible.get("wardrobe_variants", {}).get(hid, {}).get(wardrobe_state, "")
            )
            # P1-4: support structured wardrobe object (garment/accessories/material/color)
            if isinstance(wardrobe_raw, dict):
                w_parts = []
                if wardrobe_raw.get("garment"):
                    w_parts.append(str(wardrobe_raw["garment"]))
                accs = wardrobe_raw.get("accessories")
                if isinstance(accs, list) and accs:
                    w_parts.append("accessories: " + ", ".join(str(a) for a in accs))
                if wardrobe_raw.get("material"):
                    w_parts.append(f"material: {wardrobe_raw['material']}")
                if wardrobe_raw.get("color"):
                    w_parts.append(f"color: {wardrobe_raw['color']}")
                wardrobe = "; ".join(w_parts) if w_parts else ""
            else:
                wardrobe = str(wardrobe_raw) if wardrobe_raw else ""
            # Never fall back to default_wardrobe when undressed — that re-dresses
            if not wardrobe and wardrobe_state in {"full", "armored", "default"}:
                wardrobe = char_info.get("default_wardrobe", "")

            if identity:
                char_locks.append(f"Character {hid}: {identity}")

            # P1-1: Hair lock line (consistency.md H4 — was missing in prompt_injector)
            hair_lock = cl.get("hair_lock") or ""
            if not hair_lock:
                # Fallback: build from hair_swatches
                sw = self.bible.get("hair_swatches", {})
                sw_entry = sw.get(hid, {}) if isinstance(sw, dict) else {}
                if sw_entry.get("color_name"):
                    hair_lock = f"{sw_entry['color_name']}"
                    if sw_entry.get("description"):
                        hair_lock += f"; {sw_entry['description']}"
            if hair_lock:
                never = cl.get("never_tokens", "")
                hair_line = f"Hair lock {hid}: {hair_lock}"
                if never:
                    hair_line += f" ({never})"
                char_locks.append(hair_line)

            # P1-3: Makeup lock line
            makeup_lock = cl.get("makeup_lock") or ""
            if not makeup_lock:
                mu = self.bible.get("makeup", {})
                mu_entry = mu.get(hid, {}) if isinstance(mu, dict) else {}
                if mu_entry.get("lock_tokens"):
                    makeup_lock = mu_entry["lock_tokens"]
            if makeup_lock:
                char_locks.append(f"Makeup {hid}: {makeup_lock}")

            if wardrobe:
                if wardrobe_state == "default":
                    char_locks.append(f"Wardrobe {hid}: {wardrobe}")
                else:
                    char_locks.append(f"Wardrobe {hid} ({wardrobe_state}): {wardrobe}")
            elif wardrobe_state and wardrobe_state != "default":
                char_locks.append(
                    f"Wardrobe state {hid}: {wardrobe_state} "
                    f"(continue undress ladder; do NOT re-dress / clothes must not reappear)"
                )

            if resolve_state_photo is not None:
                sp = resolve_state_photo(
                    self.bible,
                    str(hid),
                    wardrobe_state,
                    root=root,
                    wardrobe_state_id=wardrobe_state_id,
                )
                if sp:
                    state_photo_paths.append(sp)
                    if wardrobe_state_id:
                        try:
                            from wardrobe_ladder import state_for_id

                            state = state_for_id(self.bible, str(hid), wardrobe_state_id) or {}
                            state_photo_records.append(
                                {
                                    "character_id": str(hid),
                                    "wardrobe_state_id": wardrobe_state_id,
                                    "parent_state_id": state.get("parent_state_id"),
                                    "removed_garment_ids": state.get("removed_garment_ids") or [],
                                    "state_photo_sha256": state.get("sha256"),
                                }
                            )
                        except ImportError:
                            pass

        if char_locks:
            parts.append(" | ".join(char_locks))
        elif fp.get("medium_key") == "photoreal":
            # Force identity reminder when cast_locks empty (common drift path)
            il = str(self.bible.get("identity_lock") or "").strip()
            if il and "to be filled" not in il.lower():
                parts.append(f"Identity lock: {il}")

        # Keyframe-first state index: tell agent which pixel ref to use
        reference_instruction = ""
        style_reference = (
            self.bible.get("style_reference")
            if isinstance(self.bible.get("style_reference"), dict)
            else {}
        )
        if style_reference.get("staged_path") and style_reference.get("sha256"):
            reference_instruction = (
                "Style reference: "
                f"{style_reference['staged_path']} (sha256={style_reference['sha256']}) — "
                "attach/use this uploaded image as the PRIMARY style reference for every still; "
                "match its linework/rendering, palette, texture, and lighting language; "
                "do not substitute a new style. "
            )
        if state_photo_paths:
            primary = state_photo_paths[0]
            if reference_instruction:
                reference_instruction = reference_instruction.replace(
                    "PRIMARY style reference", "SECONDARY style-only reference"
                )
            state_instruction = (
                f"State photo ref: {primary} — image_edit MUST use this state photo as the PRIMARY pixel reference "
                f"(or undress-anchor / prior undressed still) for wardrobe_state={wardrobe_state}"
                f" state_id={wardrobe_state_id or 'legacy'}; "
                f"do NOT restart from full cast master unless state=full"
            )
            reference_instruction += state_instruction

        costume_line = ""
        if wardrobe_state in {"partial", "undressed", "bare"}:
            costume_line = self._costume_continuity_line(wardrobe_state)
            parts.append(costume_line)

        # 3a. Adult max IRON (能脱就脱 / 能露就露)
        heat_scale_global = (
            str(
                self.bible.get("heat_scale")
                or (self.bible.get("film") or {}).get("heat_scale")
                or ""
            )
            .strip()
            .lower()
        )
        if heat_scale_global == "max" or wardrobe_state in {"partial", "undressed", "bare"}:
            iron = (
                "Adult max IRON: undress/expose when possible; never re-dress; "
                "climax must be bare readable; discarded clothes stay off; "
                "prefer bare skin / undressed over full costume; "
                "CONTINUOUSLY CHALLENGE MAXIMUM HEAT — escalate every beat, "
                "never cool down mid-film, never plateau soft, no safer retake language"
            )
            parts.append(iron)

        # 3b. Coitus / heat pose lock (act/climax — Mute Frame readable)
        heat_phase = (
            str(shot.get("heat_phase") or (shot.get("dsl") or {}).get("heat_phase") or "")
            .strip()
            .lower()
        )
        coitus_beat = (
            str(shot.get("coitus_beat") or (shot.get("dsl") or {}).get("coitus_beat") or "")
            .strip()
            .lower()
        )
        sex_arc_beat = (
            str(shot.get("sex_arc_beat") or (shot.get("dsl") or {}).get("sex_arc_beat") or "")
            .strip()
            .lower()
        )
        coitus_line = ""
        if (
            heat_phase in {"act", "climax"}
            or coitus_beat
            in {
                "entry",
                "union",
                "rhythm",
                "lock",
                "finish",
            }
            or sex_arc_beat in {"penetration", "climax_release", "entry"}
        ):
            coitus_line = (
                "Coitus readability HARD: pelvis contact / hips-sink / straddle-seat "
                "or grind must be visible in frame; NOT soft hug or eye-contact only; "
                f"coitus_beat={coitus_beat or heat_phase}; "
                f"sex_arc_beat={sex_arc_beat or 'n/a'}; weight down, thighs readable; "
                "do NOT put clothes back on"
            )

            # Add Dynamic Escalation Tokens based on the erotic arc
            escalation_tokens = self._get_heat_escalation_tokens(heat_phase, coitus_beat)
            if escalation_tokens:
                coitus_line += f" | Intensity: {escalation_tokens}"

            parts.append(coitus_line)
            # Motion template bind by sex_arc / coitus (I2V thrust readability)
            motion_bind = {
                "union": "union_settle hips settle pelvis-lock",
                "rhythm": "rhythm_hips hips-sink thrust-rhythm twice",
                "lock": "lock_clutch leg-wrap clutch",
                "finish": "finish_arch residual-tremor",
                "penetration": "rhythm_hips hips-sink thrust-rhythm",
                "climax_release": "finish_arch arch-finish release",
                "entry": "entry_pin weight drop mount",
            }
            bind_key = coitus_beat or sex_arc_beat
            if bind_key in motion_bind:
                parts.append(
                    f"I2V motion HARD bind: {motion_bind[bind_key]}; "
                    "no soft lean / Ken Burns only; visible hip travel"
                )
            pw = shot.get("partner_wardrobe_state") or (shot.get("dsl") or {}).get(
                "partner_wardrobe_state"
            )
            if pw:
                parts.append(
                    f"Partner wardrobe HARD: partner_wardrobe_state={pw}; "
                    "male/partner bottoms discarded when undressed|bare; "
                    "no pants/underwear during penetration"
                )
            cov = (
                str(shot.get("coverage_role") or (shot.get("dsl") or {}).get("coverage_role") or "")
                .strip()
                .lower()
            )
            framing = (
                str(shot.get("framing") or (shot.get("dsl") or {}).get("framing") or "")
                .strip()
                .lower()
            )
            if cov == "detail" or any(
                x in framing for x in ("union_closeup", "genital_lock", "waist_lock")
            ):
                parts.append(
                    "Detail CU HARD: waist/pelvis union lock framing; "
                    "suggestive contact readable; keep headroom if face in frame"
                )

        # 4. Cinematography DSL
        dsl = shot.get("dsl", {})
        camera = dsl.get("camera", {})
        cine_parts = []
        if camera.get("shot_size"):
            cine_parts.append(camera["shot_size"])
        if camera.get("angle"):
            cine_parts.append(camera["angle"])
        if dsl.get("viewpoint"):
            cine_parts.append(f"viewpoint: {dsl['viewpoint']}")
        if dsl.get("look_axis"):
            cine_parts.append(f"looking {dsl['look_axis']}")
        if dsl.get("focal_character"):
            cine_parts.append(f"focus on {dsl['focal_character']}")

        cine_block = ""
        if cine_parts:
            cine_block = "Cinematography: " + ", ".join(cine_parts)
        # Seedance camera language bridge (2026-07-23): append the rich cinema-grade
        # camera_prompt produced by cinema_prompt so I2V providers receive move/shot/
        # angle/pacing/lighting/palette in one structured block.
        camera_prompt = str(dsl.get("camera_prompt") or "").strip()
        if camera_prompt:
            cine_block = f"{cine_block}\n{camera_prompt}" if cine_block else camera_prompt

        # 5. Continuity State
        states = self.bible.get("continuity_states", {})
        active_states = []
        for _st_name, st_desc in states.items():
            active_states.append(st_desc)
        # start_pose continuity into prompt
        start_pose = str(dsl.get("start_pose") or "").strip()

        # 6. Shot-Specific Action.  VO/dialogue never becomes a visual action:
        # only observable body/prop action and an in-scene reaction may enter.
        try:
            from content_channels import resolve_content_channels, visual_prompt_action

            content = resolve_content_channels(shot)
            shot_action = visual_prompt_action(shot)
        except Exception:
            content = {}
            shot_action = str(dsl.get("action") or "").strip()

        # 6a. Motion Prompt Spine (shared with H3): DF + want_beat + tier + dialogue
        # I2V fail-closed (Phase A); escape AIFILM_SKIP_MOTION_CORE=1
        spine_clauses: list[str] = []
        film_spec: dict[str, Any] = {}
        from motion_prompt_spine import (
            MotionCoreError,
            motion_core_clauses,
            motion_core_skip_enabled,
        )
        from util import read_json

        try:
            if root is not None:
                film_spec = read_json(Path(root) / "film-spec.json") or {}
            # Dialogue lip-sync still injected for on_camera so bulk stays speech-aware.
            spine_clauses = motion_core_clauses(
                film_spec if isinstance(film_spec, dict) else {},
                shot,
                include_audio=bool(
                    str(shot.get("screen_mode") or "") in {"on_camera", "off_camera"}
                    or any(
                        isinstance(c, dict)
                        and c.get("line_type") == "dialogue"
                        and str(c.get("spoken_text") or "").strip()
                        for c in (shot.get("audio_cues") or [])
                        if isinstance(shot.get("audio_cues"), list)
                    )
                ),
            )
        except Exception as exc:
            if self.template_version == "I2V" and not motion_core_skip_enabled():
                raise MotionCoreError(
                    f"MOTION_CORE_SPINE_BUILD: failed to build motion core for "
                    f"{shot.get('id')!r}: {exc}"
                ) from exc
            spine_clauses = []

        # 6b. Tone tags = performance manner (still/I2V face/body acting)
        #     Sound cues = ambient/SFX description (must NOT be spoken as nar)
        tone_line = ""
        sound_line = ""
        try:
            from voice_tracks import (
                normalize_sound_cues,
                normalize_tone_tags,
                tone_tags_to_prompt,
            )

            tone_line = tone_tags_to_prompt(normalize_tone_tags(shot.get("tone_tags")))
            cues = normalize_sound_cues(shot.get("sound_cues"))
            if cues:
                sound_line = "Ambient/SFX cues (not dialogue): " + ", ".join(cues)
        except Exception:
            tone_line = ""
            sound_line = ""

        # Conflict Detection
        # Check against both character locks and global lighting/style locks
        global_locks = f"{sig} {lighting} {', '.join(active_states)}"
        for lock in char_locks + [global_locks]:
            if self.detect_conflict(lock, shot_action):
                raise PromptConflictError(
                    f"Shot prompt '{shot_action}' conflicts with locked trait '{lock}'"
                )

        # Template Branching: T2I vs I2V — ALWAYS re-attach costume continuity
        if self.template_version == "I2V":
            # Identity from input image; still forbid re-dress in motion prompt
            parts = []
            if costume_line:
                parts.append(costume_line)
            if coitus_line:
                parts.append(coitus_line)
            if cine_block:
                parts.append(cine_block)
            if active_states:
                parts.append(f"Continuity: {', '.join(active_states)}")
            if start_pose:
                parts.append(f"Start already: {start_pose}")
            # Spine first so DF/want/tier frame the action (parity with H3).
            for clause in spine_clauses:
                cl = str(clause).strip()
                if cl and cl not in parts and (not shot_action or cl != shot_action):
                    parts.append(cl)
            # go4 · Grok continue handoff (read previous endframe packet into prompt)
            try:
                from continue_handoff import resolve_continue_handoff

                cont = resolve_continue_handoff(
                    root, str(shot.get("id") or ""), shot=shot
                )
                if cont.get("ok") and cont.get("wants_continue") and cont.get("prompt_clause"):
                    pc = str(cont["prompt_clause"])
                    if pc not in parts:
                        parts.insert(0, pc)
            except Exception:
                pass
            if shot_action and f"Motion/Action: {shot_action}" not in parts:
                # Avoid duplicating action already present via spine dsl join
                if shot_action not in " ".join(parts):
                    parts.append(f"Motion/Action: {shot_action}")
            voice = content.get("voice") if isinstance(content, dict) else {}
            if (
                isinstance(voice, dict)
                and voice.get("kind") == "narration"
                and not voice.get("lipsync")
            ):
                parts.append("Narration is audio-only: no invented speech or mouth movement")
            elif (
                isinstance(voice, dict) and voice.get("kind") == "dialogue" and voice.get("lipsync")
            ):
                parts.append(
                    "Use supplied dialogue audio for lipsync; do not invent additional words"
                )
            if tone_line:
                parts.append(tone_line)
        else:
            # Full T2I Injection
            parts = []
            if sig:
                parts.append(f"Style: {sig}")
            if lighting:
                parts.append(f"Lighting: {lighting}")
            if char_locks:
                parts.append(" | ".join(char_locks))
            if costume_line:
                parts.append(costume_line)
            if coitus_line:
                parts.append(coitus_line)
            if active_states:
                parts.append(f"Continuity: {', '.join(active_states)}")
            if start_pose:
                parts.append(f"Start already: {start_pose}")
            if cine_block:
                parts.append(cine_block)
            if shot_action:
                parts.append(f"Action: {shot_action}")
            if tone_line:
                parts.append(tone_line)
            if sound_line:
                parts.append(sound_line)

        # 6. Negative Constraints — always ban re-dress when undressed
        negatives = self.bible.get("negative_hints", "")
        anatomy_no = (
            "futa, female penis, penis on woman, wrong genital anatomy, lactation, milk spray, "
            "breast milk, neon genital symbol, glowing genitals, wet nipples, neon light explosion, "
            "glowing orb on genitals, neon sphere at contact point, 伪娘阴茎, 女体阴茎, "
            "喷奶, 乳汁, 霓虹生殖器, 发光性器官, 湿乳头, 结合处霓虹光, 霓虹光球, 结合部爆光"
        )
        if str(self.bible.get("heat_scale") or "").strip().lower() == "max":
            negatives = f"{negatives}, {anatomy_no}" if negatives else anatomy_no
        re_dress_no = (
            "fully clothed after undress, clothes reappearing, re-dressed, "
            "full armor during sex, intact outfit after strip, 回穿, 脱完又穿上"
        )
        if wardrobe_state in {"partial", "undressed", "bare"}:
            negatives = f"{negatives}, {re_dress_no}" if negatives else re_dress_no
        negatives = _dedupe_csv(negatives)

        if str(self.bible.get("heat_scale") or "").strip().lower() == "max":
            parts.append(
                "Anatomy hard: anatomically correct adult bodies, penis only on man, dry nipples; "
                "no anatomical fusion or neon-genital artifact"
            )
        final_prompt = "\n".join(parts)
        if negatives:
            final_prompt += f"\n--no {negatives}"

        # Phase A: Grok I2V same fail-closed core as H3 / media-queue
        if self.template_version == "I2V" and not motion_core_skip_enabled():
            from motion_prompt_spine import assert_motion_prompt_core

            assert_motion_prompt_core(
                final_prompt,
                shot,
                mode="i2v",
                role=str(shot.get("shot_role") or "hero"),
            )

        # Phase B: Grok spine receipt (film_core_closeout dual-track)
        if self.template_version == "I2V" and root is not None:
            try:
                sid = str(shot.get("id") or "unknown")
                spine_dir = Path(root) / "receipts" / "prompts"
                spine_dir.mkdir(parents=True, exist_ok=True)
                (spine_dir / f"{sid}.grok.spine.txt").write_text(
                    final_prompt.rstrip() + "\n", encoding="utf-8"
                )
            except OSError:
                pass

        # Traceability receipt
        receipt = {
            "shot_id": shot.get("id"),
            "template_version": self.template_version,
            "bible_version": self.bible.get("schema_version"),
            "bible_state": self.bible.get("state"),
            "wardrobe_state": wardrobe_state,
            "wardrobe_state_id": wardrobe_state_id,
            "state_photo_paths": state_photo_paths,
            "state_photo_primary": state_photo_paths[0] if state_photo_paths else None,
            "state_photo_records": state_photo_records,
            "style_reference": style_reference or None,
            "reference_instruction": reference_instruction or None,
            "prompt_text": final_prompt,
            "prompt_hash": _sha256(final_prompt),
            "prompt_metrics": _prompt_metrics(final_prompt),
            "generated_at": utc_now(),
            "keyframe_first_note": (
                "Build keyframe from state_photo_primary (or undress-anchor); "
                "I2V only from that keyframe; never full-cast restart when undressed"
            ),
        }

        # Save receipt
        receipt_dir = root / "receipts"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_dir / f"prompt_assembly_{shot.get('id', 'unknown')}.json"

        with open(receipt_path, "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2, ensure_ascii=False)

        # Also write the raw text for backward compatibility with `media-queue --prompt-file`
        prompts_dir = root / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        text_path = prompts_dir / f"{shot.get('id', 'unknown')}.txt"
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(final_prompt)

        receipt["text_path"] = str(text_path)

        return receipt
