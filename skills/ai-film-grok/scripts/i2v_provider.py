#!/usr/bin/env python3
"""I2V provider abstraction and action-routing layer.

Runs the production action order FRW LTX 2.3 → Grok I2V → verified FRW Wan →
verified local providers behind a single interface. New providers can be added
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
import sys
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
ACTION_PROVIDER_PRIORITY = (
    "frw-ltx23",
    "grok",
    "frw-wan",
    "comfy-wan22",
)


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
    if primary not in ACTION_PROVIDER_PRIORITY or not is_technical_failure(error):
        return None
    try:
        stable_shot_id = validate_identifier(shot_id, field="shot id")
    except SecurityPolicyError as exc:
        raise I2VProviderError(f"PROVIDER_SWITCH_SHOT_ID_INVALID: {exc}") from exc
    if fallback_name is None:
        try:
            fallback_name = ACTION_PROVIDER_PRIORITY[ACTION_PROVIDER_PRIORITY.index(primary) + 1]
        except (ValueError, IndexError):
            return None
    if fallback_name not in ACTION_PROVIDER_PRIORITY:
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
    """Grok Build image_to_video — frame-1 I2V (default when Seedance unavailable)."""

    name = "grok"
    endpoints = frozenset({"image_to_video", "reference_to_video"})

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
                    models=["image_to_video", "reference_to_video"],
                    profile="grok_primary",
                    detail={"canary_required": True, "receipt": str(receipt)},
                )
            try:
                import json

                data = json.loads(receipt.read_text(encoding="utf-8"))
                available = bool(data.get("ok") and _canary_output_is_bound(Path(root), data))
                return CapabilityReport(
                    provider=self.name,
                    ok=available,
                    available=available,
                    reason="Grok I2V live canary passed."
                    if available
                    else "Grok I2V canary failed.",
                    models=["image_to_video", "reference_to_video"],
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
            models=["image_to_video", "reference_to_video"],
            profile="grok_primary",
        )

    def build_command(
        self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any
    ) -> list[str]:
        # Grok I2V is invoked via the in-session Grok SDK or grok-oauth adapter,
        # not a standalone CLI. We expose the adapter path for batch use.
        adapter = Path(__file__).resolve().parent / "adapters" / "grok_oauth_video.py"
        out = kwargs.get("out")
        if not out:
            raise I2VProviderError("grok batch I2V requires an explicit output path")
        command = [
            "python3",
            str(adapter),
            "--image",
            str(keyframe),
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


class SeedanceProvider(I2VProvider):
    """FRW Seedance bulk I2V (seedance-2-fast-i2v / pro-flf / pro-lipsync)."""

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
        # Read FRW canary receipt if root given; otherwise probe frw_dispatch presence.
        if root is not None:
            receipt = root / "receipts" / "frw-key-capability.json"
            if receipt.is_file():
                try:
                    import json

                    data = json.loads(receipt.read_text(encoding="utf-8"))
                    code = data.get("code") or data.get("status_code")
                    available = str(code) == "201" or bool(data.get("success"))
                    return CapabilityReport(
                        provider=self.name,
                        ok=available,
                        available=available,
                        reason=f"FRW canary code={code}",
                        models=list(self.MODELS.values()),
                        profile="seedance_first" if available else "grok_primary",
                        detail=data,
                    )
                except OSError:
                    pass
        # Resolving the adapter is not a provider canary. Keep it unavailable
        # until a receipt proves the endpoint actually accepted a request.
        try:
            from frw_dispatch import resolve_frw_root

            resolve_frw_root()
            return CapabilityReport(
                provider=self.name,
                ok=False,
                available=False,
                reason="frwclaw-pro resolvable, but Seedance canary not run.",
                models=list(self.MODELS.values()),
                profile="grok_primary",
                detail={"canary_required": True},
            )
        except SystemExit as exc:
            return CapabilityReport(
                provider=self.name,
                ok=False,
                available=False,
                reason=str(exc)[:200],
                models=list(self.MODELS.values()),
                profile="grok_primary",
            )

    def build_command(
        self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any
    ) -> list[str]:
        model = self.MODELS.get(str(kwargs.get("variant") or "i2v"), self.MODELS["i2v"])
        dispatch = Path(__file__).resolve().parent / "frw_dispatch.py"
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


class FrwImg2VideoProvider(SeedanceProvider):
    """The original FRW ``img2video`` fallback, without Seedance selection."""

    name = "frw-img2video"
    endpoints = frozenset({"frw_img2video"})

    def probe(self, *, root: Path | None = None) -> CapabilityReport:
        del root
        try:
            from frw_dispatch import resolve_frw_root

            resolve_frw_root()
        except SystemExit as exc:
            return CapabilityReport(
                provider=self.name,
                ok=False,
                available=False,
                reason=str(exc)[:200],
                models=["img2video"],
                profile="frw_fallback",
            )
        return CapabilityReport(
            provider=self.name,
            ok=False,
            available=False,
            reason="FRW img2video is resolvable; a current film canary is still required.",
            models=["img2video"],
            profile="frw_fallback",
            detail={"canary_required": True},
        )

    def build_command(
        self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any
    ) -> list[str]:
        del duration_sec
        dispatch = Path(__file__).resolve().parent / "frw_dispatch.py"
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


class FrwLtx23AudioProvider(SeedanceProvider):
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
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
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
        dispatch = Path(__file__).resolve().parent / "frw_dispatch.py"
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


class FrwWanProvider(SeedanceProvider):
    """FRW-managed I2V accepted only when the response proves a Wan backend.

    The current public FRW CLI exposes a generic ``img2video`` command, not a
    model selector.  This lane therefore stays unavailable until a film-scoped
    canary and every generation response both identify Wan explicitly.
    """

    name = "frw-wan"
    endpoints = frozenset({"frw_wan_i2v"})

    def probe(self, *, root: Path | None = None) -> CapabilityReport:
        if root is None:
            return CapabilityReport(
                provider=self.name,
                ok=False,
                available=False,
                reason="FRW Wan requires a film-scoped model-identity canary.",
                models=["wan"],
                profile="frw_wan_fallback",
                detail={"canary_required": True},
            )
        receipt = root / "receipts" / "frw-wan-i2v-canary.json"
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        model = str(data.get("provider_model") or data.get("model") or "").lower()
        approved = bool(
            data.get("ok")
            and _has_wan_model_identity(model)
            and _canary_output_is_bound(root, data)
            and data.get("full_decode_ok") is True
            and data.get("human_review") == "approved"
        )
        return CapabilityReport(
            provider=self.name,
            ok=approved,
            available=approved,
            reason=(
                "FRW Wan I2V canary approved."
                if approved
                else "FRW Wan model identity is not exposed or the canary is not approved."
            ),
            models=["wan"],
            profile="frw_wan_fallback",
            detail={"canary_required": True, "receipt": str(receipt), **data},
        )

    def build_command(
        self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any
    ) -> list[str]:
        del duration_sec
        dispatch = Path(__file__).resolve().parent / "frw_dispatch.py"
        return [
            sys.executable,
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

    def generate(self, *, keyframe: Path, prompt: str, **kwargs: Any) -> dict[str, Any]:
        result = super().generate(keyframe=keyframe, prompt=prompt, **kwargs)
        payload: dict[str, Any] = {}
        for line in reversed(str(result.get("stdout") or "").splitlines()):
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                payload = parsed
                break
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        model = str(
            data.get("model") or data.get("provider_model") or payload.get("model") or ""
        ).lower()
        if result.get("ok") and not _has_wan_model_identity(model):
            result["ok"] = False
            result["stderr"] = "FRW_WAN_MODEL_IDENTITY_UNVERIFIED"
        result["provider_model"] = model or None
        return result


class LocalComfyWan22Provider(I2VProvider):
    """Explicit private-LAN Wan 2.2 I2V lane on the user's RTX 5090."""

    name = "comfy-wan22"
    command_timeout_sec = 1830
    endpoints = frozenset({"local_wan22_i2v"})

    def _base_url(self) -> str:
        from config_loader import get_config

        return get_config().comfyui_base_url.strip()

    @staticmethod
    def _resolve_profile_name(kwargs: dict[str, Any]) -> str:
        from comfy_video import resolve_wan22_profile

        profile = resolve_wan22_profile(
            str(kwargs.get("profile") or "auto"),
            intent=str(kwargs.get("weapon_intent") or "general"),
            stage=str(kwargs.get("production_stage") or "production"),
            allow_experimental=bool(kwargs.get("allow_experimental")),
        )
        return str(profile["name"])

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
                profile="explicit_local",
            )
        try:
            from comfy_video import probe, submission_capacity

            detail = probe(base_url)
            capacity = submission_capacity(base_url)
        except Exception as exc:
            return CapabilityReport(
                provider=self.name,
                ok=False,
                available=False,
                reason=f"private ComfyUI probe failed: {exc}",
                models=[],
                profile="explicit_local",
            )
        models = list((detail.get("models") or {}).get("official") or [])
        available = bool(detail.get("ok") and capacity.get("ok"))
        return CapabilityReport(
            provider=self.name,
            ok=available,
            available=available,
            reason=(
                "Private RTX 5090 Wan 2.2 is ready."
                if available
                else "Private Wan 2.2 assets or submission capacity are unavailable."
            ),
            models=models,
            profile="explicit_local",
            detail={**detail, "submission_capacity": capacity},
        )

    def build_command(
        self, *, keyframe: Path, prompt: str, duration_sec: int = 5, **kwargs: Any
    ) -> list[str]:
        base_url = self._base_url()
        if not base_url:
            raise I2VProviderError("AIFILM_COMFYUI_BASE_URL is required for comfy-wan22")
        out = kwargs.get("out")
        if not out:
            raise I2VProviderError("comfy-wan22 requires an explicit output path")
        try:
            profile_name = self._resolve_profile_name(kwargs)
        except Exception as exc:
            raise I2VProviderError(str(exc)) from exc
        script = Path(__file__).resolve().parent / "comfy_video.py"
        command = [
            sys.executable,
            str(script),
            "generate",
            "--base-url",
            base_url,
            "--image",
            str(Path(keyframe).expanduser().resolve()),
            "--prompt",
            prompt,
            "--out",
            str(Path(out).expanduser().resolve()),
            "--duration",
            str(duration_sec),
            "--timeout",
            str(kwargs.get("timeout_sec", 1800)),
            "--width",
            str(kwargs.get("width", 480)),
            "--height",
            str(kwargs.get("height", 704)),
            "--seed",
            str(kwargs.get("seed", 123456)),
            "--profile",
            profile_name,
        ]
        if kwargs.get("turbo"):
            command.append("--turbo")
        if kwargs.get("subject_basis"):
            command.extend(("--subject-basis", str(kwargs["subject_basis"])))
        return command

    def generate(self, *, keyframe: Path, prompt: str, **kwargs: Any) -> dict[str, Any]:
        input_path = Path(keyframe).expanduser().resolve()
        expected_input_sha = sha256_file(input_path) if input_path.is_file() else None
        result = super().generate(keyframe=keyframe, prompt=prompt, **kwargs)
        out = Path(kwargs["out"]).expanduser().resolve()
        receipt = out.with_suffix(out.suffix + ".receipt.json")
        result["receipt"] = str(receipt)
        if result.get("ok") and receipt.is_file():
            try:
                from comfy_video import (
                    WAN22_ADULT_ACTION_EXPERIMENTAL_PROFILE,
                    WAN22_ADULT_PROFILE,
                    WAN22_GENERAL_ADULT_EXPERIMENTAL_PROFILE,
                    WAN22_OFFICIAL_PROFILE,
                )

                detail = json.loads(receipt.read_text(encoding="utf-8"))
                profile_name = self._resolve_profile_name(kwargs)
                profile = {
                    WAN22_ADULT_PROFILE["name"]: WAN22_ADULT_PROFILE,
                    WAN22_ADULT_ACTION_EXPERIMENTAL_PROFILE[
                        "name"
                    ]: WAN22_ADULT_ACTION_EXPERIMENTAL_PROFILE,
                    WAN22_GENERAL_ADULT_EXPERIMENTAL_PROFILE[
                        "name"
                    ]: WAN22_GENERAL_ADULT_EXPERIMENTAL_PROFILE,
                }.get(profile_name, WAN22_OFFICIAL_PROFILE)
                expected_models = [profile["high"], profile["low"]]
                expected_loras = (
                    [name for name in (profile.get("high_lora"), profile.get("low_lora")) if name]
                    if kwargs.get("turbo") or profile_name.endswith("-experimental")
                    else []
                )
                output_detail = detail.get("output") or {}
                verification_errors: list[str] = []
                if detail.get("schema_version") != 1:
                    verification_errors.append("schema version mismatch")
                if detail.get("kind") != "local-wan22-generation":
                    verification_errors.append("receipt kind mismatch")
                if expected_input_sha is None:
                    verification_errors.append("input file was missing before launch")
                elif detail.get("input_sha256") != expected_input_sha:
                    verification_errors.append("input SHA-256 mismatch")
                if not out.is_file():
                    verification_errors.append("output file is missing")
                else:
                    if output_detail.get("sha256") != sha256_file(out):
                        verification_errors.append("output SHA-256 mismatch")
                    if output_detail.get("bytes") != out.stat().st_size:
                        verification_errors.append("output byte count mismatch")
                if Path(str(output_detail.get("path") or "")).expanduser().resolve() != out:
                    verification_errors.append("output path mismatch")
                if detail.get("provider") != self.name or detail.get("ok") is not True:
                    verification_errors.append("provider receipt identity mismatch")
                if detail.get("profile") != profile_name:
                    verification_errors.append("profile mismatch")
                if detail.get("models") != expected_models:
                    verification_errors.append("model identity mismatch")
                if list(detail.get("loras") or []) != expected_loras:
                    verification_errors.append("LoRA identity mismatch")
                expected_lora_sha256 = {
                    name: str(profile[hash_key])
                    for name, hash_key in (
                        (profile.get("high_lora"), "high_lora_sha256"),
                        (profile.get("low_lora"), "low_lora_sha256"),
                    )
                    if name and hash_key in profile
                }
                if dict(detail.get("lora_sha256") or {}) != expected_lora_sha256:
                    verification_errors.append("LoRA SHA-256 mismatch")
                if (
                    profile_name.endswith("-experimental")
                    and detail.get("experimental_assets_promoted") is not False
                ):
                    verification_errors.append("experimental promotion state mismatch")
                if not detail.get("prompt_id"):
                    verification_errors.append("prompt_id is missing")
                if profile_name.startswith("adult-"):
                    if detail.get("subject_basis") != kwargs.get("subject_basis"):
                        verification_errors.append("adult subject basis mismatch")
                    if detail.get("adult_attestation") is not True:
                        verification_errors.append("adult attestation is missing")
                if verification_errors:
                    raise ValueError("; ".join(verification_errors))
                result["prompt_id"] = detail.get("prompt_id")
                result["input_sha256"] = detail.get("input_sha256")
                result["output_sha256"] = output_detail.get("sha256")
                result["models"] = detail.get("models") or []
            except (OSError, ValueError) as exc:
                result["ok"] = False
                result["stderr"] = f"comfy-wan22 receipt verification failed: {exc}"
        elif result.get("ok"):
            result["ok"] = False
            result["stderr"] = "comfy-wan22 did not write a generation receipt"
        return result


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
        raise I2VProviderError(f"unknown I2V provider: {name} (registered: {list(_REGISTRY)})")
    return _REGISTRY[name]


def all_providers() -> dict[str, I2VProvider]:
    return dict(_REGISTRY)


def for_endpoint(source_endpoint: str) -> I2VProvider | None:
    """Resolve an existing ``source_endpoint`` label to its owning provider."""
    for provider in _REGISTRY.values():
        if source_endpoint in provider.endpoints:
            return provider
    return None


def provider_priority() -> tuple[str, ...]:
    """Return the production action order, followed by future verified locals."""
    local_tail = tuple(
        sorted(
            name
            for name in _REGISTRY
            if (name.startswith("comfy-") or name.startswith("local-"))
            and name not in ACTION_PROVIDER_PRIORITY
        )
    )
    return (*ACTION_PROVIDER_PRIORITY, *local_tail)


def preferred(*, root: Path | None = None) -> I2VProvider:
    """Resolve the configured production primary without overriding shot locks."""
    try:
        from film_spec import resolve_i2v_profile

        profile = resolve_i2v_profile()
    except Exception:
        profile = "ltx23_primary"
    requested = profile
    provider = get("frw-ltx23" if profile == "ltx23_primary" else "grok")
    if root is not None:
        write_json(
            Path(root) / "receipts" / "i2v-routing.json",
            {
                "schema_version": 2,
                "kind": "i2v-routing-preflight",
                "requested_profile": requested,
                "selected_provider": provider.name,
                "provider_priority": list(provider_priority()),
                "fallback": False,
                "reason": (
                    "FRW LTX 2.3 is first; later providers require live readiness and "
                    "attempted-provider switches require signed receipts"
                    if provider.name == "frw-ltx23"
                    else "legacy grok_primary compatibility profile"
                ),
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


# Default registrations (importable side-effect)
register(GrokI2VProvider())
register(SeedanceProvider())
register(FrwImg2VideoProvider())
register(FrwLtx23AudioProvider())
register(FrwWanProvider())
register(LocalComfyWan22Provider())
