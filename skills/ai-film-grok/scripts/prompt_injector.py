import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

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
            "hair color": ["white hair", "blonde hair", "black hair", "brown hair", "red hair", "blue hair", "pink hair", "silver hair", "purple hair", "green hair"],
            "eye color": ["blue eyes", "red eyes", "green eyes", "brown eyes", "black eyes", "purple eyes"],
            "time of day": ["daytime", "night", "morning", "evening", "sunset"],
            "environment": ["indoors", "outdoors", "outside", "inside"]
        }

        for group_name, traits in conflict_groups.items():
            for trait in traits:
                if trait in lock_lower and any(t in shot_lower for t in traits if t != trait):
                    return True
        return False

    @staticmethod
    def _wardrobe_state_of(shot: dict[str, Any]) -> str:
        return str(
            shot.get("wardrobe_state")
            or (shot.get("dsl") or {}).get("wardrobe_state")
            or ""
        ).strip().lower()

    @staticmethod
    def _costume_continuity_line(w_lock: str) -> str:
        return (
            f"Costume continuity HARD: wardrobe_state={w_lock}; "
            "OPEN already at this undress level (same as previous shot or more undressed); "
            "NEVER re-dress, NEVER fully clothed, NEVER put clothes/armor back on; "
            "clothes discarded stay discarded"
        )

    @staticmethod
    def _identity_for_wardrobe(identity: str, wardrobe_state: str) -> str:
        """Strip full-dress phrases from identity lock when already undressed."""
        if wardrobe_state not in {"partial", "undressed", "bare"} or not identity:
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

        # 1. Signature / Visual Style
        sig = self.bible.get("signature_block", "")
        if sig:
            parts.append(f"Style: {sig}")

        # 2. Location / Lighting
        lighting = self.bible.get("lighting", "")
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
        char_locks = []
        state_photo_paths: list[str] = []
        try:
            from scripts.visual_bible import resolve_state_photo
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
            identity = self._identity_for_wardrobe(identity, wardrobe_state)

            wardrobe = (
                self.bible.get("wardrobe_variants", {})
                .get(hid, {})
                .get(wardrobe_state, "")
            )
            # Never fall back to default_wardrobe when undressed — that re-dresses
            if not wardrobe and wardrobe_state in {"full", "armored", "default"}:
                wardrobe = char_info.get("default_wardrobe", "")

            if identity:
                char_locks.append(f"Character {hid}: {identity}")
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
                    self.bible, str(hid), wardrobe_state, root=root
                )
                if sp:
                    state_photo_paths.append(sp)

        if char_locks:
            parts.append(" | ".join(char_locks))

        # Keyframe-first state index: tell agent which pixel ref to use
        state_photo_line = ""
        if state_photo_paths:
            primary = state_photo_paths[0]
            state_photo_line = (
                f"State photo ref: {primary} — image_edit MUST use this state photo "
                f"(or undress-anchor / prior undressed still) as PRIMARY ref for wardrobe_state={wardrobe_state}; "
                f"do NOT restart from full cast master unless state=full"
            )
            parts.append(state_photo_line)

        costume_line = ""
        if wardrobe_state in {"partial", "undressed", "bare"}:
            costume_line = self._costume_continuity_line(wardrobe_state)
            parts.append(costume_line)

        # 4. Cinematography DSL
        dsl = shot.get("dsl", {})
        camera = dsl.get("camera", {})
        cine_parts = []
        if camera.get("shot_size"): cine_parts.append(camera["shot_size"])
        if camera.get("angle"): cine_parts.append(camera["angle"])
        if dsl.get("viewpoint"): cine_parts.append(f"viewpoint: {dsl['viewpoint']}")
        if dsl.get("look_axis"): cine_parts.append(f"looking {dsl['look_axis']}")
        if dsl.get("focal_character"): cine_parts.append(f"focus on {dsl['focal_character']}")

        cine_block = ""
        if cine_parts:
            cine_block = "Cinematography: " + ", ".join(cine_parts)

        # 5. Continuity State
        states = self.bible.get("continuity_states", {})
        active_states = []
        for st_name, st_desc in states.items():
            active_states.append(st_desc)
        # start_pose continuity into prompt
        start_pose = str(dsl.get("start_pose") or "").strip()

        # 6. Shot-Specific Action
        shot_action = dsl.get("action", "") or shot.get("nar", "")

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
                raise PromptConflictError(f"Shot prompt '{shot_action}' conflicts with locked trait '{lock}'")

        # Template Branching: T2I vs I2V — ALWAYS re-attach costume continuity
        if self.template_version == "I2V":
            # Identity from input image; still forbid re-dress in motion prompt
            parts = []
            if costume_line:
                parts.append(costume_line)
            if state_photo_line:
                parts.append(
                    "I2V input MUST be keyframe built from state photo / undress-anchor; "
                    "Keep first-frame clothing — never re-dress"
                )
            if cine_block:
                parts.append(cine_block)
            if active_states:
                parts.append(f"Continuity: {', '.join(active_states)}")
            if start_pose:
                parts.append(f"Start already: {start_pose}")
            if shot_action:
                parts.append(f"Motion/Action: {shot_action}")
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
            if state_photo_line:
                parts.append(state_photo_line)
            if costume_line:
                parts.append(costume_line)
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
        re_dress_no = (
            "fully clothed after undress, clothes reappearing, re-dressed, "
            "full armor during sex, intact outfit after strip, 回穿, 脱完又穿上"
        )
        if wardrobe_state in {"partial", "undressed", "bare"}:
            if negatives:
                negatives = f"{negatives}, {re_dress_no}"
            else:
                negatives = re_dress_no

        final_prompt = "\n".join(parts)
        if negatives:
            final_prompt += f"\n--no {negatives}"

        # Traceability receipt
        receipt = {
            "shot_id": shot.get("id"),
            "template_version": self.template_version,
            "bible_version": self.bible.get("schema_version"),
            "bible_state": self.bible.get("state"),
            "wardrobe_state": wardrobe_state,
            "state_photo_paths": state_photo_paths,
            "state_photo_primary": state_photo_paths[0] if state_photo_paths else None,
            "prompt_text": final_prompt,
            "prompt_hash": _sha256(final_prompt),
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
