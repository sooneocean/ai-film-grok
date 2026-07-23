"""Tests for P1-8: dialogue ledger.

Verifies:
- DialogueLine schema exists with required fields
- DIALOGUE_LEDGER_MISSING lint fires when shot has dialogue but no line_id anchor
- No warning when shot has dialogue + dialogueLineIds
- No warning when shot has no dialogue
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from continuity import CODE_DIALOGUE_LEDGER_MISSING, lint_continuity


class TestDialogueLineSchema:
    """DialogueLine def exists with required fields."""

    def test_dialogue_line_def_exists(self):
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "drama-graph.schema.json"
        schema = json.loads(schema_path.read_text())
        defs = schema.get("$defs", {})
        assert "DialogueLine" in defs
        dl = defs["DialogueLine"]
        props = dl.get("properties", {})
        assert "line_id" in props
        assert "speaker" in props
        assert "text" in props
        assert "emotion" in props
        assert "subtext" in props
        assert "beat_ref" in props
        assert "shot_ref" in props
        assert "delivery_note" in props
        assert "lipsync_anchor" in props
        assert "is_key_line" in props

    def test_dialogue_ledger_top_level_exists(self):
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "drama-graph.schema.json"
        schema = json.loads(schema_path.read_text())
        props = schema.get("properties", {})
        assert "dialogue_ledger" in props


class TestDialogueLedgerMissing:
    """DIALOGUE_LEDGER_MISSING lint fires on shots with dialogue but no line_id."""

    def test_shot_with_dialogue_no_line_id_triggers_warning(self):
        shots = [
            {"id": "s1", "dramatic_function": "action", "dialogue": "hello world"},
        ]
        result = lint_continuity(shots)
        assert CODE_DIALOGUE_LEDGER_MISSING in result["codes"]

    def test_shot_with_dialogue_and_line_id_no_warning(self):
        shots = [
            {"id": "s1", "dramatic_function": "action", "dialogue": "hello world", "dialogueLineIds": ["dlg_001"]},
        ]
        result = lint_continuity(shots)
        assert CODE_DIALOGUE_LEDGER_MISSING not in result["codes"]

    def test_shot_with_lipsync_no_line_id_triggers_warning(self):
        shots = [
            {"id": "s1", "dramatic_function": "action", "lipsync": True},
        ]
        result = lint_continuity(shots)
        assert CODE_DIALOGUE_LEDGER_MISSING in result["codes"]

    def test_shot_no_dialogue_no_warning(self):
        shots = [
            {"id": "s1", "dramatic_function": "action"},
        ]
        result = lint_continuity(shots)
        assert CODE_DIALOGUE_LEDGER_MISSING not in result["codes"]

    def test_dsl_dialogue_triggers_warning(self):
        shots = [
            {"id": "s1", "dramatic_function": "action", "dsl": {"dialogue": "some line"}},
        ]
        result = lint_continuity(shots)
        assert CODE_DIALOGUE_LEDGER_MISSING in result["codes"]

    def test_dialogue_missing_is_warning_not_error(self):
        shots = [{"id": "s1", "dialogue": "test"}]
        result = lint_continuity(shots)
        for iss in result.get("issues", []):
            if iss["code"] == CODE_DIALOGUE_LEDGER_MISSING:
                assert iss["severity"] == "warning"
