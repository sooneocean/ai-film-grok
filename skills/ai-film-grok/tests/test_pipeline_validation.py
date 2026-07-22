from __future__ import annotations

import argparse
import contextlib
import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aifilm_grok  # noqa: E402
import render_final  # noqa: E402


def valid_spec() -> dict[str, object]:
    return {
        "title": "测试影片",
        "vo_mode": "storyteller",
        "director_intent": {
            "logline": "夜里车门打开，说书人把你拉进一场靠近。",
            "tone": "测试·压抑期待",
            "emotional_arc": ["登场", "靠近", "余韵"],
        },
        "scenes": [
            {
                "title": "Scene 1",
                "shots": [
                    {
                        "id": "shot01",
                        "title": "开场",
                        "dramatic_function": "hook",
                        "nar": "夜里，车门缓缓打开。",
                        "dsl": {
                            "subject": "an adult woman",
                            "action": "opens a door",
                            "motion": "door open, blink, idle not speaking",
                        },
                    }
                ],
            }
        ],
    }


class PipelineValidationTests(unittest.TestCase):
    def init_root(self, root: Path) -> None:
        with contextlib.redirect_stdout(StringIO()):
            rc = aifilm_grok.main(
                ["init", "--theme", "test", "--title", "test", "--root", str(root)]
            )
        self.assertEqual(rc, 0)

    def write_spec(self, root: Path, value: dict[str, object]) -> tuple[int, dict[str, object]]:
        source = root.parent / "incoming-spec.json"
        source.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        output = StringIO()
        with contextlib.redirect_stdout(output):
            rc = aifilm_grok.main(["write-spec", "--root", str(root), "--spec", str(source)])
        return rc, json.loads(output.getvalue())

    @pytest.mark.slow
    def test_write_spec_requires_vo_mode_narration_and_unique_safe_ids(self) -> None:
        mutations = []

        missing_mode = valid_spec()
        missing_mode.pop("vo_mode")
        mutations.append(("missing mode", missing_mode))

        missing_nar = valid_spec()
        del missing_nar["scenes"][0]["shots"][0]["nar"]  # type: ignore[index]
        mutations.append(("missing narration", missing_nar))

        duplicate = valid_spec()
        duplicate["scenes"][0]["shots"].append(  # type: ignore[index]
            {
                "id": "shot01",
                "title": "重复",
                "dramatic_function": "bridge",
                "nar": "重复镜头。",
                "dsl": {"subject": "same person", "motion": "soft look, idle not speaking"},
            }
        )
        mutations.append(("duplicate id", duplicate))

        traversal = valid_spec()
        traversal["scenes"][0]["shots"][0]["id"] = "../escape"  # type: ignore[index]
        mutations.append(("unsafe id", traversal))

        unknown_tts = valid_spec()
        unknown_tts["tts_backend"] = "mystery"
        mutations.append(("unknown tts backend", unknown_tts))

        missing_intent = valid_spec()
        missing_intent.pop("director_intent")
        mutations.append(("missing director_intent", missing_intent))

        missing_fn = valid_spec()
        del missing_fn["scenes"][0]["shots"][0]["dramatic_function"]  # type: ignore[index]
        mutations.append(("missing dramatic_function", missing_fn))

        for label, value in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "film"
                self.init_root(root)
                rc, result = self.write_spec(root, value)
                self.assertEqual(rc, 2)
                self.assertFalse(result["ok"])

    @pytest.mark.slow
    def test_write_spec_assigns_safe_ids_and_writes_valid_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            self.init_root(root)
            spec = valid_spec()
            del spec["scenes"][0]["shots"][0]["id"]  # type: ignore[index]
            rc, result = self.write_spec(root, spec)
            self.assertEqual(rc, 0, result)
            saved = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["scenes"][0]["shots"][0]["id"], "shot01")

    @pytest.mark.slow
    def test_register_media_rejects_unsafe_shot_id_without_writing_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "film"
            self.init_root(root)
            source = base / "source.jpg"
            source.write_bytes(b"image")
            output = StringIO()
            with contextlib.redirect_stdout(output):
                rc = aifilm_grok.main(
                    [
                        "register-still",
                        "--root",
                        str(root),
                        "--shot-id",
                        "../escape",
                        "--source",
                        str(source),
                    ]
                )
            self.assertEqual(rc, 2)
            self.assertFalse((root / "escape.jpg").exists())
            self.assertFalse((base / "escape.jpg").exists())

    @pytest.mark.slow
    def test_assemble_and_final_reject_escaping_output_name_before_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "film"
            self.init_root(root)
            for command in ("assemble", "final"):
                with self.subTest(command=command):
                    output = StringIO()
                    with contextlib.redirect_stdout(output):
                        rc = aifilm_grok.main(
                            [command, "--root", str(root), "--out-name", "../escape.mp4"]
                        )
                    self.assertEqual(rc, 2)
                    self.assertFalse((root.parent / "escape.mp4").exists())

    @pytest.mark.slow
    def test_assemble_rejects_symlinked_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp) / "film"
            self.init_root(root)
            (root / "out").rmdir()
            (root / "out").symlink_to(Path(outside), target_is_directory=True)
            output = StringIO()
            with contextlib.redirect_stdout(output):
                rc = aifilm_grok.main(["assemble", "--root", str(root)])
            self.assertEqual(rc, 2)
            result = json.loads(output.getvalue())
            self.assertIn("symbolic-link", result["error"])

    @pytest.mark.slow
    def test_render_final_rejects_escaping_output_name_before_reading_root(self) -> None:
        args = argparse.Namespace(root="/definitely/missing", out_name="../escape.mp4")
        with self.assertRaisesRegex(render_final.RenderError, "single relative path component"):
            render_final.render_final(args)

    @pytest.mark.slow
    def test_desktop_export_requires_force_when_destination_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            desktop = home / "Desktop"
            destination = desktop / "现有项目"
            destination.mkdir(parents=True)
            root = Path(tmp) / "film"
            self.init_root(root)
            args = argparse.Namespace(root=str(root), name="现有项目", force=False)
            with mock.patch.object(aifilm_grok.Path, "home", return_value=home):
                with self.assertRaises(aifilm_grok.FilmError):
                    aifilm_grok.cmd_export_desktop(args)


if __name__ == "__main__":
    unittest.main()
