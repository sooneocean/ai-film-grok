"""Private, source-bound semantic retrieval for local film authoring records.

The index is a convenience layer: it returns human-review-only candidates and
never writes story truth, changes providers, or approves a production gate.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from local_llm import LocalLLMError, _request_json, normalize_base_url
from security_policy import atomic_write_text

DEFAULT_MODEL = "text-embedding-nomic-embed-text-v1.5"
ALLOWED_MODELS = frozenset({DEFAULT_MODEL})
INDEX_RELATIVE_PATH = Path("receipts") / "semantic-index.json"
_MAX_DOCUMENT_CHARS = 6_000
_MAX_DOCUMENTS = 128
_MAX_QUERY_CHARS = 1_000
_EMBED_BATCH_SIZE = 16
_SECRET_FIELD_MARKERS = frozenset(
    {
        "token",
        "secret",
        "password",
        "authorization",
        "apikey",
        "signature",
        "signedurl",
        "cookie",
        "credential",
        "privatekey",
        "accesskey",
        "session",
        "jwt",
    }
)
_SAFE_TEXT_KEYS = frozenset(
    {
        "action",
        "beat",
        "camera",
        "cameraaxis",
        "character",
        "characters",
        "description",
        "dialogue",
        "id",
        "location",
        "motion",
        "mood",
        "name",
        "narration",
        "notes",
        "objective",
        "palette",
        "pacing",
        "prop",
        "scene",
        "shotid",
        "style",
        "text",
        "theme",
        "title",
        "wardrobe",
    }
)
_SECRET_VALUE_MARKERS = (
    "bearer ",
    "sk-",
    "api_key=",
    "token=",
    "password=",
    "passwd=",
    "secret=",
    "signature=",
    "authorization:",
)
_SENSITIVE_ASSIGNMENT_KEYS = (
    "apikey",
    "accesskey",
    "privatekey",
    "secret",
    "token",
    "session",
    "cookie",
    "password",
    "authorization",
    "jwt",
    "signature",
)
_CREDENTIAL_VALUE = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})",
    re.IGNORECASE,
)
_ABSOLUTE_PATH = re.compile(r"(?:^|[^A-Za-z0-9])(?:/[^\s]+|\\\\|[A-Za-z]:[\\/])")
_MAX_SOURCE_BYTES = 2_000_000


class SemanticIndexError(RuntimeError):
    """An index is absent, unsafe, stale, or incompatible with the local node."""


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _has_sensitive_assignment(text: str) -> bool:
    for separator in ("=", ":"):
        if separator not in text:
            continue
        name = re.sub(r"[^a-z0-9]", "", text.split(separator, 1)[0].lower())
        if any(marker in name for marker in _SENSITIVE_ASSIGNMENT_KEYS):
            return True
    return False


def _read_json_source(path: Path) -> tuple[bytes, dict[str, Any] | list[Any]]:
    """Read only a regular file without following a final-component symlink."""
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise SemanticIndexError("index source must be a regular file")
            raw = handle.read(_MAX_SOURCE_BYTES + 1)
    except OSError as exc:
        raise SemanticIndexError("index source became unsafe or unreadable") from exc
    if len(raw) > _MAX_SOURCE_BYTES:
        raise SemanticIndexError("index source exceeds 2 MB")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemanticIndexError("index source must contain valid JSON") from exc
    if not isinstance(value, (dict, list)):
        raise SemanticIndexError("index source must contain a JSON object or array")
    return raw, value


def _source_paths(root: Path) -> list[Path]:
    candidates = [
        root / "drama-graph.json",
        root / "film-spec.json",
        root / "reference-analysis" / "shot-grammar.json",
    ]
    receipts = root / "receipts"
    if receipts.is_symlink():
        raise SemanticIndexError("receipts symbolic links are not allowed")
    if receipts.is_dir():
        for path in sorted(receipts.glob("shot-review-*.json")):
            try:
                _, value = _read_json_source(path)
            except SemanticIndexError:
                continue
            if isinstance(value, dict) and value.get("approved") is True:
                candidates.append(path)
    safe_paths: list[Path] = []
    for path in candidates:
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        if path.is_file() and not path.is_symlink():
            safe_paths.append(path)
    return safe_paths


def _safe_text(value: Any, *, path: str = "") -> list[str]:
    """Flatten useful JSON fields while excluding credential-like keys and values."""
    key = path.rsplit(".", 1)[-1].lower()
    normalized_key = re.sub(r"[^a-z0-9]", "", key)
    if any(marker in normalized_key for marker in _SECRET_FIELD_MARKERS):
        return []
    if isinstance(value, dict):
        lines: list[str] = []
        for name, child in sorted(value.items()):
            if isinstance(name, str):
                lines.extend(_safe_text(child, path=f"{path}.{name}" if path else name))
        return lines
    if isinstance(value, list):
        lines: list[str] = []
        for index, child in enumerate(value):
            lines.extend(_safe_text(child, path=f"{path}[{index}]"))
        return lines
    if normalized_key not in _SAFE_TEXT_KEYS:
        return []
    if isinstance(value, (str, int, float, bool)) and not isinstance(value, bool):
        text = str(value).strip()
        lowered = text.lower()
        if (
            text
            and not any(marker in lowered for marker in _SECRET_VALUE_MARKERS)
            and not _has_sensitive_assignment(text)
            and not _CREDENTIAL_VALUE.search(text)
            and not _ABSOLUTE_PATH.search(text)
            and "://" not in text
        ):
            return [f"{path}: {text}" if path else text]
    return []


def _document_from_path(root: Path, path: Path) -> dict[str, Any] | None:
    raw, value = _read_json_source(path)
    relative = path.relative_to(root).as_posix()
    text = "\n".join(_safe_text(value))[:_MAX_DOCUMENT_CHARS].strip()
    if not text:
        return None
    return {
        "id": "doc-" + _sha256_bytes((relative + "\0" + text).encode())[:20],
        "source": {"relative_path": relative, "sha256": _sha256_bytes(raw)},
        "text": text,
        "text_sha256": _sha256_bytes(text.encode()),
    }


def _project_root(root: Path | str) -> Path:
    raw_project = Path(root).expanduser()
    if raw_project.is_symlink():
        raise SemanticIndexError("film root symbolic links are not allowed")
    project = raw_project.resolve()
    if not project.is_dir():
        raise SemanticIndexError("film root is missing")
    return project


def collect_documents(root: Path | str) -> list[dict[str, Any]]:
    """Collect a bounded, allowlisted set of local authoring documents."""
    project = _project_root(root)
    documents = [
        doc for path in _source_paths(project) if (doc := _document_from_path(project, path))
    ]
    if not documents:
        raise SemanticIndexError("no indexable source documents found")
    if len(documents) > _MAX_DOCUMENTS:
        raise SemanticIndexError(f"index has more than {_MAX_DOCUMENTS} allowed documents")
    return documents


def _require_model(model: str) -> str:
    if model not in ALLOWED_MODELS:
        raise SemanticIndexError(
            f"embedding model is not approved; allowed: {sorted(ALLOWED_MODELS)}"
        )
    return model


def _normalize_endpoint(base_url: str) -> str:
    try:
        return normalize_base_url(base_url)
    except LocalLLMError as exc:
        raise SemanticIndexError(f"private embedding endpoint is invalid: {exc}") from exc


def _embed(
    base_url: str, *, model: str, inputs: list[str], token: str | None, timeout: int
) -> list[list[float]]:
    if timeout < 1 or timeout > 120:
        raise SemanticIndexError("timeout must be between 1 and 120 seconds")
    try:
        response = _request_json(
            base_url,
            "/embeddings",
            body={"model": model, "input": inputs},
            token=token,
            timeout=timeout,
        )
    except LocalLLMError as exc:
        raise SemanticIndexError(f"private embedding request failed: {exc.code}") from exc
    data = response.get("data")
    if not isinstance(data, list) or len(data) != len(inputs):
        raise SemanticIndexError("embedding response does not match requested documents")
    vectors: list[list[float]] = []
    for expected_index, item in enumerate(data):
        vector = item.get("embedding") if isinstance(item, dict) else None
        if not isinstance(item, dict) or item.get("index") != expected_index:
            raise SemanticIndexError("embedding response indices are invalid")
        if (
            not isinstance(vector, list)
            or not vector
            or any(
                not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector
            )
        ):
            raise SemanticIndexError("embedding response contains an invalid vector")
        vectors.append([float(value) for value in vector])
    dimension = len(vectors[0])
    if dimension > 4_096 or any(len(vector) != dimension for vector in vectors):
        raise SemanticIndexError("embedding response has inconsistent dimensions")
    return vectors


def _index_path(root: Path) -> Path:
    receipts = root / "receipts"
    if receipts.is_symlink():
        raise SemanticIndexError("receipts symbolic links are not allowed")
    return receipts / "semantic-index.json"


def _source_fingerprint(documents: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    return {
        (
            document["source"]["relative_path"],
            document["source"]["sha256"],
            document["text_sha256"],
        )
        for document in documents
    }


def build_index(
    root: Path | str,
    base_url: str,
    *,
    model: str = DEFAULT_MODEL,
    token: str | None = None,
    timeout: int = 45,
) -> dict[str, Any]:
    """Embed permitted local documents and atomically replace a derived index."""
    project = _project_root(root)
    endpoint = _normalize_endpoint(base_url)
    approved_model = _require_model(model)
    documents = collect_documents(project)
    inputs = [f"search_document: {doc['text']}" for doc in documents]
    vectors = [
        vector
        for offset in range(0, len(inputs), _EMBED_BATCH_SIZE)
        for vector in _embed(
            endpoint,
            model=approved_model,
            inputs=inputs[offset : offset + _EMBED_BATCH_SIZE],
            token=token,
            timeout=timeout,
        )
    ]
    if _source_fingerprint(collect_documents(project)) != _source_fingerprint(documents):
        raise SemanticIndexError(
            "semantic sources changed during embedding; run semantic-index build again"
        )
    for document, vector in zip(documents, vectors, strict=True):
        document["vector"] = vector
    index = {
        "schema_version": 1,
        "kind": "semantic-index",
        "created_at": datetime.now(UTC).isoformat(),
        "base_url": endpoint,
        "model": approved_model,
        "embedding_dimensions": len(vectors[0]),
        "documents": documents,
        "status": "candidate_only",
        "human_apply_required": True,
        "may_modify_story_truth": False,
        "may_approve_production": False,
    }
    path = _index_path(project)
    atomic_write_text(path, json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    return {
        "schema_version": 1,
        "kind": "semantic-index-build",
        "relative_path": INDEX_RELATIVE_PATH.as_posix(),
        "document_count": len(documents),
        "embedding_dimensions": index["embedding_dimensions"],
        "model": approved_model,
        "status": "candidate_only",
        "human_apply_required": True,
        "may_modify_story_truth": False,
        "may_approve_production": False,
    }


def _load_current_index(root: Path) -> dict[str, Any]:
    path = _index_path(root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemanticIndexError(
            "semantic index is missing or invalid; run semantic-index build"
        ) from exc
    if value.get("kind") != "semantic-index" or not isinstance(value.get("documents"), list):
        raise SemanticIndexError("semantic index is invalid; run semantic-index build")
    documents = value["documents"]
    dimensions = value.get("embedding_dimensions")
    if not isinstance(dimensions, int) or dimensions < 1:
        raise SemanticIndexError("semantic index is invalid; run semantic-index build")
    for document in documents:
        source = document.get("source") if isinstance(document, dict) else None
        vector = document.get("vector") if isinstance(document, dict) else None
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("relative_path"), str)
            or not isinstance(source.get("sha256"), str)
            or not isinstance(document.get("text"), str)
            or document.get("text_sha256") != _sha256_bytes(document.get("text", "").encode())
            or not isinstance(vector, list)
            or len(vector) != dimensions
        ):
            raise SemanticIndexError("semantic index is invalid; run semantic-index build")
    return value


def _require_fresh_sources(root: Path, documents: list[dict[str, Any]]) -> None:
    current = _source_fingerprint(collect_documents(root))
    indexed = _source_fingerprint(documents)
    if current != indexed:
        raise SemanticIndexError("semantic index is stale; run semantic-index build")
    for document in documents:
        source = document["source"]
        relative = Path(source["relative_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise SemanticIndexError("semantic index has an unsafe source path")
        path = root / relative
        try:
            raw, _ = _read_json_source(path)
        except SemanticIndexError as exc:
            raise SemanticIndexError("semantic index is stale; run semantic-index build") from exc
        if _sha256_bytes(raw) != source["sha256"]:
            raise SemanticIndexError("semantic index is stale; run semantic-index build")


def _cosine(left: list[float], right: list[float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        raise SemanticIndexError("semantic index contains a zero vector")
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def query_index(
    root: Path | str,
    base_url: str,
    *,
    query: str,
    limit: int = 5,
    model: str = DEFAULT_MODEL,
    token: str | None = None,
    timeout: int = 45,
) -> dict[str, Any]:
    """Return ranked source-bound text candidates; never mutate film files."""
    project = _project_root(root)
    endpoint = _normalize_endpoint(base_url)
    approved_model = _require_model(model)
    clean_query = str(query).strip()
    if not clean_query or len(clean_query) > _MAX_QUERY_CHARS:
        raise SemanticIndexError(f"query must contain 1-{_MAX_QUERY_CHARS} characters")
    if limit < 1 or limit > 20:
        raise SemanticIndexError("limit must be between 1 and 20")
    index = _load_current_index(project)
    if index.get("model") != approved_model:
        raise SemanticIndexError("semantic index model differs; run semantic-index build")
    documents = index["documents"]
    _require_fresh_sources(project, documents)
    query_vector = _embed(
        endpoint,
        model=approved_model,
        inputs=[f"search_query: {clean_query}"],
        token=token,
        timeout=timeout,
    )[0]
    _require_fresh_sources(project, documents)
    if len(query_vector) != index["embedding_dimensions"]:
        raise SemanticIndexError("embedding dimensions changed; run semantic-index build")
    ranked = sorted(
        (
            {
                "id": document["id"],
                "source": document["source"],
                "text": document["text"],
                "text_sha256": document["text_sha256"],
                "score": round(_cosine(query_vector, document["vector"]), 6),
            }
            for document in documents
        ),
        key=lambda item: (-item["score"], item["id"]),
    )[:limit]
    return {
        "schema_version": 1,
        "kind": "semantic-index-query",
        "query_sha256": _sha256_bytes(clean_query.encode()),
        "model": approved_model,
        "results": ranked,
        "status": "candidate_only",
        "human_apply_required": True,
        "may_modify_story_truth": False,
        "may_approve_production": False,
    }
