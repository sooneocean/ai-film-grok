#!/usr/bin/env python3
"""I2V provider abstraction and action-routing layer.

Free-local default (h3_primary): 5090 MiniMax H3 primary, Grok Video 1.5 兜底.
Compatibility: ltx23_* LTX chain; grok_primary/hybrid soft → Grok first. New providers can be added
by implementing :class:`I2VProvider` and registering them instead of scattering
``source_endpoint`` labels through the codebase.

This module is the **registry + routing** layer; the actual generation still
delegates to the existing paths:

* Grok provider → Grok Build ``image_to_video`` (in-session) or
  ``scripts/adapters/grok_oauth_image.py``.
* FRW providers → ``scripts/frw_dispatch.py``.
* Local providers → the private, capability-gated ComfyUI control plane.

Backward-compatible: the existing ``source_endpoint`` labels in
``ALLOWED_VIDEO_ENDPOINTS`` keep working — the registry maps them to provider
instances rather than replacing them.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from security_policy import SecurityPolicyError, safe_existing_file, validate_identifier
from util import canonical_json_sha256, sha256_file, write_json


class I2VProviderError(RuntimeError):
    pass


TECHNICAL_FAILURE_MARKERS = (
    "timeout",
    "timed out",
    "connection reset",
    "connection refused",
    "temporary failure",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "rate limit",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
)
NON_TECHNICAL_FAILURE_MARKERS = (
    "human review",
    "human_review",
    "review rejected",
    "quality fail",
    "quality rejection",
    "identity fail",
    "motion review",
    "pilot rejected",
    "moderation",
    "content policy",
    "approval rejected",
)
_SWITCH_HMAC_FIELD = "switch_hmac_sha256"
_SWITCH_HASH_FIELD = "switch_sha256"
_SWITCH_KEY_ENV = "AIFILM_PROVIDER_SWITCH_RECEIPT_KEY"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WAN_MODEL_IDENTITY_RE = re.compile(r"(?:^|/)wan(?:[0-9._-]|$)")
ACTION_PROVIDER_PRIORITY = ("frw-ltx23", "frw-api-i2v", "grok")
# Free-local 5090 primary: MiniMax H3 first; Grok Video 1.5 = technical 兜底 only.
H3_PRIMARY_PROVIDER_PRIORITY = ("comfy-h3", "grok")
# Paid-cloud Grok bulk (grok_primary) and hybrid soft lane.
GROK_PRIMARY_PROVIDER_PRIORITY = ("grok",)


def _env_truthy(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def is_technical_failure(error: object) -> bool:
    """Return whether an error is safe to route to the next provider.

    Provider quality rejection, human review failure, and ambiguous task
    creation are deliberately not classified as automatic fallback triggers.
    """
    if isinstance(error, dict):
        if error.get("task_id") or error.get("generation_id"):
            return False
        status = str(error.get("status_code") or error.get("http_status") or "")
        if status in {"408", "425", "429", "500", "502", "503", "504"}:
            return True
        error = error.get("error") or error.get("message") or ""
    text = str(error).lower()
    if any(marker in text for marker in NON_TECHNICAL_FAILURE_MARKERS):
        return False
    return any(marker in text for marker in TECHNICAL_FAILURE_MARKERS)


def _provider_switch_key() -> bytes:
    value = os.environ.get(_SWITCH_KEY_ENV, "").strip()
    if len(value) < 32:
        raise I2VProviderError(
            "PROVIDER_SWITCH_RECEIPT_KEY_REQUIRED: "
            f"{_SWITCH_KEY_ENV} must contain at least 32 characters"
        )
    return value.encode("utf-8")


def _switch_content(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in receipt.items()
        if key not in {_SWITCH_HASH_FIELD, _SWITCH_HMAC_FIELD, "path", "archive_path"}
    }


def _switch_hmac_bytes(receipt: dict[str, Any]) -> bytes:
    return json.dumps(
        {
            key: value
            for key, value in receipt.items()
            if key not in {_SWITCH_HMAC_FIELD, "path", "archive_path"}
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sign_provider_switch_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt[_SWITCH_HASH_FIELD] = canonical_json_sha256(_switch_content(receipt))
    receipt[_SWITCH_HMAC_FIELD] = hmac.new(
        _provider_switch_key(),
        _switch_hmac_bytes(receipt),
        hashlib.sha256,
    ).hexdigest()
    return receipt


def provider_switch_receipt_is_valid(receipt: dict[str, Any]) -> bool:
    """Require both canonical content binding and a local-only HMAC."""
    content_hash = receipt.get(_SWITCH_HASH_FIELD)
    signature = receipt.get(_SWITCH_HMAC_FIELD)
    if (
        not isinstance(content_hash, str)
        or not _SHA256_RE.fullmatch(content_hash)
        or not isinstance(signature, str)
        or not _SHA256_RE.fullmatch(signature)
    ):
        return False
    expected_hash = canonical_json_sha256(_switch_content(receipt))
    if not hmac.compare_digest(content_hash, expected_hash):
        return False
    try:
        expected_hmac = hmac.new(
            _provider_switch_key(),
            _switch_hmac_bytes(receipt),
            hashlib.sha256,
        ).hexdigest()
    except I2VProviderError:
        return False
    return hmac.compare_digest(signature, expected_hmac)


def _technical_failure_label(error: object) -> str:
    text = str(error).lower()
    return next(
        (marker for marker in TECHNICAL_FAILURE_MARKERS if marker in text),
        "technical_failure",
    )


def _has_wan_model_identity(value: object) -> bool:
    """Accept only a model name whose provider token is explicitly Wan."""
    return bool(_WAN_MODEL_IDENTITY_RE.search(str(value or "").strip().casefold()))


def _canary_output_is_bound(root: Path, data: dict[str, Any]) -> bool:
    output = data.get("output")
    if isinstance(output, dict):
        output = output.get("path")
    output = output or data.get("output_path")
    expected = data.get("output_sha256")
    if not output or not isinstance(expected, str) or not _SHA256_RE.fullmatch(expected):
        return False
    try:
        media = safe_existing_file(root, str(output), field="canary output")
    except SecurityPolicyError:
        return False
    return hmac.compare_digest(sha256_file(media), expected)


def _canary_media_is_approved(root: Path, data: dict[str, Any]) -> bool:
    """Require a real local decode and usable geometry, not a claimed receipt flag."""
    output = data.get("output")
    if isinstance(output, dict):
        output = output.get("path")
    output = output or data.get("output_path")
    if not output:
        return False
    try:
        media = safe_existing_file(root, str(output), field="canary output")
        from media_qa import analyze_media

        report = analyze_media(media, require_audio=False, require_motion=False)
    except Exception:
        return False
    return bool(
        report.get("ok")
        and report.get("decode_ok")
        and int(report.get("width") or 0) >= 704
        and int(report.get("height") or 0) >= 1280
    )


def _write_switch_receipt(
    root: Path | None,
    *,
    shot_id: str,
    primary: str,
    fallback: str,
    error: object,
    plan_sha256: str | None = None,
) -> dict[str, Any]:
    receipt = {
        "schema_version": 1,
        "kind": "provider-switch",
        # The archive is append-only evidence, including repeated attempts for one shot.
        "event_id": uuid.uuid4().hex,
        "shot_id": shot_id,
        "primary_provider": primary,
        "fallback_provider": fallback,
        "reason_class": "technical_failure",
        "error": _technical_failure_label(error),
        "fallback_fixed_for_shot": True,
    }
    if plan_sha256 is not None:
        if not _SHA256_RE.fullmatch(plan_sha256):
            raise I2VProviderError("PROVIDER_SWITCH_PLAN_INVALID: plan_sha256 must be SHA-256")
        receipt["plan_sha256"] = plan_sha256
    _sign_provider_switch_receipt(receipt)
    if root is not None:
        receipt_root = Path(root).expanduser().resolve() / "receipts"
        path = receipt_root / f"provider-switch-{shot_id}.json"
        archive_path = (
            receipt_root
            / "provider-switches"
            / (f"provider-switch-{shot_id}-{primary}-to-{fallback}-{receipt['event_id']}.json")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, receipt)
        write_json(archive_path, receipt)
        receipt["path"] = str(path)
        receipt["archive_path"] = str(archive_path)
    return receipt


def route_after_failure(
    *,
    root: Path | None,
    shot_id: str,
    primary: str,
    error: object,
    plan_sha256: str | None = None,
    fallback_name: str | None = None,
) -> tuple[I2VProvider, dict[str, Any]] | None:
    """Select a reviewed fallback only after a classified technical failure."""
    priority = provider_priority()
    if primary not in priority or not is_technical_failure(error):
        return None
    try:
        stable_shot_id = validate_identifier(shot_id, field="shot id")
    except SecurityPolicyError as exc:
        raise I2VProviderError(f"PROVIDER_SWITCH_SHOT_ID_INVALID: {exc}") from exc
    if fallback_name is None:
        try:
            fallback_name = priority[priority.index(primary) + 1]
        except (ValueError, IndexError):
            return None
    if fallback_name not in priority:
        raise I2VProviderError(f"PROVIDER_SWITCH_FALLBACK_INVALID: {fallback_name}")
    provider = get(fallback_name)
    return provider, _write_switch_receipt(
        root,
        shot_id=stable_shot_id,
        primary=primary,
        fallback=provider.name,
        error=error,
        plan_sha256=plan_sha256,
    )


def generate_with_fallback(
    *,
    root: Path | None,
    shot_id: str,
    keyframe: Path,
    prompt: str,
    plan_sha256: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run the action-provider chain in policy order.

    Unready providers are skipped with a receipt-visible reason.  A provider
    that starts a task may fall through only after a classified technical
    failure; quality or human-review rejection never switches silently.
    """
    if not isinstance(plan_sha256, str) or not _SHA256_RE.fullmatch(plan_sha256):
        raise I2VProviderError("PROVIDER_SWITCH_PLAN_INVALID: plan_sha256 must be SHA-256")
    try:
        stable_shot_id = validate_identifier(shot_id, field="shot id")
    except SecurityPolicyError as exc:
        raise I2VProviderError(f"PROVIDER_SWITCH_SHOT_ID_INVALID: {exc}") from exc
    attempts: list[dict[str, Any]] = []
    technical_failure: tuple[str, object] | None = None
    switches: list[dict[str, Any]] = []
    for index, provider_name in enumerate(provider_priority()):
        provider = get(provider_name)
        capability = provider.probe(root=root)
        if not capability.available:
            attempts.append(
                {
                    "provider": provider_name,
                    "status": "not_ready",
                    "reason": str(capability.reason or "live capability unavailable")[:200],
                }
            )
            continue
        if technical_failure is not None:
            failed_provider, failed_error = technical_failure
            switch = _write_switch_receipt(
                root,
                shot_id=stable_shot_id,
                primary=failed_provider,
                fallback=provider_name,
                error=failed_error,
                plan_sha256=plan_sha256,
            )
            switches.append(switch)
            technical_failure = None
        try:
            result = provider.generate(keyframe=keyframe, prompt=prompt, **kwargs)
            if not result.get("ok"):
                raise I2VProviderError(
                    str(result.get("stderr") or result.get("error") or f"{provider_name} failed")
                )
        except Exception as exc:
            attempts.append(
                {
                    "provider": provider_name,
                    "status": "technical_failure" if is_technical_failure(exc) else "failed_closed",
                    "reason": _technical_failure_label(exc)
                    if is_technical_failure(exc)
                    else "non_technical_failure",
                }
            )
            if not is_technical_failure(exc):
                raise
            technical_failure = (provider_name, exc)
            continue
        attempts.append({"provider": provider_name, "status": "completed"})
        result["route"] = f"{provider_name}_{'primary' if index == 0 else 'fallback'}"
        result["routing_attempts"] = attempts
        result["provider_priority"] = list(provider_priority())
        if switches:
            result["provider_switch"] = switches[-1]
            result["provider_switches"] = switches
        if root is not None:
            write_json(
                Path(root).expanduser().resolve() / "receipts" / "i2v-routing.json",
                {
                    "schema_version": 2,
                    "kind": "i2v-routing",
                    "shot_id": stable_shot_id,
                    "plan_sha256": plan_sha256,
                    "provider_priority": list(provider_priority()),
                    "selected_provider": provider_name,
                    "attempts": attempts,
                    "provider_switch_sha256s": [item[_SWITCH_HASH_FIELD] for item in switches],
                },
            )
        return result
    reasons = ", ".join(
        f"{item['provider']}={item['status']}:{item['reason']}" for item in attempts
    )
    raise I2VProviderError(f"I2V_PROVIDER_CHAIN_EXHAUSTED: {reasons}")


@dataclass
class CapabilityReport:
    """Readiness summary for one provider — mirrors capability_report shape."""

    provider: str
    ok: bool = False
    available: bool = False
    reason: str | None = None
    models: list[str] = field(default_factory=list)
    profile: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


class I2VProvider:
    """Base class for image-to-video motion providers.

    Subclasses set ``name`` and ``endpoints`` and implement :meth:`probe` and
    :meth:`build_command` (and optionally :meth:`generate`).
    """

    name: str = "base"
    command_timeout_sec: int = 600
    # source_endpoint labels this provider owns (subset of ALLOWED_VIDEO_ENDPOINTS)
    endpoints: frozenset[str] = frozenset()

    def probe(self, *, root: Path | None = None) -> CapabilityReport:  # pragma: no cover
        raise NotImplementedError

    def build_command(
        self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any
    ) -> list[str]:  # pragma: no cover
        """Return the shell command that generates a clip, or raise if unsupported."""
        raise NotImplementedError

    def generate(self, *, keyframe: Path, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Execute generation. Default: run :meth:`build_command` and return receipt.

        Concrete providers may override to talk to in-session Grok SDKs or async APIs.
        """
        cmd = self.build_command(keyframe=keyframe, prompt=prompt, **kwargs)
        if not cmd:
            raise I2VProviderError(f"{self.name}: build_command returned empty")
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.command_timeout_sec,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise I2VProviderError(f"{self.name}: subprocess failed: {exc}") from exc
        ok = proc.returncode == 0
        return {
            "provider": self.name,
            "ok": ok,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[:500],
            "stderr": (proc.stderr or "")[:500],
        }


class GrokI2VProvider(I2VProvider):
    """Grok Video 1.5 frame-1 I2V fallback."""

    name = "grok"
    endpoints = frozenset({"image_to_video", "reference_to_video"})
    model = "grok-imagine-video-1.5"

    def probe(self, *, root: Path | None = None) -> CapabilityReport:
        # A no-root probe describes the in-session Build capability. For a film
        # root, only a hash-bound live canary may claim batch readiness.
        if root is not None:
            receipt = Path(root) / "receipts" / "grok-i2v-canary.json"
            if not receipt.is_file():
                return CapabilityReport(
                    provider=self.name,
                    ok=False,
                    available=False,
                    reason="Grok I2V canary not run for this film root.",
                    models=[self.model],
                    profile="grok_primary",
                    detail={"canary_required": True, "receipt": str(receipt)},
                )
            try:

                from util import soft_json

                data = soft_json(receipt)
                recorded_model = str(data.get("provider_model") or data.get("model") or "").strip()
                available = bool(
                    data.get("ok")
                    and recorded_model == self.model
                    and _canary_output_is_bound(Path(root), data)
                    and _canary_media_is_approved(Path(root), data)
                )
                return CapabilityReport(
                    provider=self.name,
                    ok=available,
                    available=available,
                    reason="Grok I2V live canary passed."
                    if available
                    else "Grok Video 1.5 canary failed or is not verified for this model.",
                    models=[self.model],
                    profile="grok_primary",
                    detail=data,
                )
            except (OSError, ValueError) as exc:
                return CapabilityReport(
                    provider=self.name,
                    ok=False,
                    available=False,
                    reason=f"Grok I2V canary unreadable: {exc}",
                    models=["image_to_video", "reference_to_video"],
                    profile="grok_primary",
                )
        return CapabilityReport(
            provider=self.name,
            ok=True,
            available=True,
            reason="Grok image_to_video is ready as the second action lane.",
            models=[self.model],
            profile="grok_primary",
        )

    def build_command(
        self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any
    ) -> list[str]:
        # Grok I2V is invoked via the in-session Grok SDK or grok-oauth adapter,
        # not a standalone CLI. We expose the adapter path for batch use.
        adapter = Path(__file__).resolve().parent.parent / "adapters" / "grok_oauth_video.py"
        out = kwargs.get("out")
        if not out:
            raise I2VProviderError("grok batch I2V requires an explicit output path")
        command = [
            "python3",
            str(adapter),
            "--image",
            str(keyframe),
            "--model",
            self.model,
            "--prompt",
            prompt,
            "--duration",
            str(duration_sec),
            "--out",
            str(Path(out).expanduser().resolve()),
        ]
        reference_images = kwargs.get("reference_images") or []
        if isinstance(reference_images, (str, Path)):
            reference_images = [reference_images]
        for reference in reference_images:
            command.extend(("--ref", str(Path(reference).expanduser().resolve())))
        return command


class FrwRemoteProvider(I2VProvider):
    """Shared FRW upload + subprocess runner for live FRW lanes (not Seedance bulk).

    Subclasses implement :meth:`build_command` only. Seedance bulk is a separate
    retired class (:class:`SeedanceProvider`) and is **not** registered by default.
    """

    def generate(self, *, keyframe: Path, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Upload local inputs before invoking FRW; never pass local paths as URLs."""
        from frw_upload import upload_typed_inputs

        params = dict(kwargs)
        params.pop("out", None)
        handoff = upload_typed_inputs(
            keyframe,
            end=Path(params.pop("img2_path")) if params.get("img2_path") else None,
            category="image",
        )
        params["img_url"] = handoff["start_url"]
        if handoff.get("end_url"):
            params["img2_url"] = handoff["end_url"]
        cmd = self.build_command(keyframe=keyframe, prompt=prompt, **params)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
        except (OSError, subprocess.SubprocessError) as exc:
            raise I2VProviderError(f"{self.name}: subprocess failed: {exc}") from exc
        return {
            "provider": self.name,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[:500],
            "stderr": (proc.stderr or "")[:500],
            "input_sha256": sha256_file(keyframe),
            "uploaded_input": True,
            "input_mode": handoff["input_mode"],
            "pair_checksum": handoff.get("pair_checksum"),
        }


class SeedanceProvider(FrwRemoteProvider):
    """Retired Seedance bulk lane — **not registered** unless AIFILM_ALLOW_SEEDANCE=1.

    Prefer ``comfy-h3`` / ``frw-api-i2v``. Kept for hard-compat imports + escape only.
    """

    name = "seedance"
    endpoints = frozenset(
        {
            "frw_seedance_i2v",
            "frw_seedance_flf",
            "frw_seedance_lipsync",
        }
    )
    MODELS = {
        "i2v": "seedance-2-fast-i2v",
        "flf": "seedance-2-pro-flf",
        "lipsync": "seedance-2-pro-lipsync",
    }

    def probe(self, *, root: Path | None = None) -> CapabilityReport:
        del root
        return CapabilityReport(
            provider=self.name,
            ok=False,
            available=False,
            reason="SEEDANCE_RETIRED: not on default spine (use comfy-h3 / frw-api-i2v)",
            models=list(self.MODELS.values()),
            profile="retired",
            detail={"retired": True, "escape": "AIFILM_ALLOW_SEEDANCE=1"},
        )

    def build_command(
        self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any
    ) -> list[str]:
        model = self.MODELS.get(str(kwargs.get("variant") or "i2v"), self.MODELS["i2v"])
        dispatch = Path(__file__).resolve().parent.parent / "frw_dispatch.py"
        cmd = [
            "python3",
            str(dispatch),
            "newvideo",
            "--model",
            model,
            "--img-url",
            str(kwargs.get("img_url") or keyframe),
            "--prompt",
            prompt,
            "--aspect-ratio",
            str(kwargs.get("aspect", "9:16")),
            "--resolution",
            str(kwargs.get("resolution", "720p")),
            "--duration",
            str(duration_sec),
            "--wait",
        ]
        if kwargs.get("img2_url"):
            cmd += ["--img2-url", str(kwargs["img2_url"])]
        return cmd

    def generate(self, *, keyframe: Path, prompt: str, **kwargs: Any) -> dict[str, Any]:
        if not _env_truthy("AIFILM_ALLOW_SEEDANCE"):
            raise I2VProviderError(
                "SEEDANCE_RETIRED: not on default spine (use comfy-h3 / grok / frw-api-i2v). "
                "Escape only with AIFILM_ALLOW_SEEDANCE=1 for explicit recovery."
            )
        return super().generate(keyframe=keyframe, prompt=prompt, **kwargs)


class FrwImg2VideoProvider(FrwRemoteProvider):
    """Film-scoped FRW API ``img2video`` lane.

    FRW exposes this as a generic API, not a Wan/Seedance selector.  A passed
    canary records the actual returned model and terminal media evidence.
    """

    name = "frw-api-i2v"
    endpoints = frozenset({"frw_img2video"})

    def probe(self, *, root: Path | None = None) -> CapabilityReport:
        if root is None:
            return CapabilityReport(
                provider=self.name,
                ok=False,
                available=False,
                reason="FRW API I2V requires a film-scoped approved canary.",
                models=["img2video"],
                profile="frw_api_fallback",
                detail={"canary_required": True},
            )
        receipt = root / "receipts" / "frw-api-i2v-canary.json"
        from util import soft_json

        data = soft_json(receipt)
        approved = bool(
            data.get("ok")
            and _canary_output_is_bound(root, data)
            and _canary_media_is_approved(root, data)
            and data.get("full_decode_ok") is True
            and data.get("human_review") == "approved"
            and str(data.get("provider_model") or data.get("model") or "").strip()
        )
        return CapabilityReport(
            provider=self.name,
            ok=approved,
            available=approved,
            reason=(
                "FRW API I2V canary approved."
                if approved
                else "FRW API I2V canary is missing, unapproved, or lacks returned model identity."
            ),
            models=[str(data.get("provider_model") or data.get("model") or "img2video")],
            profile="frw_api_fallback",
            detail={"canary_required": True, "receipt": str(receipt), **data},
        )

    def build_command(
        self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any
    ) -> list[str]:
        del duration_sec
        dispatch = Path(__file__).resolve().parent.parent / "frw_dispatch.py"
        return [
            "python3",
            str(dispatch),
            "img2video",
            "--img-url",
            str(kwargs.get("img_url") or keyframe),
            "--prompt",
            prompt,
            "--width",
            str(kwargs.get("width", 704)),
            "--height",
            str(kwargs.get("height", 1280)),
            "--wait",
        ]


class FrwLtx23AudioProvider(FrwRemoteProvider):
    """FRW LTX 2.3 prompt-conditioned native-audio I2V production lane."""

    name = "frw-ltx23"
    endpoints = frozenset({"frw_ltx23_img2video_audio"})
    command_timeout_sec = 900

    def probe(self, *, root: Path | None = None) -> CapabilityReport:
        if root is None:
            return CapabilityReport(
                provider=self.name,
                ok=False,
                available=False,
                reason="LTX 2.3 requires a film-scoped approved native-audio canary.",
                models=["ltx-2.3", "img2video-audio"],
                profile="ltx23_primary",
                detail={"canary_required": True},
            )
        receipt = root / "receipts" / "frw-ltx23-i2v-audio-canary.json"
        from util import soft_json

        data = soft_json(receipt)
        approved = bool(
            data.get("ok")
            and _canary_output_is_bound(root, data)
            and data.get("full_decode_ok") is True
            and data.get("human_review") == "approved"
        )
        return CapabilityReport(
            provider=self.name,
            ok=approved,
            available=approved,
            reason=(
                "LTX 2.3 native-audio I2V canary approved."
                if approved
                else "LTX 2.3 native-audio canary missing or not fully approved."
            ),
            models=["ltx-2.3", "img2video-audio"],
            profile="ltx23_primary",
            detail={"canary_required": True, "receipt": str(receipt), **data},
        )

    def build_command(
        self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any
    ) -> list[str]:
        dispatch = Path(__file__).resolve().parent.parent / "frw_dispatch.py"
        return [
            "python3",
            str(dispatch),
            "img2video-audio",
            "--img-url",
            str(kwargs.get("img_url") or keyframe),
            "--prompt",
            prompt,
            "--width",
            str(kwargs.get("width", 704)),
            "--height",
            str(kwargs.get("height", 1280)),
            "--duration",
            str(duration_sec),
            "--wait",
        ]


# --- retired providers (not registered; names kept for hard-compat imports) ---

FRW_WAN_I2V_RETIRED = "FRW_WAN_I2V_RETIRED: use frw-api-i2v or comfy-h3 instead"
WAN22_I2V_RETIRED_MSG = "WAN22_I2V_RETIRED: local Wan 2.2 I2V has been removed; use comfy-h3"


class FrwWanProvider(I2VProvider):
    """Tombstone — FRW Wan lane retired (not registered)."""

    name = "frw-wan"
    endpoints = frozenset({"frw_wan_i2v"})

    def __init__(self) -> None:
        raise I2VProviderError(FRW_WAN_I2V_RETIRED)

    def probe(self, *, root: Path | None = None) -> CapabilityReport:
        del root
        return CapabilityReport(
            provider=self.name, ok=False, available=False, reason="FRW_WAN_I2V_RETIRED", models=[], profile="retired"
        )

    def build_command(self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any) -> list[str]:
        del keyframe, prompt, duration_sec, kwargs
        raise I2VProviderError(FRW_WAN_I2V_RETIRED)


class LocalComfyWan22Provider(I2VProvider):
    """Tombstone — local Wan 2.2 I2V removed (not registered); motion primary is MiniMax H3."""

    name = "comfy-wan22"
    command_timeout_sec = 30
    endpoints = frozenset({"local_wan22_i2v"})

    def __init__(self) -> None:
        raise I2VProviderError(WAN22_I2V_RETIRED_MSG)

    def probe(self, *, root: Path | None = None) -> CapabilityReport:
        del root
        return CapabilityReport(
            provider=self.name, ok=False, available=False, reason="WAN22_I2V_RETIRED", models=[], profile="retired"
        )

    def build_command(self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any) -> list[str]:
        del keyframe, prompt, duration_sec, kwargs
        raise I2VProviderError(WAN22_I2V_RETIRED_MSG)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, I2VProvider] = {}


def register(provider: I2VProvider) -> I2VProvider:
    """Register a provider instance by its ``name``."""
    _REGISTRY[provider.name] = provider
    return provider


def get(name: str) -> I2VProvider:
    if name not in _REGISTRY:
        hint = ""
        if name == "seedance":
            hint = (
                " Seedance bulk spine is retired (2026-08-07); use comfy-h3 or frw-api-i2v. "
                "Escape only: AIFILM_ALLOW_SEEDANCE=1 then re-import/register."
            )
        raise I2VProviderError(
            f"unknown I2V provider: {name} (registered: {list(_REGISTRY)}).{hint}"
        )
    return _REGISTRY[name]


def all_providers() -> dict[str, I2VProvider]:
    return dict(_REGISTRY)


def for_endpoint(source_endpoint: str) -> I2VProvider | None:
    """Resolve an existing ``source_endpoint`` label to its owning provider."""
    for provider in _REGISTRY.values():
        if source_endpoint in provider.endpoints:
            return provider
    return None


def _resolve_profile_for_routing() -> str:
    try:
        from film_spec import resolve_i2v_profile

        return resolve_i2v_profile()
    except Exception:
        return "h3_primary"


def provider_priority() -> tuple[str, ...]:
    """Return the profile-aware production action order.

    Free-local ``h3_primary``: local MiniMax H3 first, Grok Video 1.5 last (兜底).
    Quality/human/moderation failures never auto-advance the chain — only
    :func:`is_technical_failure` errors do, and each switch writes a signed receipt.
    """
    profile = _resolve_profile_for_routing()
    if profile == "h3_primary":
        return H3_PRIMARY_PROVIDER_PRIORITY
    if profile in {"grok_primary", "hybrid_h3"}:
        return GROK_PRIMARY_PROVIDER_PRIORITY
    # ltx23_primary / ltx23_adult / any residual cloud-chain profile
    return ACTION_PROVIDER_PRIORITY


def preferred(*, root: Path | None = None) -> I2VProvider:
    """Resolve the configured production primary without overriding shot locks."""
    try:
        from film_spec import default_i2v_provider, resolve_i2v_profile

        profile = resolve_i2v_profile()
        primary_name = default_i2v_provider()
    except Exception:
        profile = "h3_primary"
        primary_name = "comfy-h3"
    requested = profile
    try:
        provider = get(primary_name)
    except I2VProviderError:
        provider = get("comfy-h3" if profile == "h3_primary" else "grok")
    if root is not None:
        if provider.name == "comfy-h3":
            reason = (
                "h3_primary free-local: 5090 MiniMax H3 is film-wide motion primary; "
                "Grok Video 1.5 is technical/explicit 兜底 only (signed switch receipt)"
            )
        elif provider.name == "grok":
            reason = (
                "Grok Video 1.5 bulk (grok_primary / hybrid_h3 soft lane); "
                "not the free-local default — use AIFILM_I2V_PROFILE=h3_primary for 5090"
            )
        else:
            reason = (
                "explicit ltx23 compatibility profile: FRW LTX → FRW API I2V → "
                "Grok Video 1.5 technical fallback"
            )
        write_json(
            Path(root) / "receipts" / "i2v-routing.json",
            {
                "schema_version": 2,
                "kind": "i2v-routing-preflight",
                "requested_profile": requested,
                "selected_provider": provider.name,
                "provider_priority": list(provider_priority()),
                "fallback": False,
                "reason": reason,
                "models": list(provider.probe(root=root).models),
                "requires_hero_repilot": False,
            },
        )
    return provider


def registry_report(*, root: Path | None = None) -> dict[str, Any]:
    """Build a capability summary across all registered providers."""
    entries = []
    for name, provider in _REGISTRY.items():
        try:
            report = provider.probe(root=root)
        except Exception as exc:  # pragma: no cover — defensive
            report = CapabilityReport(provider=name, ok=False, reason=str(exc)[:200])
        entries.append(
            {
                "name": name,
                "endpoints": sorted(provider.endpoints),
                "available": report.available,
                "ok": report.ok,
                "reason": report.reason,
                "models": report.models,
                "profile": report.profile,
            }
        )
    active = preferred(root=root)
    return {
        "schema_version": 1,
        "kind": "i2v-provider-registry",
        "providers": entries,
        "active": active.name,
        "registered": sorted(_REGISTRY),
    }


class LocalComfyH3Provider(I2VProvider):
    """Private-LAN MiniMax H3 motion lane on the RTX 5090 ComfyUI node.

    Uses armory-compiled native MiniMaxH3 workflows (T2V/I2V/R2V). Does not
    revive the retired Wan 2.2 local I2V path. Generation remains pilot-gated
    until weapons are production-promoted.
    """

    name = "comfy-h3"
    command_timeout_sec = 3600
    endpoints = frozenset(
        {
            "local_minimax_h3_t2v",
            "local_minimax_h3_i2v",
            "local_minimax_h3_r2v",
        }
    )

    def _base_url(self) -> str:
        from config_loader import get_config

        return get_config().comfyui_base_url.strip()

    @staticmethod
    def _resolve_weapon(mode: str) -> tuple[str, str]:
        normalized = str(mode or "i2v").strip().lower()
        if normalized in {"t2v", "text-to-video", "text_to_video"}:
            return "text-to-video", "minimax-h3-t2v-pilot"
        if normalized in {"r2v", "reference-to-video", "reference_to_video"}:
            return "reference-to-video", "minimax-h3-r2v-pilot"
        return "image-to-video", "minimax-h3-i2v-pilot"

    def probe(self, *, root: Path | None = None) -> CapabilityReport:
        del root
        base_url = self._base_url()
        if not base_url:
            return CapabilityReport(
                provider=self.name,
                ok=False,
                available=False,
                reason="AIFILM_COMFYUI_BASE_URL is not configured.",
                models=[],
                profile="explicit_local_h3",
            )
        try:
            from comfy_armory import probe_armory
            from comfy_video import probe, submission_capacity

            detail = probe(base_url)
            capacity = submission_capacity(base_url)
            armory = probe_armory(base_url)
        except Exception as exc:
            return CapabilityReport(
                provider=self.name,
                ok=False,
                available=False,
                reason=f"MiniMax H3 probe failed: {exc}",
                models=[],
                profile="explicit_local_h3",
            )
        ready = [
            item["id"]
            for item in armory.get("ready", [])
            if str(item.get("id") or "").startswith("minimax-h3-")
        ]
        available = bool(detail.get("ok") and ready)
        return CapabilityReport(
            provider=self.name,
            ok=available,
            available=available,
            reason=(
                f"MiniMax H3 ready weapons: {', '.join(ready)}"
                if available
                else "MiniMax H3 weapons missing weights or live probe failed"
            ),
            models=ready,
            profile="explicit_local_h3",
            detail={
                **detail,
                "submission_capacity": capacity,
                "ready_h3_weapons": ready,
                "armory_blocked": armory.get("blocked"),
            },
        )

    def build_command(
        self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any
    ) -> list[str]:
        raise I2VProviderError(
            "comfy-h3 does not expose a raw shell command; call generate() which uses "
            "armory compile + comfy run-workflow"
        )

    def generate(self, *, keyframe: Path, prompt: str, **kwargs: Any) -> dict[str, Any]:
        import secrets

        from comfy_armory import (
            assert_registered_weapon_workflow,
            authorize_weapon_execution,
            compile_weapon_workflow,
            select_weapon,
        )
        from comfy_video import download_result, submit, upload_image, wait_for_result

        base_url = self._base_url()
        if not base_url:
            raise I2VProviderError("AIFILM_COMFYUI_BASE_URL is required for comfy-h3")
        out = kwargs.get("out")
        if not out:
            raise I2VProviderError("comfy-h3 requires an explicit output path")
        out_path = Path(out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        mode = str(kwargs.get("mode") or kwargs.get("operation") or "i2v")
        intent, weapon_id = self._resolve_weapon(mode)
        allow_experimental = bool(kwargs.get("allow_experimental", True))
        stage = str(kwargs.get("production_stage") or "pilot")
        try:
            select_weapon(
                intent,
                stage=stage,
                allow_experimental=allow_experimental,
            )
            authorize_weapon_execution(
                weapon_id,
                stage=stage,
                allow_experimental=allow_experimental,
            )
            input_image_name = kwargs.get("input_image_name")
            last_image_name = kwargs.get("last_image_name")
            last_frame = kwargs.get("last_frame") or kwargs.get("last_image")
            ref_image_names = kwargs.get("ref_image_names")
            reference_images = kwargs.get("reference_images") or []
            if isinstance(reference_images, (str, Path)):
                reference_images = [reference_images]
            if intent != "text-to-video":
                if not input_image_name:
                    remote = upload_image(base_url, Path(keyframe).expanduser().resolve())
                    input_image_name = remote.get("name") if isinstance(remote, dict) else remote
                if not input_image_name:
                    raise I2VProviderError("comfy-h3 failed to resolve uploaded input image name")
                if last_frame and not last_image_name:
                    last_path = Path(last_frame).expanduser().resolve()
                    if not last_path.is_file():
                        raise I2VProviderError(f"comfy-h3 last_frame missing: {last_path}")
                    remote_last = upload_image(base_url, last_path)
                    last_image_name = (
                        remote_last.get("name") if isinstance(remote_last, dict) else remote_last
                    )
                if reference_images and not ref_image_names:
                    uploaded_refs: list[str] = []
                    for ref in reference_images:
                        ref_path = Path(ref).expanduser().resolve()
                        if not ref_path.is_file():
                            raise I2VProviderError(f"comfy-h3 reference image missing: {ref_path}")
                        remote_ref = upload_image(base_url, ref_path)
                        name = (
                            remote_ref.get("name") if isinstance(remote_ref, dict) else remote_ref
                        )
                        if name:
                            uploaded_refs.append(str(name))
                    ref_image_names = uploaded_refs or None
            graph = compile_weapon_workflow(
                weapon_id,
                prompt=prompt,
                seed=int(kwargs.get("seed", 20260803)),
                input_image_name=str(input_image_name) if input_image_name else None,
                last_image_name=str(last_image_name) if last_image_name else None,
                ref_image_names=list(ref_image_names) if ref_image_names else None,
                filename_prefix=str(
                    kwargs.get("filename_prefix") or f"aifilm/h3/{weapon_id.replace('-', '_')}"
                ),
                steps=kwargs.get("steps"),
            )
            assert_registered_weapon_workflow(base_url, weapon_id, graph)
            client_id = f"aifilm-h3-{secrets.token_hex(6)}"
            prompt_id = submit(
                base_url,
                graph,
                client_id=client_id,
                weapon_id=weapon_id,
                allow_queue=bool(kwargs.get("enqueue", False)),
            )
            result = wait_for_result(
                base_url,
                prompt_id,
                client_id=client_id,
                timeout_sec=int(kwargs.get("timeout_sec", 1800)),
            )
            artifacts = result.get("artifacts") or []
            if not artifacts:
                raise I2VProviderError("comfy-h3 completed without downloadable artifacts")
            downloaded = download_result(base_url, artifacts[0], out_path)
        except Exception as exc:
            raise I2VProviderError(f"comfy-h3 generate failed: {exc}") from exc
        last_frame_path = kwargs.get("last_frame") or kwargs.get("last_image")
        receipt = {
            "schema_version": 1,
            "kind": "local-minimax-h3-generation",
            "ok": True,
            "provider": self.name,
            "weapon_id": weapon_id,
            "intent": intent,
            "mode": mode,
            "prompt_id": prompt_id,
            "output": downloaded,
            "source_endpoint": (
                "local_minimax_h3_t2v"
                if intent == "text-to-video"
                else "local_minimax_h3_r2v"
                if intent == "reference-to-video"
                else "local_minimax_h3_i2v"
            ),
            "input_provenance": {
                "first_image": str(Path(keyframe).expanduser().resolve()) if keyframe else None,
                "last_image": str(Path(last_frame_path).expanduser().resolve())
                if last_frame_path
                else None,
                "has_last_frame": bool(last_frame_path),
                "ref_count": len(
                    kwargs.get("reference_images") or kwargs.get("ref_image_names") or []
                ),
            },
        }
        receipt_path = out_path.with_suffix(out_path.suffix + ".receipt.json")
        write_json(receipt_path, receipt)
        return {
            "provider": self.name,
            "ok": True,
            "returncode": 0,
            "stdout": str(out_path),
            "stderr": "",
            "receipt": str(receipt_path),
            "prompt_id": prompt_id,
            "weapon_id": weapon_id,
            "source_endpoint": receipt["source_endpoint"],
            "input_provenance": receipt["input_provenance"],
        }


# Default registrations (importable side-effect).
# SeedanceProvider is **not** registered (2026-08-07 clear mind): bulk spine retired.
# Escape FRW img2video stays as frw-api-i2v; H3 owns motion primary.
# Class SeedanceProvider remains as base for Frw* providers + AIFILM_ALLOW_SEEDANCE recovery.
register(GrokI2VProvider())
register(FrwImg2VideoProvider())
register(FrwLtx23AudioProvider())
register(LocalComfyH3Provider())


def _register_seedance_escape_if_allowed() -> None:
    """Opt-in only: AIFILM_ALLOW_SEEDANCE=1 re-registers name=seedance for recovery."""
    if _env_truthy("AIFILM_ALLOW_SEEDANCE") and "seedance" not in _REGISTRY:
        register(SeedanceProvider())


_register_seedance_escape_if_allowed()
