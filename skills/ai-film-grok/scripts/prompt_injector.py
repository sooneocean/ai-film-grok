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

    def assemble(self, shot: dict[str, Any], root: Path) -> dict[str, Any]:
        """
        Assemble the prompt strictly following priority:
        1. Signature / Visual Style
        2. Location / Lighting
        3. Character Lock & Wardrobe Lock
        4. Continuity State
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
        characters = self.bible.get("characters", {})
        
        char_locks = []
        for hid in heroine_ids:
            char_info = characters.get(hid, {})
            identity = char_info.get("identity", "")
            if not identity and hid == "hero":
                identity = self.bible.get("identity_lock", "")
                
            # Prefer shot-level wardrobe_state (continuity carry) over dsl-only
            wardrobe_state = (
                shot.get("wardrobe_state")
                or (shot.get("dsl") or {}).get("wardrobe_state")
                or "default"
            )
            wardrobe = (
                self.bible.get("wardrobe_variants", {})
                .get(hid, {})
                .get(wardrobe_state, char_info.get("default_wardrobe", ""))
            )
            
            if identity:
                char_locks.append(f"Character {hid}: {identity}")
            if wardrobe:
                char_locks.append(f"Wardrobe {hid} ({wardrobe_state}): {wardrobe}")
            elif wardrobe_state and wardrobe_state != "default":
                # Explicit state even without bible variant — blocks full-dress drift
                char_locks.append(
                    f"Wardrobe state {hid}: {wardrobe_state} "
                    f"(continue undress ladder; do NOT re-dress / clothes must not reappear)"
                )
                
        if char_locks:
            parts.append(" | ".join(char_locks))
        # Continuity lock: once undressed, never re-clothe in later stills/I2V
        w_lock = shot.get("wardrobe_state") or (shot.get("dsl") or {}).get("wardrobe_state")
        if w_lock in {"partial", "undressed", "bare"}:
            parts.append(
                f"Costume continuity: wardrobe_state={w_lock}; "
                "same undress progress as previous shot or more undressed; "
                "NEVER fully clothed or re-armored after undress"
            )
            
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
                
        # Template Branching: T2I vs I2V
        if self.template_version == "I2V":
            # Condense static elements, focus on motion and camera
            # Identity is mostly derived from the input image
            parts = []
            if cine_block: parts.append(cine_block)
            if active_states: parts.append(f"Continuity: {', '.join(active_states)}")
            if shot_action: parts.append(f"Motion/Action: {shot_action}")
            if tone_line: parts.append(tone_line)
            # sound cues stay off I2V motion text (SFX is mix-layer)
        else:
            # Full T2I Injection
            parts = []
            if sig: parts.append(f"Style: {sig}")
            if lighting: parts.append(f"Lighting: {lighting}")
            if char_locks: parts.append(" | ".join(char_locks))
            if active_states: parts.append(f"Continuity: {', '.join(active_states)}")
            if cine_block: parts.append(cine_block)
            if shot_action: parts.append(f"Action: {shot_action}")
            if tone_line: parts.append(tone_line)
            if sound_line: parts.append(sound_line)
            
        # 6. Negative Constraints
        negatives = self.bible.get("negative_hints", "")
        
        final_prompt = "\n".join(parts)
        if negatives:
            final_prompt += f"\n--no {negatives}"
            
        # Traceability receipt
        receipt = {
            "shot_id": shot.get("id"),
            "template_version": self.template_version,
            "bible_version": self.bible.get("schema_version"),
            "bible_state": self.bible.get("state"),
            "prompt_text": final_prompt,
            "prompt_hash": _sha256(final_prompt),
            "generated_at": utc_now()
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
