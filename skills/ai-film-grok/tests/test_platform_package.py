"""Platform post-package contract for designed-post delivery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from export_composition import (  # noqa: E402
    build_end_roll_html,
    build_platform_ending_html,
    build_platform_opening_html,
)
from platform_package import (  # noqa: E402
    PlatformPackageError,
    assert_no_double_burn_override,
    load_platform_package,
)
from show_package import ShowPackageError, resolve_show_package  # noqa: E402


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_missing_post_package_is_a_safe_default(tmp_path: Path) -> None:
    result = load_platform_package(tmp_path)
    assert result["enabled"] is False
    assert result["caption_policy"]["owner"] == "hyperframes"


def test_valid_package_drives_caption_and_card_overrides(tmp_path: Path) -> None:
    _write(
        tmp_path / "post-package.json",
        {
            "schema_version": 1,
            "kind": "short-drama-platform-package",
            "package_id": "my-series-v1",
            "intro": {"mode": "short", "duration_sec": 1.1, "subtitle": "EP 03"},
            "outro": {
                "mode": "hook",
                "duration_sec": 2.2,
                "cta": "下一集更刺激",
                "next_episode": "第 4 集：反转",
            },
            "captions": {"theme": "platform-drama", "max_chars": 10, "languages": ["zh", "ja"]},
            "safe_area": {"top_pct": 10, "bottom_pct": 16},
        },
    )
    result = load_platform_package(tmp_path)
    assert result["package_id"] == "my-series-v1"
    assert result["caption_policy"]["max_chars"] == 10
    assert result["timing"] == {"title_duration_sec": 1.1, "end_duration_sec": 2.2}
    assert result["overrides"]["title_sequence"]["subtitle"] == "EP 03"


def test_platform_outro_copy_is_escaped() -> None:
    rendered = build_end_roll_html(
        {"film_timeline": {"output_duration": 20}},
        {"mode": "hook", "cta": "追更 <现在>", "next_episode": "第 4 集"},
        "minimal",
        {},
        {"cast": [], "crew": [], "shots": []},
    )
    assert 'class="er-next">第 4 集' in rendered
    assert 'class="er-cta">追更 &lt;现在&gt;' in rendered


def test_show_package_prefers_inline_and_escapes_platform_cards(tmp_path: Path) -> None:
    sidecar = {
        "id": "sidecar-v1",
        "version": "1.0.0",
        "brand": {"label": "AI FILM SPACE", "accent": "#F5C2D5"},
        "opening": {"duration_sec": 1.2, "series_title": "午夜祕密", "episode": "EP.01"},
        "captions": {"identity": "platform-drama", "safe_bottom_px": 240},
        "ending": {
            "duration_sec": 1.8,
            "cta": "下一集，敬请期待",
            "next_episode_hook": "门后的声音。",
        },
    }
    _write(tmp_path / "show-package.json", sidecar)
    inline = {**sidecar, "id": "inline-v1"}

    resolved = resolve_show_package(tmp_path, {"show_package": inline})

    assert resolved is not None
    assert resolved["id"] == "inline-v1"
    assert resolved["captions"]["safe_bottom_px"] == 240
    resolved["opening"]["series_title"] = "<午夜>"
    resolved["ending"]["cta"] = "追更 <现在>"
    opening = build_platform_opening_html({}, resolved, title_dur=1.2)
    ending = build_platform_ending_html(
        {"film_timeline": {"output_duration": 20}}, resolved, end_dur=1.8
    )
    assert "&lt;午夜&gt;" in opening
    assert "&lt;现在&gt;" in ending
    assert 'data-start="18.200"' in ending


def test_invalid_show_package_color_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ShowPackageError, match="accent"):
        resolve_show_package(
            tmp_path,
            {
                "show_package": {
                    "id": "invalid",
                    "version": "1.0.0",
                    "brand": {"accent": "pink"},
                }
            },
        )


def test_none_modes_are_preserved_as_explicit_overrides(tmp_path: Path) -> None:
    _write(
        tmp_path / "post-package.json",
        {
            "schema_version": 1,
            "kind": "short-drama-platform-package",
            "package_id": "no-cards",
            "intro": {"mode": "none"},
            "outro": {"mode": "none"},
        },
    )
    result = load_platform_package(tmp_path)
    assert result["overrides"]["title_sequence"] == {"mode": "none"}
    assert result["overrides"]["end_roll"] == {"mode": "none"}


def test_packaged_episode_rejects_double_burn_override(tmp_path: Path) -> None:
    _write(
        tmp_path / "post-package.json",
        {"schema_version": 1, "package_id": "platform", "intro": {"mode": "short"}},
    )
    with pytest.raises(PlatformPackageError, match="forbids --allow-burned-underlay"):
        assert_no_double_burn_override(tmp_path, allow_burned_underlay=True)


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"schema_version": 2}, "schema_version"),
        ({"schema_version": 1, "kind": "wrong"}, "kind"),
        ({"schema_version": 1, "package_id": "test", "captions": {"max_chars": 5}}, "max_chars"),
        ({"schema_version": 1, "package_id": "test", "safe_area": {"bottom_pct": 50}}, "safe_area"),
        (
            {"schema_version": 1, "package_id": "test", "intro": {"duration_sec": 0.2}},
            "intro.duration_sec",
        ),
        (
            {"schema_version": 1, "package_id": "test", "captions": {"theme": "premium"}},
            "captions.theme",
        ),
        ({"schema_version": 1, "unknown": True}, "unknown keys"),
    ],
)
def test_invalid_package_fails_closed(
    tmp_path: Path, payload: dict[str, object], message: str
) -> None:
    _write(tmp_path / "post-package.json", payload)
    with pytest.raises(PlatformPackageError, match=message):
        load_platform_package(tmp_path)
