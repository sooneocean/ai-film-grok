"""post_route — one caption_path per episode; no double-burn."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from post_route import (  # noqa: E402
    PostRouteError,
    apply_route_to_plate,
    assert_no_double_caption_layers,
    default_caption_path,
    normalize_caption_path,
    resolve_caption_path,
    write_post_route,
)


def test_normalize_aliases() -> None:
    assert normalize_caption_path("hf") == "master_hf"
    assert normalize_caption_path("ship") == "ship_hardburn"
    assert normalize_caption_path("hard_burn") == "ship_hardburn"
    with pytest.raises(PostRouteError):
        normalize_caption_path("magic")


def test_default_by_engine() -> None:
    assert default_caption_path(post_engine="hyperframes") == "master_hf"
    assert default_caption_path(post_engine="remotion") == "master_hf"
    assert default_caption_path(post_engine="ffmpeg") == "ship_hardburn"


def test_resolve_master_hf_plate_off(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text("{}", encoding="utf-8")
    route = resolve_caption_path(tmp_path, post_engine="hyperframes")
    assert route["caption_path"] == "master_hf"
    assert route["designed_caption_owner"] is True
    plate = apply_route_to_plate(route, subs_mode=None, plate_cards="auto")
    assert plate["subs"] == "off"
    assert plate["plate_cards"] == "blank"
    with pytest.raises(PostRouteError, match="double-burn|forbids plate"):
        apply_route_to_plate(route, subs_mode="burn", plate_cards="auto")


def test_resolve_ship_forces_burn(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"caption_path": "ship_hardburn"}),
        encoding="utf-8",
    )
    route = resolve_caption_path(tmp_path, post_engine="ffmpeg")
    assert route["caption_path"] == "ship_hardburn"
    plate = apply_route_to_plate(route, subs_mode="off", plate_cards="auto")
    assert plate["subs"] == "burn"
    receipt = write_post_route(tmp_path, {**route, "plate_subs": plate["subs"]})
    assert Path(receipt["path"]).is_file()


def test_cli_explicit_beats_spec(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"caption_path": "master_hf"}),
        encoding="utf-8",
    )
    route = resolve_caption_path(
        tmp_path, post_engine="hyperframes", explicit="ship_hardburn"
    )
    assert route["caption_path"] == "ship_hardburn"
    assert route["source"] == "cli"


def test_assert_no_double_layers() -> None:
    with pytest.raises(PostRouteError):
        assert_no_double_caption_layers(
            caption_path="master_hf",
            plate_subs="burn",
            caption_owner=None,
        )
    with pytest.raises(PostRouteError):
        assert_no_double_caption_layers(
            caption_path="ship_hardburn",
            plate_subs="burn",
            caption_owner="hyperframes",
        )
    assert_no_double_caption_layers(
        caption_path="ship_hardburn",
        plate_subs="burn",
        caption_owner="ffmpeg_plate",
    )
