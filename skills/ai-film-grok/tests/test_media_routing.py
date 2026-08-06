from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from media.media_routing import (  # noqa: E402
    load_cast_stability,
    media_routing_report,
    resolve_shot_medium,
    route_character_medium,
)

pytestmark = pytest.mark.hotpath


class RouteCharacterMediumTests(unittest.TestCase):
    def test_unstable_downgrades_photoreal_to_anime(self):
        self.assertEqual(
            route_character_medium("photoreal", "unstable"),
            ("anime", "unstable_cast_downgrade_to_anime"),
        )

    def test_unstable_downgrades_semi_real(self):
        self.assertEqual(
            route_character_medium("semi_real", "unstable"),
            ("anime", "unstable_cast_downgrade_to_anime"),
        )

    def test_stable_keeps_photoreal(self):
        self.assertEqual(
            route_character_medium("photoreal", "stable"),
            ("photoreal", "film_medium_default"),
        )

    def test_unstable_keeps_anime_unchanged(self):
        # Already anime: unstable does not flip it to something else.
        self.assertEqual(
            route_character_medium("anime", "unstable"),
            ("anime", "film_medium_default"),
        )

    def test_unknown_medium_stable_default(self):
        self.assertEqual(
            route_character_medium("manhua", "stable"),
            ("manhua", "film_medium_default"),
        )

    def test_unknown_medium_unstable_not_photoreal_no_downgrade(self):
        self.assertEqual(
            route_character_medium("manhua", "unstable"),
            ("manhua", "film_medium_default"),
        )

    def test_empty_inputs_default(self):
        self.assertEqual(
            route_character_medium("", ""),
            ("", "film_medium_default"),
        )


def _make_root(spec: dict, *, style_bible: dict | None = None) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    if style_bible is not None:
        (root / "style-bible.json").write_text(json.dumps(style_bible), encoding="utf-8")
    return root


class LoadCastStabilityTests(unittest.TestCase):
    def test_defaults_all_stable_from_cast_ids(self):
        root = _make_root({"cast_ids": ["hero", "rival"]})
        self.assertEqual(load_cast_stability(root), {"hero": "stable", "rival": "stable"})

    def test_override_marks_unstable(self):
        root = _make_root(
            {
                "cast_ids": ["hero", "rival"],
                "cast_stability": {"rival": "unstable"},
            }
        )
        self.assertEqual(load_cast_stability(root), {"hero": "stable", "rival": "unstable"})

    def test_override_normalizes_case(self):
        root = _make_root({"cast_stability": {"hero": "UNSTABLE"}})
        self.assertEqual(load_cast_stability(root), {"hero": "unstable"})

    def test_missing_spec_returns_empty(self):
        root = Path(tempfile.mkdtemp())  # no film-spec.json
        self.assertEqual(load_cast_stability(root), {})


class ResolveAndReportTests(unittest.TestCase):
    def test_resolve_shot_downgrades_unstable_hero(self):
        root = _make_root(
            {"cast_ids": ["hero"], "cast_stability": {"hero": "unstable"}},
            style_bible={"style_fingerprint": {"medium_key": "photoreal"}},
        )
        eff, reason = resolve_shot_medium(root, {"character": "hero"}, {})
        self.assertEqual((eff, reason), ("anime", "unstable_cast_downgrade_to_anime"))

    def test_resolve_shot_stable_stays_photoreal(self):
        root = _make_root(
            {"cast_ids": ["hero"]},
            style_bible={"style_fingerprint": {"medium_key": "photoreal"}},
        )
        eff, _ = resolve_shot_medium(root, {"character": "hero"}, {})
        self.assertEqual(eff, "photoreal")

    def test_report_counts_routed(self):
        root = _make_root(
            {
                "cast_ids": ["hero", "rival"],
                "cast_stability": {"rival": "unstable"},
            },
            style_bible={"style_fingerprint": {"medium_key": "photoreal"}},
        )
        rep = media_routing_report(root)
        self.assertEqual(rep["film_medium"], "photoreal")
        self.assertEqual(rep["count"], 2)
        self.assertEqual(rep["routed"], 1)
        rival = next(r for r in rep["rows"] if r["character"] == "rival")
        self.assertEqual(rival["effective_medium"], "anime")

    def test_report_default_medium_without_style_bible(self):
        root = _make_root({"cast_ids": ["hero"], "cast_stability": {"hero": "unstable"}})
        rep = media_routing_report(root)
        self.assertEqual(rep["film_medium"], "photoreal")
        self.assertEqual(rep["routed"], 1)


if __name__ == "__main__":
    unittest.main()
