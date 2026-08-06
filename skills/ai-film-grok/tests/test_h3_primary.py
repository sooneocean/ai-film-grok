"""h3_primary profile: local 5090 MiniMax H3 is film-wide motion primary."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from film_spec import (  # noqa: E402
    default_i2v_provider,
    resolve_h3_config,
    resolve_i2v_profile,
)
from production_router import build_shot_intent  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_config_cache():
    import config_loader as cl

    cl._CONFIG = None
    cl._CONFIG_ENV_FINGERPRINT = None
    yield
    cl._CONFIG = None
    cl._CONFIG_ENV_FINGERPRINT = None


def test_h3_primary_profile_resolves() -> None:
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "h3_primary"}):
        assert resolve_i2v_profile() == "h3_primary"
        assert default_i2v_provider() == "comfy-h3"
        h3 = resolve_h3_config({})
        assert h3["enabled"] is True


def test_h3_primary_setup_hero_locks_comfy_h3() -> None:
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "h3_primary"}):
        intent = build_shot_intent(
            {
                "_i2v_profile": "h3_primary",
                "h3": {"enabled": True},
                "i2v_provider": "comfy-h3",
                "_i2v_provider_explicit": False,
            },
            {
                "id": "s_setup",
                "shot_role": "hero",
                "heat_phase": "setup",
            },
        )
    assert intent["content_class"] == "general"
    assert intent["recommended_provider"] == "comfy-h3"
    assert intent["provider_lock"] == "comfy-h3"
    assert intent["recommended_weapon"] == "minimax-h3-i2v-pilot"


def test_h3_primary_env_uses_local_t2v() -> None:
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "h3_primary"}):
        intent = build_shot_intent(
            {"_i2v_profile": "h3_primary", "h3": {"enabled": True}},
            {"id": "s_env", "shot_role": "env"},
        )
    assert intent["operation"] == "text_to_video"
    assert intent["identity_lock"] is False
    assert intent["recommended_provider"] == "comfy-h3"
    assert intent["provider_lock"] == "comfy-h3"
    assert intent["recommended_weapon"] == "minimax-h3-t2v-pilot"


def test_h3_primary_dialogue_local_not_frw() -> None:
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "h3_primary"}):
        intent = build_shot_intent(
            {"_i2v_profile": "h3_primary", "h3": {"enabled": True}},
            {
                "id": "s_dlg",
                "shot_role": "hero",
                "heat_phase": "setup",
                "screen_mode": "on_camera",
                "speaker_on_camera": True,
            },
        )
    assert intent["recommended_provider"] == "comfy-h3"
    assert intent["provider_lock"] == "comfy-h3"


def test_h3_primary_restricted_still_locks() -> None:
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "h3_primary"}):
        intent = build_shot_intent(
            {"_i2v_profile": "h3_primary", "h3": {"enabled": True}},
            {
                "id": "s_meat",
                "shot_role": "hero",
                "heat_phase": "act",
                "wardrobe_state": "bare",
            },
        )
    assert intent["content_class"] == "restricted_local"
    assert intent["provider_lock"] == "comfy-h3"


def test_hybrid_setup_still_grok() -> None:
    """Regression: hybrid_h3 must not force setup onto H3."""
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "hybrid_h3"}):
        intent = build_shot_intent(
            {"_i2v_profile": "hybrid_h3", "h3": {"enabled": True}},
            {"id": "s_setup", "shot_role": "hero", "heat_phase": "setup"},
        )
    assert intent["recommended_provider"] == "grok"
    assert intent["provider_lock"] is None




def test_h3_primary_preferred_and_priority() -> None:
    """Shipped preferred()/provider_priority() must lock free-local to comfy-h3."""
    from i2v_provider import preferred, provider_priority

    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "h3_primary"}):
        assert resolve_i2v_profile() == "h3_primary"
        assert default_i2v_provider() == "comfy-h3"
        assert provider_priority() == ("comfy-h3", "grok")
        active = preferred()
        assert active.name == "comfy-h3"


def test_grok_primary_preferred_still_grok() -> None:
    from i2v_provider import preferred, provider_priority

    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "grok_primary"}):
        assert resolve_i2v_profile() == "grok_primary"
        assert default_i2v_provider() == "grok"
        assert provider_priority() == ("grok",)
        assert preferred().name == "grok"

def test_media_queue_blocks_h3_primary_cloud(tmp_path: Path) -> None:
    from media_queue import MediaQueue, QueueError

    root = tmp_path / "film"
    root.mkdir()
    (root / "film-spec.json").write_text(
        """
{
  "title": "t",
  "aspect_ratio": "9:16",
  "_i2v_profile": "h3_primary",
  "h3": {"enabled": true},
  "i2v_provider": "comfy-h3",
  "shots": [
    {
      "id": "s01",
      "shot_role": "hero",
      "heat_phase": "setup",
      "nar": "hi",
      "duration_sec": 6,
      "dramatic_function": "hook",
      "dsl": {"action": "walks", "motion": "walk forward", "visible_change": "stands→walks"}
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    prompt = root / "prompt.txt"
    prompt.write_text(
        "dramatic_function: hook\nwant: enter room\n"
        "HIGH MOTION walk into frame, visible step change each second\n",
        encoding="utf-8",
    )
    still = root / "still.png"
    still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    q = MediaQueue(root)
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "h3_primary"}, clear=False):
        with pytest.raises(QueueError) as ei:
            q.add_job(
                shot_id="s01",
                operation="image_to_video",
                prompt_file=prompt,
                inputs=[still],
                generation_contract={"provider": "grok"},
                allow_without_pilot=True,
            )
    msg = str(ei.value)
    assert "h3_primary" in msg or "MiniMax H3" in msg
    assert "AIFILM_ALLOW_CLOUD_RESTRICTED" in msg


def test_dispatch_h3_primary_agent_do_ranks_local_h3(tmp_path: Path) -> None:
    """Live dispatch under free-local must not rank FRW/Grok bulk above H3."""
    import json

    from dispatch import build_dispatch

    root = tmp_path / "film"
    root.mkdir()
    (root / "brief.json").write_text('{"title":"t","theme":"x"}\n', encoding="utf-8")
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "t",
                "tts_backend": "edge",
                "_i2v_profile": "h3_primary",
                "i2v_provider": "comfy-h3",
                "h3": {"enabled": True},
                "shots": [
                    {
                        "id": "shot01",
                        "nar": "话说",
                        "dramatic_function": "hook",
                        "dsl": {
                            "action": "walks",
                            "motion": "walk forward",
                            "visible_change": "stands→walks",
                        },
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "h3_primary"}):
        packet = build_dispatch(
            root,
            gates={"spec": True, "style_locked": True},
            include_capability=False,
            write_receipt=False,
        )
    assert packet.get("craft_stage") in {"shots", "media", "selects", "agent"}
    routing = packet.get("routing") or {}
    assert routing.get("i2v_profile") == "h3_primary"
    i2v = str(routing.get("i2v") or "")
    assert "H3" in i2v or "h3" in i2v.lower()
    assert "兜底" in i2v or "fallback" in i2v.lower() or "escape" in i2v.lower()
    ref = str(routing.get("ref") or "")
    assert "hard-defaults" in ref or "weapon-lane" in ref
    # compat pointer ok; must not present grok doc as sole default truth without compat label
    assert "compat" in ref.lower() or "i2v-grok-primary" not in ref
    agent_blob = "\n".join(packet.get("agent_do") or [])
    assert "动 bulk FRW 或 image_to_video" not in agent_blob
    assert "bulk 前先 frw canary" not in agent_blob
    assert "5090" in agent_blob or "MiniMax H3" in agent_blob or "h3 plan" in agent_blob.lower()
    # pre-action chain must advertise local H3 primary
    pre_ids = [str(a.get("id") or "") for a in (packet.get("next_actions") or [])]
    assert "h3-primary-local" in pre_ids
    video = str((routing.get("grok_build") or {}).get("video") or "")
    assert "兜底" in video or "escape" in video.lower() or "h3" in video.lower()
    assert "SECOND: image_to_video after FRW" not in video


def test_dispatch_exception_default_profile_is_h3_primary() -> None:
    """Source-level: free-local exception default must not be ltx23_primary."""
    src = (Path(__file__).resolve().parents[1] / "scripts" / "spine" / "dispatch.py").read_text(
        encoding="utf-8"
    )
    assert 'i2v_profile = "h3_primary"' in src
    assert "the policy order remains FRW LTX" not in src

