"""Tests for the local content-addressed cache."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cache import ContentCache


def test_key_is_stable_sha256() -> None:
    assert ContentCache.key("abc") == ContentCache.key(b"abc")
    assert len(ContentCache.key("abc")) == 64


def test_put_get_and_json_roundtrip(tmp_path: Path) -> None:
    cache = ContentCache(tmp_path, namespace="unit")
    key = cache.key("payload")
    assert cache.get(key) is None
    path = cache.put(key, b"payload")
    assert path.is_file()
    assert cache.get(key) == b"payload"

    json_key = cache.key("json")
    cache.put_json(json_key, {"duration_sec": 1.25, "ok": True})
    assert cache.get_json(json_key) == {"duration_sec": 1.25, "ok": True}


def test_rejects_unsafe_keys_and_namespaces(tmp_path: Path) -> None:
    try:
        ContentCache(tmp_path, namespace="../escape")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe namespace accepted")

    cache = ContentCache(tmp_path)
    try:
        cache.get("../escape")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe cache key accepted")


def test_file_fingerprint_changes_when_file_changes(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"one")
    first = ContentCache.file_fingerprint(source)
    source.write_bytes(b"two")
    assert ContentCache.file_fingerprint(source) != first
