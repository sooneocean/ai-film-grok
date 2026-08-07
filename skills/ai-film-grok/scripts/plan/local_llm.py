"""Fail-closed client for an explicitly configured private OpenAI-compatible LLM.

This adapter produces reviewable creative candidates only.  It cannot write
story truth, select providers, or approve production gates.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, ValidationError

DEFAULT_MODEL = "openai/gpt-oss-20b"
# Vision models allowed for visual-text-audit / omni review on 5090 LM Studio pool.
ALLOWED_MODELS = frozenset(
    {
        DEFAULT_MODEL,
        "zai-org/glm-4.6v-flash",
        "nvidia/nemotron-3-nano-omni",
    }
)
# Models that accept an `image_url` content part in chat/completions.
VISION_MODELS = frozenset({"zai-org/glm-4.6v-flash", "nvidia/nemotron-3-nano-omni"})

# Decomposition schema: a full pre-production plan derived from a story (+ image).
_DECOMPOSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "title",
        "genre",
        "heat_scale",
        "characters",
        "scenes",
        "shot_hints",
        "voice_suggestions",
        "bgm_mood",
    ],
    "properties": {
        "title": {"type": "string", "maxLength": 80},
        "genre": {"type": "string", "maxLength": 40},
        "heat_scale": {"type": "string", "maxLength": 20},
        "theme": {"type": "string", "maxLength": 200},
        "tone": {"type": "string", "maxLength": 200},
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "name", "role"],
                "properties": {
                    "id": {"type": "string", "maxLength": 40},
                    "name": {"type": "string", "maxLength": 40},
                    "role": {"type": "string", "maxLength": 40},
                    "description": {"type": "string", "maxLength": 300},
                    "is_lead": {"type": "boolean"},
                },
            },
        },
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "summary"],
                "properties": {
                    "title": {"type": "string", "maxLength": 80},
                    "summary": {"type": "string", "maxLength": 300},
                    "mood": {"type": "string", "maxLength": 60},
                    "location": {"type": "string", "maxLength": 80},
                },
            },
        },
        "shot_hints": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["action", "camera"],
                "properties": {
                    "action": {"type": "string", "maxLength": 120},
                    "camera": {"type": "string", "maxLength": 60},
                },
            },
        },
        "voice_suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["character_id", "voice"],
                "properties": {
                    "character_id": {"type": "string", "maxLength": 40},
                    "voice": {"type": "string", "maxLength": 60},
                },
            },
        },
        "bgm_mood": {"type": "string", "maxLength": 120},
    },
}
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


def _image_data_url(path: str | Path | None) -> str | None:
    """Read an image file as a base64 data URL for a multimodal message, or None."""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    ext = p.suffix.lower().lstrip(".")
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }.get(ext)
    if not mime:
        return None
    try:
        raw = p.read_bytes()
    except OSError:
        return None
    if not raw or len(raw) > _MAX_RESPONSE_BYTES:
        return None
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def decompose(
    base_url: str,
    *,
    prompt: str,
    image_path: str | Path | None = None,
    model: str = DEFAULT_MODEL,
    token: str | None = None,
    timeout: int = 90,
) -> dict[str, Any]:
    """Return a structured pre-production plan (candidate-only, human-apply-required).

    If ``image_path`` is provided and ``model`` is a vision model, the lead image
    is attached as a multimodal part so the planner can use the protagonist visual.
    """
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

    user_content: list[dict[str, Any]] = [{"type": "text", "content": clean_prompt}]
    if image_path and approved_model in VISION_MODELS:
        data_url = _image_data_url(image_path)
        if data_url:
            user_content.insert(0, {"type": "image_url", "image_url": {"url": data_url}})

    response = _request_json(
        normalized,
        "/chat/completions",
        token=token,
        timeout=timeout,
        body={
            "model": approved_model,
            "temperature": 0,
            "max_tokens": 1200,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "decompose", "strict": True, "schema": _DECOMPOSE_SCHEMA},
            },
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a film pre-production planner. Given a story (and optional "
                        "protagonist image), return a structured decomposition: title, genre, "
                        "heat_scale, theme, tone, characters (id/name/role/description/is_lead), "
                        "scenes (title/summary/mood/location), shot_hints (action/camera), "
                        "voice_suggestions (character_id/voice using zh-CN neural voices), and "
                        "bgm_mood. Use safe, production-ready values. Do not claim approval or "
                        "invent provenance."
                    ),
                },
                {"role": "user", "content": user_content},
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
            "LOCAL_LLM_INCOMPLETE_OUTPUT", "local LLM decompose did not finish normally"
        )
    try:
        candidate = json.loads(content) if isinstance(content, str) else None
    except json.JSONDecodeError as exc:
        raise LocalLLMError(
            "LOCAL_LLM_INVALID_DECOMPOSE_JSON", "local LLM returned invalid decompose JSON"
        ) from exc
    try:
        Draft202012Validator(_DECOMPOSE_SCHEMA).validate(candidate)
    except ValidationError as exc:
        raise LocalLLMError(
            "LOCAL_LLM_INVALID_DECOMPOSE_JSON", "local LLM returned an invalid decomposition"
        ) from exc
    canonical = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    usage = _safe_usage(response.get("usage"))
    return {
        "schema_version": 1,
        "kind": "local-llm-decompose",
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
