from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from semantic_index import SemanticIndexError, build_index, collect_documents, query_index


def _write_root(root: Path) -> None:
    (root / "drama-graph.json").write_text(
        json.dumps(
            {
                "title": "Rain delivery",
                "beats": [{"id": "bt01", "action": "Mei delivers a parcel in rain"}],
                "api_token": "do-not-index-this-secret",
                "source": {"path": "/private/film/brief.txt"},
            }
        ),
        encoding="utf-8",
    )
    (root / "film-spec.json").write_text(
        json.dumps({"shots": [{"id": "s01", "action": "red jacket enters alley"}]}),
        encoding="utf-8",
    )


def test_collect_documents_is_source_bound_and_redacts_secret_values(tmp_path: Path) -> None:
    _write_root(tmp_path)

    documents = collect_documents(tmp_path)

    assert {item["source"]["relative_path"] for item in documents} == {
        "drama-graph.json",
        "film-spec.json",
    }
    assert all(len(item["source"]["sha256"]) == 64 for item in documents)
    assert all("do-not-index-this-secret" not in item["text"] for item in documents)
    assert all("/private/film/brief.txt" not in item["text"] for item in documents)


@patch("semantic_index._embed")
def test_build_writes_candidate_only_index_with_source_hashes(mock_embed, tmp_path: Path) -> None:
    _write_root(tmp_path)
    mock_embed.return_value = [[1.0, 0.0], [0.0, 1.0]]

    report = build_index(tmp_path, "http://192.168.88.52:1234/v1")

    stored = json.loads((tmp_path / "receipts" / "semantic-index.json").read_text(encoding="utf-8"))
    assert report["status"] == "candidate_only"
    assert report["may_modify_story_truth"] is False
    assert report["may_approve_production"] is False
    assert stored["kind"] == "semantic-index"
    assert len(stored["documents"]) == 2
    assert stored["embedding_dimensions"] == 2
    assert stored["documents"][0]["source"]["sha256"]
    mock_embed.assert_called_once()


@patch("semantic_index._embed")
def test_query_returns_ranked_source_bound_candidate_and_rejects_stale_index(
    mock_embed, tmp_path: Path
) -> None:
    _write_root(tmp_path)
    mock_embed.return_value = [[1.0, 0.0], [0.0, 1.0]]
    build_index(tmp_path, "http://192.168.88.52:1234/v1")
    mock_embed.return_value = [[1.0, 0.0]]

    report = query_index(tmp_path, "http://192.168.88.52:1234/v1", query="who delivers a parcel")

    assert report["results"][0]["source"]["relative_path"] == "drama-graph.json"
    assert report["results"][0]["score"] == 1.0
    assert "vector" not in report["results"][0]

    (tmp_path / "drama-graph.json").write_text('{"changed": true}', encoding="utf-8")
    with pytest.raises(SemanticIndexError, match="stale"):
        query_index(tmp_path, "http://192.168.88.52:1234/v1", query="who delivers a parcel")


def test_build_requires_private_embedding_endpoint_and_indexable_source(tmp_path: Path) -> None:
    with pytest.raises(SemanticIndexError, match="indexable"):
        build_index(tmp_path, "http://192.168.88.52:1234/v1")
    _write_root(tmp_path)
    with pytest.raises(SemanticIndexError, match="private"):
        build_index(tmp_path, "https://example.com/v1")
