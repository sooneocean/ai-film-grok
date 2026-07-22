#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from drama_graph import (  # noqa: E402
    build_jobs_summary,
    derive_graph,
    graph_path,
    graph_status,
    validate_graph,
)


def _mini_spec() -> dict:
    return {
        "title": "test-rain",
        "aspect_ratio": "9:16",
        "vo_mode": "storyteller",
        "director_intent": {
            "logline": "A rainy night hook for vertical drama test.",
            "tone": "test",
            "emotional_arc": ["hook", "rise", "end"],
            "theme": "boundary",
        },
        "scenes": [
            {
                "title": "Cab",
                "summary": "ride",
                "shots": [
                    {
                        "id": "shot01",
                        "nar": "雨很急。",
                        "dramatic_function": "hook",
                        "duration_sec": 4,
                        "dsl": {
                            "subject": "driver",
                            "action": "opens door",
                            "motion": "push-in",
                            "camera_axis": "dolly_in",
                            "chain_mode": "continue",
                        },
                    },
                    {
                        "id": "shot02",
                        "nar": "她看向后座。",
                        "dramatic_function": "approach",
                        "duration_sec": 5,
                        "dsl": {
                            "subject": "driver face",
                            "action": "looks back",
                            "chain_mode": "continue",
                        },
                    },
                    {
                        "id": "shot03",
                        "nar": "热气扑来。",
                        "dramatic_function": "sensory",
                        "duration_sec": 6,
                        "shot_role": "hero",
                        "dsl": {"subject": "steam", "action": "breath", "chain_mode": "cut"},
                    },
                ],
            }
        ],
    }


class DramaGraphTests(unittest.TestCase):
    def test_derive_validate_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                json.dumps(_mini_spec(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "style-bible.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "characters": {
                            "hero": {
                                "identity": "wet driver",
                                "default_wardrobe": "raincoat",
                                "cast_master": "canonical/cast/hero.png",
                            }
                        },
                        "locations": {"cab": "taxi interior rain"},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            # fake assets
            (root / "keyframes").mkdir()
            (root / "keyframes" / "shot01.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            (root / "prompts").mkdir()
            (root / "prompts" / "shot01.txt").write_text("p1\n", encoding="utf-8")

            graph = derive_graph(root, write=True)
            self.assertTrue(graph_path(root).is_file())
            self.assertEqual(graph.get("schema_version"), 2)
            self.assertEqual(len(graph.get("episodes") or []), 1)
            ep = graph["episodes"][0]
            self.assertGreaterEqual(len(ep.get("scenes") or []), 1)
            beats = ep["scenes"][0]["beats"]
            self.assertGreaterEqual(len(beats), 2)
            shots = [sh for bt in beats for sh in bt["shots"]]
            self.assertEqual({s["id"] for s in shots}, {"shot01", "shot02", "shot03"})
            s1 = next(s for s in shots if s["id"] == "shot01")
            self.assertTrue(s1["panels"])
            self.assertTrue(s1["assetHints"]["hasKeyframe"])
            self.assertEqual(len(graph.get("characters") or []), 1)

            v = validate_graph(graph)
            self.assertTrue(v.get("ok"), v)
            self.assertEqual(v.get("shot_count"), 3)

            st = graph_status(root, auto_derive=False)
            self.assertTrue(st.get("ok"))
            self.assertEqual(st["counts"]["shots"], 3)
            self.assertIn("sh=3", st.get("line") or "")

            jobs = build_jobs_summary(root, craft_stage="shots")
            self.assertGreater(jobs.get("total") or 0, 3)
            self.assertIn("ready_count", jobs)
            ids = {j["id"] for j in jobs["jobs"]}
            self.assertIn("job_kf_shot01", ids)
            # shot01 has keyframe → done
            j_kf = next(j for j in jobs["jobs"] if j["id"] == "job_kf_shot01")
            self.assertEqual(j_kf["status"], "done")
            j_kf2 = next(j for j in jobs["jobs"] if j["id"] == "job_kf_shot02")
            self.assertEqual(j_kf2["status"], "ready")

    def test_validate_missing_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = validate_graph(root=root)
            self.assertFalse(report.get("ok"))
            self.assertTrue(report.get("errors"))


if __name__ == "__main__":
    unittest.main()
