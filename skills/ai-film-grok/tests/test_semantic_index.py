from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from semantic_index import SemanticIndexError, build_index, collect_documents, query_index


def _write_root(root: Path) -> None:
    synthetic_github_token = "ghp" + "_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789012"
    (root / "drama-graph.json").write_text(
        json.dumps(
            {
                "title": "Rain delivery",
                "beats": [{"id": "bt01", "action": "Mei delivers a parcel in rain"}],
                "api_token": "do-not-index-this-secret",
                "apiKey": "do-not-index-this-secret-either",
                "cookie": "session=do-not-index-this-secret",
                "session": "do-not-index-this-session",
                "access_key": "do-not-index-this-access-key",
                "source": {"path": "/private/film/brief.txt"},
                "source_path": "/Users/dex/private/story.txt",
                "notes": "/etc/hosts",
                "description": r"C:\\Users\\dex\\private.txt",
                "text": r"\\server\\share\\private.txt",
                "theme": synthetic_github_token,
                "mood": "prefix(/Users/dex/private/story.txt)",
                "objective": "password=synthetic-secret-not-real",
                "dialogue": "access key = ACCESS_SECRET_8",
                "narration": "private key: PRIVATE_SECRET_9",
                "wardrobe": "AWS_SECRET_ACCESS_KEY=AWS_SECRET_10",
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
    synthetic_github_token = "ghp" + "_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789012"

    documents = collect_documents(tmp_path)

    assert {item["source"]["relative_path"] for item in documents} == {
        "drama-graph.json",
        "film-spec.json",
    }
    assert all(len(item["source"]["sha256"]) == 64 for item in documents)
    assert all("do-not-index-this-secret" not in item["text"] for item in documents)
    assert all("/private/film/brief.txt" not in item["text"] for item in documents)
    assert all("/Users/dex/private/story.txt" not in item["text"] for item in documents)
    assert all("do-not-index-this-session" not in item["text"] for item in documents)
    assert all("do-not-index-this-access-key" not in item["text"] for item in documents)
    assert all("/etc/hosts" not in item["text"] for item in documents)
    assert all("C:\\Users\\dex\\private.txt" not in item["text"] for item in documents)
    assert all("\\\\server\\share\\private.txt" not in item["text"] for item in documents)
    assert all(
        synthetic_github_token not in item["text"] for item in documents
    )
    assert all("prefix(/Users/dex/private/story.txt)" not in item["text"] for item in documents)
    assert all("synthetic-secret-not-real" not in item["text"] for item in documents)
    assert all("ACCESS_SECRET_8" not in item["text"] for item in documents)
    assert all("PRIVATE_SECRET_9" not in item["text"] for item in documents)
    assert all("AWS_SECRET_10" not in item["text"] for item in documents)


@patch("semantic_index._embed")
def test_build_writes_candidate_only_index_with_source_hashes(mock_embed, tmp_path: Path) -> None:
    _write_root(tmp_path)
    mock_embed.return_value = [[1.0, 0.0], [0.0, 1.0]]

    report = build_index(tmp_path, "http://192.168.88.52:1234/v1")

    stored = json.loads((tmp_path / "receipts" / "semantic-index.json").read_text(encoding="utf-8"))
    assert report["status"] == "candidate_only"
    assert report["relative_path"] == "receipts/semantic-index.json"
    assert "path" not in report
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


@patch("semantic_index._embed")
def test_rejects_index_text_tampering_and_source_symlink_swap(mock_embed, tmp_path: Path) -> None:
    _write_root(tmp_path)
    mock_embed.return_value = [[1.0, 0.0], [0.0, 1.0]]
    build_index(tmp_path, "http://192.168.88.52:1234/v1")
    index_path = tmp_path / "receipts" / "semantic-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["documents"][0]["text"] = "INJECTED_NOT_SOURCE_BOUND"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(SemanticIndexError, match="invalid"):
        query_index(tmp_path, "http://192.168.88.52:1234/v1", query="who delivers a parcel")

    _write_root(tmp_path)
    external = tmp_path / "external.json"
    external.write_text('{"title": "external"}', encoding="utf-8")
    graph = tmp_path / "drama-graph.json"
    from semantic_index import _source_paths

    def swap_after_discovery(root: Path) -> list[Path]:
        paths = _source_paths(root)
        graph.unlink()
        graph.symlink_to(external)
        return paths

    mock_embed.reset_mock()
    with patch("semantic_index._source_paths", side_effect=swap_after_discovery):
        with pytest.raises(SemanticIndexError, match="unsafe"):
            build_index(tmp_path, "http://192.168.88.52:1234/v1")
    mock_embed.assert_not_called()


@patch("semantic_index._embed")
def test_query_rejects_new_allowlisted_source_and_receipts_symlink(
    mock_embed, tmp_path: Path
) -> None:
    _write_root(tmp_path)
    mock_embed.return_value = [[1.0, 0.0], [0.0, 1.0]]
    build_index(tmp_path, "http://192.168.88.52:1234/v1")
    receipts = tmp_path / "receipts"
    (receipts / "shot-review-new.json").write_text(
        '{"approved": true, "notes": "new"}', encoding="utf-8"
    )
    with pytest.raises(SemanticIndexError, match="stale"):
        query_index(tmp_path, "http://192.168.88.52:1234/v1", query="who delivers a parcel")

    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(SemanticIndexError, match="symbolic"):
        build_index(linked_root, "http://192.168.88.52:1234/v1")

    symlink_root = tmp_path / "symlink-receipts"
    symlink_root.mkdir()
    _write_root(symlink_root)
    external_receipts = tmp_path / "external-receipts"
    external_receipts.mkdir()
    (symlink_root / "receipts").symlink_to(external_receipts, target_is_directory=True)
    with pytest.raises(SemanticIndexError, match="symbolic"):
        build_index(symlink_root, "http://192.168.88.52:1234/v1")


@patch("semantic_index._embed")
def test_build_and_query_reject_source_changes_during_remote_embedding(
    mock_embed, tmp_path: Path
) -> None:
    _write_root(tmp_path)

    def mutate_during_build(*args, **kwargs):
        del args, kwargs
        (tmp_path / "drama-graph.json").write_text('{"changed": true}', encoding="utf-8")
        return [[1.0, 0.0], [0.0, 1.0]]

    mock_embed.side_effect = mutate_during_build
    with pytest.raises(SemanticIndexError, match="changed during embedding"):
        build_index(tmp_path, "http://192.168.88.52:1234/v1")

    _write_root(tmp_path)
    mock_embed.side_effect = None
    mock_embed.return_value = [[1.0, 0.0], [0.0, 1.0]]
    build_index(tmp_path, "http://192.168.88.52:1234/v1")

    def mutate_during_query(*args, **kwargs):
        del args, kwargs
        (tmp_path / "film-spec.json").write_text('{"changed": true}', encoding="utf-8")
        return [[1.0, 0.0]]

    mock_embed.side_effect = mutate_during_query
    with pytest.raises(SemanticIndexError, match="stale"):
        query_index(tmp_path, "http://192.168.88.52:1234/v1", query="who delivers a parcel")


def test_build_requires_private_embedding_endpoint_and_indexable_source(tmp_path: Path) -> None:
    with pytest.raises(SemanticIndexError, match="indexable"):
        build_index(tmp_path, "http://192.168.88.52:1234/v1")
    _write_root(tmp_path)
    with pytest.raises(SemanticIndexError, match="private"):
        build_index(tmp_path, "https://example.com/v1")
