from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from util import (  # noqa: E402  # noqa: E402
    canonical_json_sha256,
    ensure_dir,
    exclusive_file_lock,
    sha256_file,
)
from util import read_json as permissive_read_json  # noqa: E402
from util import write_json as permissive_write_json
from util.json_io import atomic_write_text, read_json, write_json  # noqa: E402
from util.subprocess import run, run_compose_env  # noqa: E402
from util.time import utc_now  # noqa: E402
from util.validators import aspect_dims, film_output_path, slugify, valid_shot_id  # noqa: E402


class TimeTests(unittest.TestCase):
    def test_utc_now_format(self) -> None:
        ts = utc_now()
        self.assertIsInstance(ts, str)
        self.assertIn("T", ts)
        self.assertNotIn(".", ts.split("+")[0].split("T")[1] if "+" in ts else ts.split("T")[1])


class JsonIOTests(unittest.TestCase):
    def test_write_read_json(self) -> None:
        data = {"a": 1, "b": [2, 3]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "test.json"
            write_json(path, data)
            self.assertTrue(path.is_file())
            loaded = read_json(path)
            self.assertEqual(loaded, data)

    def test_read_json_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.json"
            with self.assertRaises(RuntimeError):
                read_json(missing)

    def test_atomic_write_text(self) -> None:
        content = "hello world"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "out.txt"
            atomic_write_text(path, content)
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_atomic_write_text_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.txt"
            atomic_write_text(path, "")
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_text(encoding="utf-8"), "")


class PermissiveJsonIOTests(unittest.TestCase):
    def test_legacy_write_read(self) -> None:
        data = {"x": 1}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "perm.json"
            permissive_write_json(path, data)
            loaded = permissive_read_json(path)
            self.assertEqual(loaded, data)

    def test_legacy_read_missing_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = permissive_read_json(Path(tmp) / "missing.json")
            self.assertIsNone(result)

    def test_legacy_canonical_hash(self) -> None:
        data = {"b": 2, "a": 1}
        h = canonical_json_sha256(data)
        self.assertIsInstance(h, str)
        self.assertEqual(len(h), 64)
        h2 = canonical_json_sha256(dict(sorted(data.items())))
        self.assertEqual(h, h2)


class Sha256FileTests(unittest.TestCase):
    def test_sha256_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.bin"
            path.write_bytes(b"hello world")
            h = sha256_file(path)
            self.assertIsInstance(h, str)
            self.assertEqual(len(h), 64)

    def test_sha256_file_large(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.bin"
            path.write_bytes(b"x" * (1024 * 1024 * 2 + 1))
            h = sha256_file(path)
            self.assertIsInstance(h, str)
            self.assertEqual(len(h), 64)


class EnsureDirTests(unittest.TestCase):
    def test_ensure_dir_creates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "a" / "b" / "c"
            self.assertFalse(d.is_dir())
            result = ensure_dir(d)
            self.assertTrue(d.is_dir())
            self.assertEqual(result, d)

    def test_ensure_dir_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = ensure_dir(Path(tmp))
            self.assertTrue(Path(tmp).is_dir())
            self.assertEqual(result, Path(tmp))


class ExclusiveFileLockTests(unittest.TestCase):
    def test_lock_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            with exclusive_file_lock(path):
                path.write_text("{}")
            self.assertTrue(path.is_file())

    def test_lock_creates_lock_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "locked.json"
            lock_path = path.with_name(f".{path.name}.lock")
            self.assertFalse(lock_path.is_file())
            with exclusive_file_lock(path):
                self.assertTrue(lock_path.is_file())


class ValidatorTests(unittest.TestCase):
    def test_slugify(self) -> None:
        self.assertEqual(slugify("Hello World"), "hello-world")
        self.assertEqual(slugify("  Foo  Bar  "), "foo-bar")
        self.assertEqual(slugify("你好世界"), "你好世界")
        self.assertEqual(slugify(""), "film")
        self.assertEqual(slugify("!!!###"), "film")

    def test_aspect_dims(self) -> None:
        self.assertEqual(aspect_dims("9:16"), (720, 1280))
        self.assertEqual(aspect_dims("16:9"), (1280, 720))
        self.assertEqual(aspect_dims("1:1"), (1024, 1024))
        with self.assertRaises(RuntimeError):
            aspect_dims("21:9")

    def test_valid_shot_id_ok(self) -> None:
        self.assertEqual(valid_shot_id("shot01"), "shot01")

    def test_valid_shot_id_invalid(self) -> None:
        with self.assertRaises(RuntimeError):
            valid_shot_id("../evil")

    def test_film_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            result = film_output_path(root, "film.mp4")
            self.assertEqual(result, (root / "out" / "film.mp4").resolve())

    def test_film_output_path_bad_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            with self.assertRaises(RuntimeError):
                film_output_path(root, "film.txt")


class SubprocessTests(unittest.TestCase):
    def test_run_echo(self) -> None:
        result = run(["echo", "hello"], check=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("hello", (result.stdout or ""))

    def test_run_fail(self) -> None:
        with self.assertRaises(Exception):
            run(["false"], check=True)

    def test_run_fail_no_check(self) -> None:
        result = run(["false"], check=False)
        self.assertNotEqual(result.returncode, 0)

    def test_run_compose_env_basic(self) -> None:
        result = run_compose_env(["echo", "test"], check=True)
        self.assertEqual(result.returncode, 0)

    def test_run_compose_env_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_compose_env(["pwd"], cwd=Path(tmp), check=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn(Path(tmp).name, (result.stdout or ""))


class BackCompatWrapperTests(unittest.TestCase):
    def test_aifilm_grok_utc_now(self) -> None:
        from aifilm_grok import utc_now as _f

        ts = _f()

        self.assertIsInstance(ts, str)
        self.assertIn("T", ts)

    def test_aifilm_grok_write_read_json(self) -> None:
        from aifilm_grok import read_json as _r
        from aifilm_grok import write_json as _w

        data = {"k": "v"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.json"
            _w(path, data)
            loaded = _r(path)
            self.assertEqual(loaded, data)

    def test_compose_render_utc_now(self) -> None:
        from compose_render import utc_now as _f

        self.assertIn("T", _f())

    def test_compose_preview_utc_now(self) -> None:
        from compose_preview import utc_now as _f

        self.assertIn("T", _f())

    def test_render_final_utc_now(self) -> None:
        from render_final import utc_now as _f

        self.assertIn("T", _f())

    def test_render_final_write_read_json(self) -> None:
        from render_final import read_json as _r
        from render_final import write_json as _w

        data = {"k": "v"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.json"
            _w(path, data)
            loaded = _r(path)
            self.assertEqual(loaded, data)

    def test_asset_registry_utc_now(self) -> None:
        from asset_registry import utc_now as _f

        self.assertIn("T", _f())


class ReExportTests(unittest.TestCase):
    def test_util_module_exports(self) -> None:
        from util import run as _r
        from util import slugify as _s
        from util import utc_now as _t

        self.assertIn("T", _t())
        self.assertEqual(_s("A B"), "a-b")
        self.assertIsNotNone(_r)

    def test_legacy_functions_still_exist(self) -> None:
        from util import (
            canonical_json_sha256,
            ensure_dir,
            exclusive_file_lock,
            read_json,
            sha256_file,
            write_json,
        )

        self.assertIsNotNone(canonical_json_sha256({"a": 1}))
        self.assertIsNotNone(ensure_dir)
        self.assertIsNotNone(exclusive_file_lock)
        self.assertIsNotNone(read_json)
        self.assertIsNotNone(sha256_file)
        self.assertIsNotNone(write_json)


if __name__ == "__main__":
    unittest.main()
