"""media-queue add_job errors name inventory primaries."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from media_queue import (  # noqa: E402
    MediaQueue,
    QueueError,
    _inventory_weapon_tags,
    _queue_error,
)
from workflow_pack import WorkflowPackError  # noqa: E402


def test_inventory_weapon_tags_names_primaries() -> None:
    tags = _inventory_weapon_tags()
    assert "still=qwen-image-2512-quality" in tags
    assert "motion=minimax-h3-i2v-pilot" in tags
    assert "edit=qwen-image-edit-2511-local" in tags
    assert "tts=edge_tts_zh" in tags


def test_queue_error_appends_weapon_tags() -> None:
    err = _queue_error("pilot not approved")
    msg = str(err)
    assert msg.startswith("pilot not approved")
    assert "weapons:" in msg
    assert "motion=minimax-h3-i2v-pilot" in msg


def test_queue_error_does_not_double_tag() -> None:
    err = _queue_error("bulk preflight failed: pilot — weapons: still=x motion=y")
    assert str(err).count("weapons:") == 1


def test_queue_error_from_bulk_preflight_message_preserved() -> None:
    msg_in = (
        "bulk preflight failed: pilot — next: aifilm pilot pack "
        "— weapons: still=qwen-image-2512-quality motion=minimax-h3-i2v-pilot"
    )
    err = _queue_error(msg_in)
    assert "still=qwen-image-2512-quality" in str(err)
    assert str(err).count("weapons:") == 1


def test_bulk_preflight_failure_via_add_job_wraps_queue_error(tmp_path: Path) -> None:
    root = tmp_path / "film"
    root.mkdir()
    (root / "receipts").mkdir()
    (root / "film-spec.json").write_text(
        '{"title":"q","scenes":[{"shots":[{"id":"shot01","duration_sec":6,'
        '"dsl":{"subject":"a","action":"b","motion":"c"}}]}]}',
        encoding="utf-8",
    )
    (root / "manifest.json").write_text("{}", encoding="utf-8")
    prompt = root / "p.txt"
    prompt.write_text("walk", encoding="utf-8")
    img = root / "i.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    q = MediaQueue(root, budget_units=5)
    bulk_msg = (
        "bulk preflight failed: pilot — next: x "
        "— weapons: still=qwen-image-2512-quality motion=minimax-h3-i2v-pilot"
    )
    with mock.patch("media_queue.assert_pilot_allows_add", return_value={"ok": True}):
        with mock.patch("media_queue.assert_heat_allows_media", return_value={"ok": True}):
            with mock.patch(
                "media_queue.build_shot_contract",
                return_value={"ok": True, "errors": []},
            ):
                with mock.patch(
                    "media_queue.canonical_contract_required",
                    return_value=False,
                ):
                    with mock.patch(
                        "workflow_pack.assert_bulk_preflight",
                        side_effect=WorkflowPackError(bulk_msg),
                    ):
                        with pytest.raises(QueueError) as ei:
                            q.add_job(
                                shot_id="shot01",
                                operation="image_to_video",
                                prompt_file=prompt,
                                inputs=[img],
                                require_preflight=True,
                            )
    msg = str(ei.value)
    assert "still=qwen-image-2512-quality" in msg
    assert "motion=minimax-h3-i2v-pilot" in msg


def test_h3_cloud_block_message_includes_inventory_motion() -> None:
    """Unit: _queue_error path used by restricted/h3 block includes motion primary."""
    motion = "minimax-h3-i2v-pilot"
    err = _queue_error(
        f"shot 's1' is h3_primary film-wide local primary → local motion primary "
        f"{motion} (provider_lock=comfy-h3). "
        f"Use: aifilm h3 plan --root /f --shot-id s1 "
        f"&& aifilm h3 run --root /f --shot-id s1 "
        f"--register (inventory motion={motion})."
    )
    assert motion in str(err)
    assert "inventory motion=" in str(err)
