#!/usr/bin/env python3
"""Sung-line providers for ai-film-grok — removes the HeartMuLa hard dependency.

 historically ``sung_beat`` audio could only be generated through the external
HeartMuLa backend wired via ``AIFILM_MUSIC_ARGV``. That made the whole
``sung_beat`` recipe degrade to ``narrate_bed`` whenever the external command
was not configured — an external-only capability gate.

This module breaks that gate by defining a small :class:`SungProvider`
abstraction with two concrete implementations:

* :class:`HeartMuLaSungProvider` — the original external backend
  (``AIFILM_MUSIC_ARGV``). High quality, *requires* an external command.
* :class:`LocalFallbackSungProvider` — a self-contained path that renders the
  lyric with one of the project's already-bundled **local** TTS adapters
  (CosyVoice preferred, then piper / kokoro / chatterbox) onto the musical
  bed. No external service, no network. The vocal is a sung-styled local TTS
  line (not a true singing model); set ``AIFILM_MUSIC_ARGV`` for HeartMuLa
  true-singing when available.

Selection is ``external if configured, else local`` via :func:`select_sung_provider`,
and :func:`sung_provider_ready` reports whether *any* provider is usable — so
``sung_beat`` is no longer blocked on an external dependency.

The provider is pure and injectable: tests can pass ``tts_callable`` to
:class:`LocalFallbackSungProvider` so synthesis runs offline.
"""

from __future__ import annotations

import importlib
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Local TTS adapters already bundled with the skill, in singing-capability order.
# Each exposes a module-level ``synthesize(text, out, voice)``. The second tuple
# element is an optional required env var; when set it must be present for the
# adapter to count as available.
_LOCAL_TTS_ADAPTERS: tuple[tuple[str, str | None], ...] = (
    ("cosyvoice_local_tts", "COSYVOICE_ROOT"),
    ("piper_local_tts", None),
    ("kokoro_tts", None),
    ("chatterbox_local_tts", None),
)

_LOCAL_SUNG_OPT_IN = "AIFILM_LOCAL_SUNG_PROVIDER"


class SungProviderError(RuntimeError):
    """Raised when a sung-line provider cannot synthesize."""


class SungProvider(ABC):
    """A sung-line (``sung_beat``) audio source."""

    name: str = "base"
    kind: str = "abstract"  # "external" | "local"

    @abstractmethod
    def is_available(self) -> bool:
        """True if this provider can actually produce audio in this environment."""

    @abstractmethod
    def synthesize_beat(
        self,
        *,
        text: str,
        out_path: Path,
        mood: str = "rnb",
        key: str = "C",
        tempo_bpm: float = 76.0,
        voice: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Render one sung beat. Returns a receipt dict with at least ``path``."""


def _detect_local_tts() -> tuple[str, Callable[..., Any]] | None:
    """Return (module_name, synthesize) for the first usable local TTS adapter."""
    for mod_name, required_env in _LOCAL_TTS_ADAPTERS:
        if required_env and not os.environ.get(required_env):
            continue
        try:
            mod = importlib.import_module(mod_name)
        except Exception:  # noqa: BLE001
            continue
        fn = getattr(mod, "synthesize", None)
        if callable(fn):
            return mod_name, fn
    return None


class HeartMuLaSungProvider(SungProvider):
    """External HeartMuLa / generative-music backend via ``AIFILM_MUSIC_ARGV``."""

    name = "heartmula"
    kind = "external"

    def is_available(self) -> bool:
        return bool((os.environ.get("AIFILM_MUSIC_ARGV") or "").strip())

    def synthesize_beat(
        self,
        *,
        text: str,
        out_path: Path,
        mood: str = "rnb",
        key: str = "C",
        tempo_bpm: float = 76.0,
        voice: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not self.is_available():
            raise SungProviderError(
                "HeartMuLa provider unavailable: set AIFILM_MUSIC_ARGV "
                "(see adapters/music_external.py)"
            )
        out_path = Path(out_path)
        try:
            from security_policy import (  # type: ignore
                expand_argv,
                minimal_subprocess_env,
                parse_argv_json,
            )
        except Exception as exc:  # pragma: no cover - security_policy always present
            raise SungProviderError(f"cannot load security_policy: {exc}") from exc

        raw = os.environ["AIFILM_MUSIC_ARGV"]
        template = parse_argv_json(raw, variable="AIFILM_MUSIC_ARGV")
        prompt = (
            os.environ.get("AIFILM_MUSIC_PROMPT")
            or f"vocal line, {mood}, sung, key {key}, {tempo_bpm:.0f} bpm, cinematic"
        )
        argv = expand_argv(
            template,
            {
                "out": str(out_path),
                "duration": f"{float(kwargs.get('duration', 8.0)):.3f}",
                "mood": str(mood),
                "seed": str(int(kwargs.get("seed", 0))),
                "prompt": prompt,
                "title": str(kwargs.get("title", "")),
                "text": str(text),
                "voice": str(voice),
            },
            variable="AIFILM_MUSIC_ARGV",
        )
        import subprocess

        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env=minimal_subprocess_env(),
            timeout=float(os.environ.get("AIFILM_MUSIC_TIMEOUT") or 600),
        )
        if proc.returncode != 0 or not out_path.is_file() or out_path.stat().st_size < 500:
            msg = (proc.stderr or proc.stdout or "")[-400:]
            raise SungProviderError(f"HeartMuLa gen failed: {msg}")
        return {
            "path": str(out_path.resolve()),
            "provider": self.name,
            "sung": True,
            "license_note": os.environ.get("AIFILM_MUSIC_LICENSE")
            or "external generative music (AIFILM_MUSIC_ARGV) — verify model license",
            "source": "external_music",
        }


class LocalFallbackSungProvider(SungProvider):
    """Self-contained sung-line renderer using a bundled local TTS adapter.

    No external service. Renders the lyric as a sung-styled local vocal on the
    musical bed. For true singing, configure ``AIFILM_MUSIC_ARGV`` (HeartMuLa).
    """

    name = "local_fallback"
    kind = "local"

    def __init__(self, tts_callable: Callable[..., Any] | None = None) -> None:
        # Injectable for offline tests; otherwise resolved from local adapters.
        self._tts = tts_callable

    def is_available(self) -> bool:
        if self._tts is not None:
            return True
        if os.environ.get(_LOCAL_SUNG_OPT_IN):
            return True
        return _detect_local_tts() is not None

    def _resolve_tts(self) -> tuple[str, Callable[..., Any]]:
        if self._tts is not None:
            return "injected", self._tts
        detected = _detect_local_tts()
        if detected is None:
            raise SungProviderError(
                "no local TTS adapter available; install CosyVoice/piper/kokoro/"
                "chatterbox or set AIFILM_LOCAL_SUNG_PROVIDER / AIFILM_MUSIC_ARGV"
            )
        return detected

    def synthesize_beat(
        self,
        *,
        text: str,
        out_path: Path,
        mood: str = "rnb",
        key: str = "C",
        tempo_bpm: float = 76.0,
        voice: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        out_path = Path(out_path)
        mod_name, fn = self._resolve_tts()
        try:
            fn(text, out_path, voice)
        except TypeError:
            # Some adapters take (text, out) only.
            fn(text, out_path)
        if not out_path.is_file() or out_path.stat().st_size < 1:
            raise SungProviderError(f"local TTS produced no audio at {out_path}")
        return {
            "path": str(out_path.resolve()),
            "provider": self.name,
            "tts_adapter": mod_name,
            "sung": False,
            "note": (
                "local TTS vocal on music bed (not true singing); "
                "set AIFILM_MUSIC_ARGV for HeartMuLa true-singing"
            ),
            "source": "local_sung_fallback",
        }


def list_sung_providers() -> list[SungProvider]:
    """All known providers, in selection priority order (external first)."""
    return [HeartMuLaSungProvider(), LocalFallbackSungProvider()]


def select_sung_provider() -> SungProvider | None:
    """Return the best available provider, or ``None`` if none usable."""
    for provider in list_sung_providers():
        if provider.is_available():
            return provider
    return None


def sung_provider_ready() -> bool:
    """True when at least one sung-line provider is usable in this environment."""
    return select_sung_provider() is not None
