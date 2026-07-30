"""Fail-closed client for an explicitly configured private OpenAI-compatible LLM.

This adapter produces reviewable creative candidates only.  It cannot write
story truth, select providers, or approve production gates.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, ValidationError

DEFAULT_MODEL = "openai/gpt-oss-20b"
ALLOWED_MODELS = frozenset({DEFAULT_MODEL})
_MAX_RESPONSE_BYTES = 1_048_576
_MAX_PROMPT_CHARS = 12_000
_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)
_TWO_SHOT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["shots"],
    "properties": {
        "shots": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["action", "camera"],
                "properties": {
                    "action": {"type": "string", "maxLength": 90},
                    "camera": {"type": "string", "maxLength": 48},
                },
            },
        }
    },
}


class LocalLLMError(RuntimeError):
    """A safe, machine-readable failure from the private local-model boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep an initial private endpoint from crossing a redirect boundary."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        del req, fp, code, msg, headers, newurl
        return None


def _private_opener() -> urllib.request.OpenerDirector:
    """Do not let ambient proxy settings export private requests or auth headers."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _safe_usage(value: Any) -> dict[str, int]:
    """A provider response must not echo credentials through a receipt-like result."""
    if not isinstance(value, dict):
        return {}
    return {
        key: raw
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if type(raw := value.get(key)) is int and raw >= 0
    }


def normalize_base_url(base_url: str) -> str:
    """Accept only a private numeric host and the OpenAI-compatible ``/v1`` root."""
    parsed = urlsplit(str(base_url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise LocalLLMError("LOCAL_LLM_URL_INVALID", "local LLM URL must use http(s) with a host")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LocalLLMError(
            "LOCAL_LLM_URL_INVALID",
            "local LLM URL must not include credentials, query, or fragment",
        )
    try:
        host = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise LocalLLMError(
            "LOCAL_LLM_URL_INVALID", "local LLM host must be a numeric private IP"
        ) from exc
    if not (host.is_loopback or any(host in network for network in _PRIVATE_NETWORKS)):
        raise LocalLLMError(
            "LOCAL_LLM_URL_NOT_PRIVATE", "local LLM host must be private or loopback"
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise LocalLLMError(
            "LOCAL_LLM_URL_INVALID", "local LLM URL contains an invalid port"
        ) from exc
    if port is None or not 1 <= port <= 65535:
        raise LocalLLMError("LOCAL_LLM_URL_INVALID", "local LLM URL must include a valid port")
    if parsed.path.rstrip("/") != "/v1":
        raise LocalLLMError("LOCAL_LLM_URL_INVALID", "local LLM URL must end with /v1")
    return f"{parsed.scheme}://{parsed.netloc}/v1"


def _require_model(model: str) -> str:
    if model not in ALLOWED_MODELS:
        raise LocalLLMError(
            "LOCAL_LLM_MODEL_NOT_ALLOWED",
            f"local LLM model is not approved; allowed: {sorted(ALLOWED_MODELS)}",
        )
    return model


def _request_json(
    base_url: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode() if body else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method="POST" if body is not None else "GET",
        headers=headers,
    )
    try:
        opener = _private_opener()
        with opener.open(request, timeout=timeout) as response:  # noqa: S310 -- private URL is validated above
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise LocalLLMError("LOCAL_LLM_HTTP_ERROR", f"local LLM returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise LocalLLMError("LOCAL_LLM_UNREACHABLE", "local LLM is unreachable") from exc
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise LocalLLMError("LOCAL_LLM_RESPONSE_TOO_LARGE", "local LLM response exceeded 1 MiB")
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise LocalLLMError("LOCAL_LLM_INVALID_JSON", "local LLM returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise LocalLLMError("LOCAL_LLM_INVALID_JSON", "local LLM returned an invalid JSON envelope")
    return value


def probe(base_url: str, *, model: str = DEFAULT_MODEL, token: str | None = None) -> dict[str, Any]:
    """Read only the model list; this never loads a model or starts inference."""
    normalized = normalize_base_url(base_url)
    approved_model = _require_model(model)
    response = _request_json(normalized, "/models", token=token, timeout=10)
    models = response.get("data")
    ids = sorted(
        item["id"]
        for item in models
        if isinstance(models, list) and isinstance(item, dict) and isinstance(item.get("id"), str)
    )
    available = approved_model in ids
    return {
        "schema_version": 1,
        "kind": "local-llm-probe",
        "base_url": normalized,
        "model": approved_model,
        "available_models": ids,
        "model_available": available,
        "ok": available,
        "inference_started": False,
        "fallback": "existing deterministic planning; no automatic retry",
    }


def draft(
    base_url: str,
    *,
    prompt: str,
    model: str = DEFAULT_MODEL,
    token: str | None = None,
    timeout: int = 45,
) -> dict[str, Any]:
    """Return one human-review-only creative candidate without modifying any film artifact."""
    normalized = normalize_base_url(base_url)
    approved_model = _require_model(model)
    clean_prompt = str(prompt).strip()
    if not clean_prompt or len(clean_prompt) > _MAX_PROMPT_CHARS:
        raise LocalLLMError(
            "LOCAL_LLM_PROMPT_INVALID", f"prompt must contain 1-{_MAX_PROMPT_CHARS} characters"
        )
    if timeout < 1 or timeout > 120:
        raise LocalLLMError(
            "LOCAL_LLM_TIMEOUT_INVALID", "timeout must be between 1 and 120 seconds"
        )
    response = _request_json(
        normalized,
        "/chat/completions",
        token=token,
        timeout=timeout,
        body={
            "model": approved_model,
            "temperature": 0,
            "max_tokens": 220,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You create a concise draft for a human film director. "
                        "Use no more than 120 words and no markdown. It is not approved story truth "
                        "and must not claim quality approval."
                    ),
                },
                {"role": "user", "content": clean_prompt},
            ],
        },
    )
    choices = response.get("choices")
    message = choices[0].get("message") if isinstance(choices, list) and choices else None
    content = message.get("content") if isinstance(message, dict) else None
    finish_reason = (
        choices[0].get("finish_reason") if isinstance(choices, list) and choices else None
    )
    if finish_reason != "stop":
        raise LocalLLMError(
            "LOCAL_LLM_INCOMPLETE_OUTPUT", "local LLM candidate did not finish normally"
        )
    if not isinstance(content, str) or not content.strip():
        raise LocalLLMError("LOCAL_LLM_EMPTY_OUTPUT", "local LLM returned no usable candidate")
    output = content.strip()
    usage = _safe_usage(response.get("usage"))
    return {
        "schema_version": 1,
        "kind": "local-llm-draft",
        "base_url": normalized,
        "model": approved_model,
        "candidate": output,
        "input_sha256": hashlib.sha256(clean_prompt.encode()).hexdigest(),
        "candidate_sha256": hashlib.sha256(output.encode()).hexdigest(),
        "usage": usage,
        "finish_reason": finish_reason,
        "status": "candidate_only",
        "human_apply_required": True,
        "may_modify_story_truth": False,
        "may_approve_production": False,
        "fallback": "existing deterministic planning; no automatic retry",
    }


def shot_draft(
    base_url: str,
    *,
    prompt: str,
    model: str = DEFAULT_MODEL,
    token: str | None = None,
    timeout: int = 45,
) -> dict[str, Any]:
    """Return an exactly-two-shot, schema-validated candidate for human review."""
    normalized = normalize_base_url(base_url)
    approved_model = _require_model(model)
    clean_prompt = str(prompt).strip()
    if not clean_prompt or len(clean_prompt) > _MAX_PROMPT_CHARS:
        raise LocalLLMError(
            "LOCAL_LLM_PROMPT_INVALID", f"prompt must contain 1-{_MAX_PROMPT_CHARS} characters"
        )
    if timeout < 1 or timeout > 120:
        raise LocalLLMError(
            "LOCAL_LLM_TIMEOUT_INVALID", "timeout must be between 1 and 120 seconds"
        )
    response = _request_json(
        normalized,
        "/chat/completions",
        token=token,
        timeout=timeout,
        body={
            "model": approved_model,
            "temperature": 0,
            "max_tokens": 320,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "two_shots", "strict": True, "schema": _TWO_SHOT_SCHEMA},
            },
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return exactly two concise, safe candidate shots. "
                        "Do not claim approval, invent provenance, or add markdown."
                    ),
                },
                {"role": "user", "content": clean_prompt},
            ],
        },
    )
    choices = response.get("choices")
    choice = (
        choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    )
    finish_reason = choice.get("finish_reason")
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if finish_reason != "stop":
        raise LocalLLMError(
            "LOCAL_LLM_INCOMPLETE_OUTPUT", "local LLM shot candidate did not finish normally"
        )
    try:
        candidate = json.loads(content) if isinstance(content, str) else None
    except json.JSONDecodeError as exc:
        raise LocalLLMError(
            "LOCAL_LLM_INVALID_SHOT_JSON", "local LLM returned invalid shot JSON"
        ) from exc
    try:
        Draft202012Validator(_TWO_SHOT_SCHEMA).validate(candidate)
    except ValidationError as exc:
        raise LocalLLMError(
            "LOCAL_LLM_INVALID_SHOT_JSON", "local LLM did not return a valid two-shot candidate"
        ) from exc
    shots = candidate["shots"]
    if any(not shot["action"].strip() or not shot["camera"].strip() for shot in shots):
        raise LocalLLMError(
            "LOCAL_LLM_INVALID_SHOT_JSON", "local LLM did not return two usable shots"
        )
    canonical = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    usage = _safe_usage(response.get("usage"))
    return {
        "schema_version": 1,
        "kind": "local-llm-shot-draft",
        "base_url": normalized,
        "model": approved_model,
        "candidate": candidate,
        "input_sha256": hashlib.sha256(clean_prompt.encode()).hexdigest(),
        "candidate_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "usage": usage,
        "finish_reason": finish_reason,
        "schema_valid": True,
        "status": "candidate_only",
        "human_apply_required": True,
        "may_modify_story_truth": False,
        "may_approve_production": False,
        "fallback": "existing deterministic planning; no automatic retry",
    }
