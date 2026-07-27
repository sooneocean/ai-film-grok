from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_project_blueprint import validate


def _blueprint(reference_path: str, reference_sha256: str) -> dict:
    return {
        "schema_version": 1,
        "kind": "ai-film-project-blueprint",
        "project": {
            "project_id": "project_1",
            "title": "Project",
            "format": "vertical_9_16",
            "status": "staged",
        },
        "story": {
            "source": "story.md",
            "source_sha256": "0" * 64,
            "status": "staged",
        },
        "characters": [
            {
                "character_id": "lead_1",
                "name": "Lead",
                "reference_views": [
                    {
                        "view_id": "front",
                        "role": "front",
                        "path": reference_path,
                        "sha256": reference_sha256,
                        "review_status": "needs_review",
                    }
                ],
                "canonical_master": {
                    "view_id": "front",
                    "path": reference_path,
                    "sha256": reference_sha256,
                    "review_status": "needs_review",
                },
                "status": "staged",
            }
        ],
        "style": {
            "medium": "anime",
            "palette": "warm",
            "lighting": "soft",
            "rendering": "cel",
            "signature_block": "x" * 48,
            "negative_constraints": ["identity drift"],
            "status": "staged",
        },
        "continuity": {
            "stable_id_policy": "stable",
            "state_policy": "explicit",
            "continue_policy": "hash-bound",
        },
        "episodes": [],
        "handoff": {
            "project_lock_fields": ["project_id"],
            "episode_fields": ["episode_id"],
            "approval_required": ["canonical_master"],
        },
    }


def test_validate_accepts_a_hash_bound_blueprint(tmp_path: Path) -> None:
    reference = tmp_path / "references" / "lead.png"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"lead-reference")
    digest = hashlib.sha256(reference.read_bytes()).hexdigest()
    blueprint = tmp_path / "project-blueprint.json"
    import json

    blueprint.write_text(
        json.dumps(_blueprint("references/lead.png", digest)), encoding="utf-8"
    )

    report = validate(tmp_path, blueprint)

    assert report["ok"] is True
    assert report["character_count"] == 1


def test_validate_rejects_reference_path_escape(tmp_path: Path) -> None:
    import json

    blueprint = tmp_path / "project-blueprint.json"
    blueprint.write_text(
        json.dumps(_blueprint("../outside.png", "0" * 64)), encoding="utf-8"
    )

    report = validate(tmp_path, blueprint)

    assert report["ok"] is False
    assert any("escapes project root" in error for error in report["errors"])
