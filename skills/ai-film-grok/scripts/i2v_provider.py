#!/usr/bin/env python3
"""I2V provider abstraction layer.

Unifies Grok image_to_video and FRW Seedance behind a single interface so new
providers can be added by implementing :class:`I2VProvider` and registering it,
instead of scattering string ``source_endpoint`` labels through ``frw_dispatch.py``
and ``capability_report.py``.

This module is the **registry + routing** layer; the actual generation still
delegates to the existing paths:

* Grok provider → Grok Build ``image_to_video`` (in-session) or
  ``scripts/adapters/grok_oauth_image.py``.
* Seedance provider → ``scripts/frw_dispatch.py`` (FRW newvideo seedance-*-i2v).

Backward-compatible: the existing ``source_endpoint`` labels in
``ALLOWED_VIDEO_ENDPOINTS`` keep working — the registry maps them to provider
instances rather than replacing them.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


def is_technical_failure(error: object) -> bool:
    """Return whether an error is safe to route from Grok to FRW.

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
    return any(marker in text for marker in TECHNICAL_FAILURE_MARKERS)


def _write_switch_receipt(
    root: Path | None,
    *,
    shot_id: str,
    primary: str,
    fallback: str,
    error: object,
) -> dict[str, Any]:
    receipt = {
        "schema_version": 1,
        "kind": "provider-switch",
        "shot_id": shot_id,
        "primary_provider": primary,
        "fallback_provider": fallback,
        "reason_class": "technical_failure",
        "error": str(error)[:500],
        "fallback_fixed_for_shot": True,
    }
    receipt["switch_sha256"] = canonical_json_sha256(receipt)
    if root is not None:
        path = Path(root).expanduser().resolve() / "receipts" / f"provider-switch-{shot_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, receipt)
        receipt["path"] = str(path)
    return receipt


def route_after_failure(
    *, root: Path | None, shot_id: str, primary: str, error: object
) -> tuple[I2VProvider, dict[str, Any]] | None:
    """Select FRW only after a classified Grok technical failure."""
    if primary != "grok" or not is_technical_failure(error):
        return None
    provider = get("seedance")
    return provider, _write_switch_receipt(
        root, shot_id=shot_id, primary=primary, fallback=provider.name, error=error
    )


def generate_with_fallback(
    *,
    root: Path | None,
    shot_id: str,
    keyframe: Path,
    prompt: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run Grok first and invoke FRW only for a classified technical failure."""
    primary = preferred(root=root)
    try:
        result = primary.generate(keyframe=keyframe, prompt=prompt, **kwargs)
        if not result.get("ok"):
            raise I2VProviderError(
                str(result.get("stderr") or result.get("error") or "Grok failed")
            )
        result["route"] = "grok_primary"
        return result
    except Exception as exc:
        selected = route_after_failure(root=root, shot_id=shot_id, primary=primary.name, error=exc)
        if selected is None:
            raise
        fallback, switch = selected
        result = fallback.generate(keyframe=keyframe, prompt=prompt, **kwargs)
        result["route"] = "frw_fallback"
        result["provider_switch"] = switch
        return result


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
                available = bool(data.get("ok") and data.get("output_sha256"))
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
            reason="Grok image_to_video is the default in-session I2V (grok_primary).",
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
            from comfy_video import probe

            detail = probe(base_url)
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
        return CapabilityReport(
            provider=self.name,
            ok=bool(detail.get("ok")),
            available=bool(detail.get("ok")),
            reason="Private RTX 5090 Wan 2.2 is ready."
            if detail.get("ok")
            else "Required Wan 2.2 assets are missing.",
            models=models,
            profile="explicit_local",
            detail=detail,
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


def preferred(*, root: Path | None = None) -> I2VProvider:
    """Resolve Grok as the production primary provider.

    FRW is selected only through :func:`route_after_failure`, after a
    classified technical failure and a checksum-bound switch receipt.
    """
    try:
        from film_spec import resolve_i2v_profile

        profile = resolve_i2v_profile()
    except Exception:
        profile = "grok_primary"
    requested = profile
    provider = get("grok")
    if root is not None:
        write_json(
            Path(root) / "receipts" / "i2v-routing.json",
            {
                "schema_version": 1,
                "requested_profile": requested,
                "selected_provider": provider.name,
                "fallback": False,
                "reason": "grok_primary production default; FRW requires technical-failure switch",
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
register(LocalComfyWan22Provider())
