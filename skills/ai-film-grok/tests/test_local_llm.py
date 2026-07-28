from __future__ import annotations

from unittest.mock import patch

import pytest
from local_llm import DEFAULT_MODEL, LocalLLMError, draft, normalize_base_url, probe, shot_draft


def test_normalize_base_url_requires_private_numeric_v1_host() -> None:
    assert normalize_base_url("http://192.168.88.52:1234/v1/") == "http://192.168.88.52:1234/v1"
    for value in ("https://example.com/v1", "http://8.8.8.8:1234/v1", "http://192.168.1.2:1234"):
        with pytest.raises(LocalLLMError):
            normalize_base_url(value)


@patch("local_llm._request_json")
def test_probe_is_read_only_and_requires_approved_model(mock_request) -> None:
    mock_request.return_value = {"data": [{"id": DEFAULT_MODEL}, {"id": "other"}]}
    report = probe("http://192.168.88.52:1234/v1")
    assert report["ok"] is True
    assert report["inference_started"] is False
    assert report["fallback"].startswith("existing deterministic")
    mock_request.assert_called_once()


@patch("local_llm._request_json")
def test_draft_is_candidate_only_with_hashes(mock_request) -> None:
    mock_request.return_value = {
        "choices": [
            {"finish_reason": "stop", "message": {"content": "Two shots: rain, then delivery."}}
        ],
        "usage": {"total_tokens": 12},
    }
    report = draft("http://192.168.88.52:1234/v1", prompt="Draft a safe two-shot rain scene.")
    assert report["candidate"] == "Two shots: rain, then delivery."
    assert report["human_apply_required"] is True
    assert report["may_modify_story_truth"] is False
    assert len(report["candidate_sha256"]) == 64


@patch("local_llm._request_json")
def test_draft_rejects_empty_model_output(mock_request) -> None:
    mock_request.return_value = {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]}
    with pytest.raises(LocalLLMError, match="no usable candidate"):
        draft("http://192.168.88.52:1234/v1", prompt="x")


@patch("local_llm._request_json")
def test_draft_rejects_truncated_output(mock_request) -> None:
    mock_request.return_value = {
        "choices": [{"finish_reason": "length", "message": {"content": "Partial"}}]
    }
    with pytest.raises(LocalLLMError, match="truncated"):
        draft("http://192.168.88.52:1234/v1", prompt="x")


@patch("local_llm._request_json")
def test_shot_draft_requires_exactly_two_schema_valid_shots(mock_request) -> None:
    mock_request.return_value = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": (
                        '{"shots":[{"action":"walk","camera":"wide"},'
                        '{"action":"deliver","camera":"close"}]}'
                    )
                },
            }
        ],
        "usage": {"total_tokens": 20},
    }
    report = shot_draft("http://192.168.88.52:1234/v1", prompt="Courier in rain, then delivery")
    assert report["schema_valid"] is True
    assert len(report["candidate"]["shots"]) == 2


@patch("local_llm._request_json")
def test_shot_draft_rejects_missing_shot(mock_request) -> None:
    mock_request.return_value = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": '{"shots":[{"action":"walk","camera":"wide"}]}'},
            }
        ]
    }
    with pytest.raises(LocalLLMError, match="two usable shots"):
        shot_draft("http://192.168.88.52:1234/v1", prompt="x")
