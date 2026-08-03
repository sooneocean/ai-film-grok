"""Wave A–C throughput helpers: closeout / pilot pack / variety / lease / tunnel."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workflow_pack import (  # noqa: E402
    bulk_preflight,
    closeout_run,
    gpu_lease_acquire,
    gpu_lease_release,
    gpu_lease_status,
    pilot_pack,
    queue_progress_honest,
    select_shortlist,
    tunnel_probe,
    variety_precheck,
)


def _write(root: Path, rel: str, data: dict | str | bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    elif isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(str(data), encoding="utf-8")
    return path


def _meat_spec() -> dict:
    poses = ["cowgirl", "missionary", "from_behind", "side", "standing"]
    sizes = ["ms", "cu", "insert", "insert", "cu"]
    cams = ["push-in", "orbit", "pull-back", "tilt-up", "handheld"]
    shots = []
    for i in range(5):
        shots.append(
            {
                "id": f"shot{i + 1:02d}",
                "heat_phase": "act" if i < 4 else "climax",
                "sex_pose": poses[i],
                "shot_size": sizes[i],
                "duration_sec": 5.0,
                "coitus_beat": "undress" if i == 0 else ("union" if i == 1 else "rhythm"),
                "dsl": {
                    "motion": f"{cams[i]} slow body thrust, idle not speaking",
                    "camera_axis": cams[i],
                    "action": poses[i],
                    "camera": {"shot_size": sizes[i], "move": cams[i]},
                },
            }
        )
    return {
        "title": "variety-test",
        "heat_scale": "max",
        "scenes": [{"shots": shots}],
    }


class CloseoutDelegateTests(unittest.TestCase):
    def test_missing_plate_stops_with_final_cmd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "film-spec.json", {"title": "x", "scenes": []})
            _write(root, "manifest.json", {"gates": {}, "outputs": {}})
            report = closeout_run(root, write=True, run_post_audit=False)
            self.assertFalse(report["ok"])
            self.assertEqual(report["blocked_by"], "plate_or_final")
            self.assertIn("final", report["next_cmd"] or "")
            self.assertTrue((root / "receipts" / "closeout.json").is_file())

    def test_plate_without_review_points_final_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "film-spec.json", {"title": "x", "heat_scale": "soft", "scenes": []})
            _write(root, "out/film_final.mp4", b"\x00\x00fake")
            _write(
                root,
                "manifest.json",
                {"gates": {"final_complete": False}, "outputs": {}},
            )
            with mock.patch(
                "heat_check.heat_agent_status",
                return_value={"active": False, "ok": True, "final_ok": True},
            ):
                report = closeout_run(root, write=True, run_post_audit=False)
            self.assertFalse(report["ok"])
            self.assertEqual(report["blocked_by"], "final_complete")
            self.assertIn("review-final", report["next_cmd"] or "")


class PilotPackDelegateTests(unittest.TestCase):
    def test_pack_not_go_without_media(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root,
                "film-spec.json",
                {
                    "title": "p",
                    "vo_mode": "storyteller",
                    "director_intent": {
                        "logline": "测试 pilot pack 的完整句子。",
                        "tone": "t",
                        "emotional_arc": ["a", "b", "c"],
                    },
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "shot01",
                                    "dramatic_function": "hook",
                                    "nar": "一。",
                                    "duration_sec": 6,
                                    "dsl": {
                                        "subject": "a",
                                        "action": "b",
                                        "motion": "soft blink, idle not speaking",
                                    },
                                },
                                {
                                    "id": "shot02",
                                    "dramatic_function": "reaction",
                                    "nar": "二。",
                                    "duration_sec": 6,
                                    "dsl": {
                                        "subject": "a",
                                        "action": "b",
                                        "motion": "soft blink, idle not speaking",
                                    },
                                },
                                {
                                    "id": "shot03",
                                    "dramatic_function": "action",
                                    "nar": "三。",
                                    "duration_sec": 6,
                                    "dsl": {
                                        "subject": "a",
                                        "action": "b",
                                        "motion": "soft blink, idle not speaking",
                                    },
                                },
                            ]
                        }
                    ],
                },
            )
            _write(root, "manifest.json", {"stills": {}, "clips": {}})
            pack = pilot_pack(root, write=True)
            self.assertFalse(pack.get("go_ready") or pack.get("ok"))
            blockers = (pack.get("pilot_go") or {}).get("blockers") or pack.get("blockers") or []
            self.assertTrue(any("MEDIA" in str(b) for b in blockers))
            self.assertTrue((root / "receipts" / "pilot-go.json").is_file())


class VarietyTests(unittest.TestCase):
    def test_good_variety_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "film-spec.json", _meat_spec())
            report = variety_precheck(root, write=True)
            self.assertTrue(report["ok"], report.get("issues"))
            self.assertGreaterEqual(report["unique_pose_count"], 4)

    def test_adjacent_motion_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = _meat_spec()
            for sh in spec["scenes"][0]["shots"]:
                sh["dsl"]["motion"] = "same push-in thrust, idle not speaking"
                sh["dsl"]["camera_axis"] = "push-in"
                sh["dsl"]["camera"]["move"] = "push-in"
            _write(root, "film-spec.json", spec)
            report = variety_precheck(root, write=True)
            self.assertFalse(report["ok"])
            codes = {i["code"] for i in report["issues"]}
            self.assertIn("ADJACENT_MOTION_COLLISION", codes)


class BulkPreflightTests(unittest.TestCase):
    def test_fails_without_pilot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "film-spec.json", {"title": "x", "heat_scale": "soft", "scenes": []})
            _write(root, "manifest.json", {"stills": {}, "clips": {}})
            report = bulk_preflight(
                root, write=True, probe_tunnel=False, check_lease=False
            )
            self.assertFalse(report["ok"])
            self.assertIn("pilot", report["failed"])


class GpuLeaseTests(unittest.TestCase):
    def test_acquire_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lease_dir = Path(tmp) / "lease-home"
            lease_dir.mkdir()
            with mock.patch.dict(os.environ, {"AIFILM_GPU_LEASE_DIR": str(lease_dir)}):
                st = gpu_lease_status(root)
                self.assertTrue(st["free"])
                acq = gpu_lease_acquire(root)
                self.assertTrue(acq["ok"])
                st2 = gpu_lease_status(root)
                self.assertTrue(st2["owned_by_self"])
                other = Path(tmp) / "other"
                other.mkdir()
                st3 = gpu_lease_status(other)
                self.assertFalse(st3["free"])
                self.assertEqual(st3["code"], "LEASE_HELD")
                rel = gpu_lease_release(root)
                self.assertTrue(rel["released"])
                self.assertTrue(gpu_lease_status(other)["free"])


class TunnelTests(unittest.TestCase):
    def test_unauthorized_is_wrong_port(self) -> None:
        class FakeResp:
            status = 401

            def read(self, n: int = -1) -> bytes:
                return b'{"detail":"unauthorized"}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=3.0):  # noqa: ARG001
            import urllib.error

            raise urllib.error.HTTPError(
                req.full_url if hasattr(req, "full_url") else "http://x",
                401,
                "Unauthorized",
                hdrs=None,  # type: ignore[arg-type]
                fp=__import__("io").BytesIO(b'{"detail":"unauthorized"}'),
            )

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            report = tunnel_probe(port=18188)
        self.assertFalse(report["ok"])
        self.assertEqual(report["code"], "TUNNEL_WRONG_PORT")

    def test_comfy_json_ok(self) -> None:
        body = json.dumps({"system": {"comfyui_version": "0.1"}, "devices": []}).encode()

        class FakeResp:
            status = 200

            def read(self, n: int = -1) -> bytes:
                return body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with mock.patch("urllib.request.urlopen", return_value=FakeResp()):
            report = tunnel_probe(port=18188)
        self.assertTrue(report["ok"])


class ProgressAndSelectTests(unittest.TestCase):
    def test_progress_counts_nonzero_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "takes/shot01/a.mp4", b"\x00\x01" * 50)
            _write(root, "takes/shot01/empty.mp4", b"")
            rep = queue_progress_honest(root)
            self.assertEqual(rep["takes_files"], 1)
            self.assertFalse(rep["interrupt_is_progress"])

    def test_select_shortlist_prefers_largest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "takes/shot01/low.mp4", b"\x00" * 50)
            _write(root, "takes/shot01/high.mp4", b"\x00" * 200_000)
            rep = select_shortlist(root, write=True)
            self.assertEqual(len(rep["shots"]), 1)
            pref = rep["shots"][0]["preferred"]
            self.assertIn("high.mp4", pref["path"])


class DispatchCloseoutHookTests(unittest.TestCase):
    def test_action_skill_maps_closeout(self) -> None:
        from dispatch import _ACTION_SKILLS

        self.assertEqual(_ACTION_SKILLS.get("closeout-run"), "projection.verify")


if __name__ == "__main__":
    unittest.main()
