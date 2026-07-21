from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from security_policy import (  # noqa: E402
    SecurityPolicyError,
    expand_argv,
    parse_argv_json,
    safe_output_path,
    safe_subdirectory,
    safe_workspace_directory,
    safe_existing_file,
    minimal_subprocess_env,
    reject_symlinks,
    validate_identifier,
)
import aifilm_grok  # noqa: E402
import media_qa  # noqa: E402
import render_final  # noqa: E402


class IdentifierPolicyTests(unittest.TestCase):
    def test_accepts_stable_ascii_shot_ids(self) -> None:
        self.assertEqual(validate_identifier("shot_01-A", field="shot id"), "shot_01-A")

    def test_rejects_traversal_absolute_and_control_characters(self) -> None:
        for value in ("../escape", "/tmp/escape", "shot/01", "shot\\01", "shot\n01", ".."):
            with self.subTest(value=value):
                with self.assertRaises(SecurityPolicyError):
                    validate_identifier(value, field="shot id")


class PathPolicyTests(unittest.TestCase):
    def test_recursive_symlink_scan_rejects_nested_export_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            nested = root / "成片"
            nested.mkdir()
            (nested / "项目状态").symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaises(SecurityPolicyError):
                reject_symlinks(root, field="Desktop export")

    def test_workspace_directory_rejects_symlink_to_outside(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            (root / "out").symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaises(SecurityPolicyError):
                safe_workspace_directory(root, "out")

    def test_existing_file_must_resolve_inside_expected_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            clips = root / "clips"
            clips.mkdir()
            inside = clips / "shot01.mp4"
            inside.write_bytes(b"video")
            external = Path(outside) / "secret.mp4"
            external.write_bytes(b"secret")
            self.assertEqual(safe_existing_file(clips, inside), inside.resolve())
            for candidate in (external, clips / "../outside.mp4"):
                with self.subTest(candidate=candidate):
                    with self.assertRaises(SecurityPolicyError):
                        safe_existing_file(clips, candidate)

    def test_output_is_contained_and_has_expected_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = safe_output_path(root, "film-final_01.mp4", suffixes={".mp4"})
            self.assertEqual(path, root.resolve() / "film-final_01.mp4")

    def test_output_rejects_escape_absolute_wrong_suffix_and_nested_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for value in ("../escape.mp4", "/tmp/escape.mp4", "nested/film.mp4", "film.mov", ".mp4"):
                with self.subTest(value=value):
                    with self.assertRaises(SecurityPolicyError):
                        safe_output_path(root, value, suffixes={".mp4"})

    def test_existing_symlink_cannot_redirect_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            (root / "film.mp4").symlink_to(Path(outside) / "film.mp4")
            with self.assertRaises(SecurityPolicyError):
                safe_output_path(root, "film.mp4", suffixes={".mp4"})

    def test_desktop_subdirectory_accepts_chinese_but_rejects_path_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            desktop = Path(tmp)
            self.assertEqual(safe_subdirectory(desktop, "夜班车 成片"), desktop.resolve() / "夜班车 成片")
            for value in (".", "..", "../escape", "/tmp/escape", "a/b", "a\\b", "name\0bad"):
                with self.subTest(value=value):
                    with self.assertRaises(SecurityPolicyError):
                        safe_subdirectory(desktop, value)


class ArgvPolicyTests(unittest.TestCase):
    def test_minimal_subprocess_environment_drops_secrets_agents_and_proxies(self) -> None:
        source = {
            "PATH": "/usr/bin",
            "HOME": "/tmp/home",
            "LANG": "en_US.UTF-8",
            "FISH_API_KEY": "secret",
            "MINIMAX_API_KEY": "secret",
            "SSH_AUTH_SOCK": "/tmp/agent.sock",
            "HTTPS_PROXY": "http://proxy",
        }
        env = minimal_subprocess_env(source)
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertNotIn("FISH_API_KEY", env)
        self.assertNotIn("MINIMAX_API_KEY", env)
        self.assertNotIn("SSH_AUTH_SOCK", env)
        self.assertNotIn("HTTPS_PROXY", env)

    def test_pipeline_process_wrappers_strip_parent_secrets(self) -> None:
        parent = {
            "PATH": "/usr/bin",
            "HOME": "/tmp/home",
            "FISH_API_KEY": "secret",
            "SSH_AUTH_SOCK": "/tmp/agent.sock",
            "HTTPS_PROXY": "http://proxy",
        }
        completed = subprocess.CompletedProcess(["ffmpeg"], 0, stdout="", stderr="")
        wrappers = (aifilm_grok.run, media_qa._run, render_final.run)
        with mock.patch.dict(os.environ, parent, clear=True):
            for wrapper in wrappers:
                with self.subTest(wrapper=wrapper.__module__):
                    with mock.patch.object(wrapper.__globals__["subprocess"], "run", return_value=completed) as mocked:
                        wrapper(["ffmpeg"])
                    child_env = mocked.call_args.kwargs["env"]
                    self.assertEqual(child_env["PATH"], "/usr/bin")
                    self.assertNotIn("FISH_API_KEY", child_env)
                    self.assertNotIn("SSH_AUTH_SOCK", child_env)
                    self.assertNotIn("HTTPS_PROXY", child_env)

    def test_json_array_preserves_each_argument(self) -> None:
        raw = json.dumps(["python3", "/opt/tool.py", "--face", "{video}"])
        self.assertEqual(parse_argv_json(raw, variable="AIFILM_TOOL_ARGV")[2], "--face")

    def test_rejects_shell_strings_and_invalid_arrays(self) -> None:
        for raw in (
            "python3 tool.py --face {video}",
            json.dumps([]),
            json.dumps(["python3", 7]),
            json.dumps(["", "tool.py"]),
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(SecurityPolicyError):
                    parse_argv_json(raw, variable="AIFILM_TOOL_ARGV")

    def test_expansion_keeps_shell_metacharacters_inside_one_argument(self) -> None:
        argv = ["python3", "tool.py", "--face", "{video}", "--out", "{out}"]
        expanded = expand_argv(
            argv,
            {"video": "/tmp/a; touch PWNED.mp4", "out": "/tmp/out.mp4"},
            variable="AIFILM_TOOL_ARGV",
        )
        self.assertEqual(expanded[3], "/tmp/a; touch PWNED.mp4")
        self.assertEqual(len(expanded), 6)

    def test_unknown_or_formatted_placeholders_are_rejected(self) -> None:
        for argv in (["tool", "{secret}"], ["tool", "{video!r}"], ["tool", "{video:>8}"]):
            with self.subTest(argv=argv):
                with self.assertRaises(SecurityPolicyError):
                    expand_argv(argv, {"video": "/tmp/v.mp4"}, variable="AIFILM_TOOL_ARGV")


if __name__ == "__main__":
    unittest.main()
