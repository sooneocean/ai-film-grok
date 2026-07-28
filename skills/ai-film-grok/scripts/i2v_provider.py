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

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from util import sha256_file, write_json


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
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
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
