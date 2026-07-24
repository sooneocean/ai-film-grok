#!/usr/bin/env python3
"""Canonical production control book with precise downstream invalidation."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from util import exclusive_file_lock, read_json, utc_now, write_json

BOOK_NAME = "production-book.json"
SCHEMA_VERSION = 1
RIGOR_LEVELS = {"legacy", "guided", "professional"}
QUALITY_TARGETS = {"standard", "premium_vertical"}
STATES = {"draft", "review", "locked", "stale"}

DEFAULT_DEPENDENCIES: dict[str, list[str]] = {
    "story": [],
    "editorial": ["story"],
    "visual": ["story", "editorial"],
    "performance": ["story", "visual"],
    "sound": ["story", "editorial", "performance"],
    "post": ["visual", "performance", "sound"],
    "delivery": ["post"],
}

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_HASH_IGNORED_KEYS = {"content_sha256", "updated_at", "created_at"}


class ProductionBookError(ValueError):
    """Base error for malformed production-book operations."""


class ProductionBookConflict(ProductionBookError):
    """An optimistic-lock revision did not match the current book."""


def production_book_path(root: Path | str) -> Path:
    candidate = Path(root).expanduser()
    return candidate if candidate.name == BOOK_NAME else candidate / BOOK_NAME


def _hashable(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _hashable(item)
            for key, item in value.items()
            if key not in _HASH_IGNORED_KEYS
        }
    if isinstance(value, list):
        return [_hashable(item) for item in value]
    return value


def stable_content_hash(value: Any) -> str:
    payload = json.dumps(
        _hashable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _department(department_id: str) -> dict[str, Any]:
    return {
        "ref": f"production-book://department/{department_id}",
        "revision": 1,
        "content_sha256": stable_content_hash({"department": department_id, "revision": 1}),
        "state": "draft",
        "stale_reasons": [],
    }


def new_production_book(
    *,
    title: str = "Untitled",
    rigor: str = "professional",
    format_pack: str = "vertical-short",
    genre_pack: str = "drama",
    quality_target: str = "standard",
    phase: str = "development",
    stage: str = "idea",
) -> dict[str, Any]:
    if rigor not in RIGOR_LEVELS:
        raise ProductionBookError("rigor must be legacy|guided|professional")
    if quality_target not in QUALITY_TARGETS:
        raise ProductionBookError("quality_target must be standard|premium_vertical")
    now = utc_now()
    book: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "production-book",
        "title": str(title),
        "rigor": rigor,
        "quality_target": quality_target,
        "packs": {"format": str(format_pack), "genre": str(genre_pack)},
        "phase": str(phase),
        "stage": str(stage),
        "state": "draft",
        "revision": 1,
        "created_at": now,
        "updated_at": now,
        "departments": {name: _department(name) for name in DEFAULT_DEPENDENCIES},
        "dependency_graph": copy.deepcopy(DEFAULT_DEPENDENCIES),
        "stale_reasons": [],
        "exception_ledger": [],
        "assets": [],
    }
    book["content_sha256"] = stable_content_hash(book)
    return book


def _normalize_legacy(raw: dict[str, Any]) -> dict[str, Any]:
    book = copy.deepcopy(raw)
    is_legacy = "rigor" not in book
    book.setdefault("schema_version", SCHEMA_VERSION)
    book.setdefault("kind", "production-book")
    book["rigor"] = "legacy" if is_legacy else str(book["rigor"])
    if book["rigor"] not in RIGOR_LEVELS:
        raise ProductionBookError("rigor must be legacy|guided|professional")
    book.setdefault("quality_target", "standard")
    book["quality_target"] = str(book["quality_target"])
    if book["quality_target"] not in QUALITY_TARGETS:
        raise ProductionBookError("quality_target must be standard|premium_vertical")
    book.setdefault("title", "Untitled")
    book.setdefault("packs", {"format": "legacy", "genre": "legacy"})
    book.setdefault("phase", "development")
    book.setdefault("stage", "idea")
    book.setdefault("state", "draft")
    book.setdefault("revision", 1)
    book.setdefault("departments", {})
    for name in DEFAULT_DEPENDENCIES:
        book["departments"].setdefault(name, _department(name))
    book.setdefault("dependency_graph", copy.deepcopy(DEFAULT_DEPENDENCIES))
    book.setdefault("stale_reasons", [])
    book.setdefault("exception_ledger", [])
    book.setdefault("assets", [])
    book.setdefault("created_at", utc_now())
    book.setdefault("updated_at", book["created_at"])
    book["content_sha256"] = stable_content_hash(book)
    return book


def read_production_book(root: Path | str) -> dict[str, Any]:
    path = production_book_path(root)
    raw = read_json(path)
    if raw is None:
        raise FileNotFoundError(path)
    recorded_hash = raw.get("content_sha256")
    if isinstance(recorded_hash, str) and recorded_hash != stable_content_hash(raw):
        raise ProductionBookError("production book content hash is stale or tampered")
    return _normalize_legacy(raw)


def _assert_revision(book: dict[str, Any], expected_revision: int | None) -> None:
    if expected_revision is None:
        return
    actual = int(book.get("revision") or 0)
    if actual != expected_revision:
        raise ProductionBookConflict(
            f"expected revision {expected_revision}, current revision is {actual}"
        )


def write_production_book(
    root: Path | str,
    book: dict[str, Any],
    *,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    path = production_book_path(root)
    with exclusive_file_lock(path):
        current = read_json(path)
        if current is not None:
            recorded_hash = current.get("content_sha256")
            if isinstance(recorded_hash, str) and recorded_hash != stable_content_hash(current):
                raise ProductionBookError("refusing to replace a tampered production book")
            _assert_revision(current, expected_revision)
        elif expected_revision not in {None, 0}:
            raise ProductionBookConflict(
                f"expected revision {expected_revision}, but production book does not exist"
            )
        output = _normalize_legacy(book)
        write_json(path, output)
        return output


def init_production_book(
    root: Path | str,
    *,
    title: str = "Untitled",
    rigor: str = "professional",
    format_pack: str = "vertical-short",
    genre_pack: str = "drama",
    quality_target: str = "standard",
    phase: str = "development",
    stage: str = "idea",
) -> dict[str, Any]:
    path = production_book_path(root)
    if path.is_file():
        return read_production_book(path)
    book = new_production_book(
        title=title,
        rigor=rigor,
        format_pack=format_pack,
        genre_pack=genre_pack,
        quality_target=quality_target,
        phase=phase,
        stage=stage,
    )
    return write_production_book(path, book, expected_revision=0)


def update_department(
    root: Path | str,
    department: str,
    *,
    revision: int,
    content_sha256: str,
    ref: str | None = None,
    state: str = "review",
    expected_revision: int,
) -> dict[str, Any]:
    if state not in STATES:
        raise ProductionBookError("state must be draft|review|locked|stale")
    if revision < 1 or not _SHA256_RE.fullmatch(content_sha256):
        raise ProductionBookError("department requires a positive revision and SHA-256 hash")
    book = read_production_book(root)
    _assert_revision(book, expected_revision)
    if department not in book["departments"]:
        raise ProductionBookError(f"unknown department: {department}")
    entry = book["departments"][department]
    entry.update(
        {
            "ref": ref or entry["ref"],
            "revision": revision,
            "content_sha256": content_sha256,
            "state": state,
        }
    )
    entry["stale_reasons"] = []
    book["revision"] = expected_revision + 1
    book["updated_at"] = utc_now()
    book["state"] = (
        "stale"
        if any(item.get("state") == "stale" for item in book["departments"].values())
        else "review"
    )
    return write_production_book(root, book, expected_revision=expected_revision)


def _dependency_closure(graph: dict[str, list[str]], changed: Iterable[str]) -> list[str]:
    known = list(graph)
    selected = {name for name in changed if name in graph}
    unknown = set(changed) - selected
    if unknown:
        raise ProductionBookError(f"unknown dependency refs: {', '.join(sorted(unknown))}")
    while True:
        additions = {
            node
            for node, dependencies in graph.items()
            if node not in selected and any(dependency in selected for dependency in dependencies)
        }
        if not additions:
            break
        selected.update(additions)
    return [name for name in known if name in selected]


def impact_dry_run(
    book: dict[str, Any], changed_refs: Iterable[str], *, reason: str
) -> dict[str, Any]:
    changed = list(dict.fromkeys(str(item) for item in changed_refs))
    if not changed or not str(reason).strip():
        raise ProductionBookError("impact requires changed refs and a stale reason")
    graph = book.get("dependency_graph")
    if not isinstance(graph, dict):
        raise ProductionBookError("production book dependency_graph is invalid")
    affected = _dependency_closure(graph, changed)
    digest = stable_content_hash(
        {
            "source_revision": book.get("revision"),
            "source_sha256": stable_content_hash(book),
            "changed_refs": changed,
            "affected": affected,
            "reason": reason,
        }
    )
    return {
        "kind": "production-book-impact",
        "dry_run": True,
        "source_revision": int(book.get("revision") or 0),
        "source_sha256": stable_content_hash(book),
        "changed_refs": changed,
        "affected": affected,
        "reason": str(reason),
        "transaction_id": f"production-impact-{digest[:20]}",
        "assets_deleted": [],
    }


def apply_stale_propagation(
    book: dict[str, Any],
    impact: dict[str, Any],
    *,
    expected_revision: int,
    transaction_id: str | None = None,
) -> dict[str, Any]:
    _assert_revision(book, expected_revision)
    if impact.get("source_revision") != expected_revision:
        raise ProductionBookConflict("impact source revision is no longer current")
    if impact.get("source_sha256") != stable_content_hash(book):
        raise ProductionBookConflict("impact source hash is no longer current")
    if transaction_id is not None and impact.get("transaction_id") != transaction_id:
        raise ProductionBookConflict("impact transaction id does not match")
    expected = impact_dry_run(
        book, impact.get("changed_refs") or [], reason=impact.get("reason") or ""
    )
    if expected["affected"] != impact.get("affected"):
        raise ProductionBookConflict("impact dependency closure does not match current book")

    output = copy.deepcopy(book)
    stale_record = {
        "reason": impact["reason"],
        "changed_refs": list(impact["changed_refs"]),
        "affected": list(impact["affected"]),
        "transaction_id": impact["transaction_id"],
        "at": utc_now(),
    }
    for name in impact["affected"]:
        department = output["departments"][name]
        department["state"] = "stale"
        department.setdefault("stale_reasons", []).append(copy.deepcopy(stale_record))
    output.setdefault("stale_reasons", []).append(stale_record)
    output["state"] = "stale"
    output["revision"] = expected_revision + 1
    output["updated_at"] = utc_now()
    output["content_sha256"] = stable_content_hash(output)
    return output
