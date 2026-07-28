from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

import pytest
from local_llm import (
    DEFAULT_MODEL,
    LocalLLMError,
    _NoRedirect,
    _request_json,
    draft,
    normalize_base_url,
    probe,
    shot_draft,
)


def test_normalize_base_url_requires_private_numeric_v1_host() -> None:
    assert normalize_base_url("http://192.168.88.52:1234/v1/") == "http://192.168.88.52:1234/v1"
    for value in ("https://example.com/v1", "http://8.8.8.8:1234/v1", "http://192.168.1.2:1234"):
        with pytest.raises(LocalLLMError):
            normalize_base_url(value)


def test_redirect_handler_rejects_all_redirects() -> None:
    assert (
        _NoRedirect().redirect_request(None, None, 302, "Found", {}, "http://localhost/v1") is None
    )


def test_request_rejects_redirect_before_following_it() -> None:
    class RedirectingHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            self.send_response(302)
            self.send_header("Location", "http://localhost:9/escaped")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectingHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(LocalLLMError, match="HTTP 302"):
            _request_json(f"http://127.0.0.1:{server.server_port}/v1", "/models")
    finally:
        server.shutdown()
        thread.join()


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
    with pytest.raises(LocalLLMError, match="did not finish normally"):
        draft("http://192.168.88.52:1234/v1", prompt="x")


@patch("local_llm._request_json")
def test_draft_rejects_non_stop_finish_reason(mock_request) -> None:
    mock_request.return_value = {
        "choices": [{"finish_reason": "content_filter", "message": {"content": "Filtered"}}]
    }
    with pytest.raises(LocalLLMError, match="did not finish normally"):
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
    with pytest.raises(LocalLLMError, match="valid two-shot"):
        shot_draft("http://192.168.88.52:1234/v1", prompt="x")


@pytest.mark.parametrize(
    "content",
    [
        '{"shots":[{"action":"walk","camera":"wide","extra":"no"},{"action":"deliver","camera":"close"}]}',
        '{"shots":[{"action":"'
        + ("x" * 91)
        + '","camera":"wide"},{"action":"deliver","camera":"close"}]}',
    ],
)
@patch("local_llm._request_json")
def test_shot_draft_enforces_full_schema(mock_request, content: str) -> None:
    mock_request.return_value = {
        "choices": [{"finish_reason": "stop", "message": {"content": content}}]
    }
    with pytest.raises(LocalLLMError, match="valid two-shot"):
        shot_draft("http://192.168.88.52:1234/v1", prompt="x")


@patch("local_llm._request_json")
def test_shot_draft_rejects_non_stop_finish_reason(mock_request) -> None:
    mock_request.return_value = {
        "choices": [
            {
                "finish_reason": "content_filter",
                "message": {
                    "content": '{"shots":[{"action":"walk","camera":"wide"},{"action":"deliver","camera":"close"}]}'
                },
            }
        ]
    }
    with pytest.raises(LocalLLMError, match="did not finish normally"):
        shot_draft("http://192.168.88.52:1234/v1", prompt="x")
