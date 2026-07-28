"""Fail-closed client for the private 5090 audio node."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from security_policy import atomic_write_bytes


class AudioNodeError(RuntimeError):
    pass


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


_PUBLIC_MODEL_FIELDS = (
    "model",
    "music_model",
    "music_checkpoint_fingerprint",
    "performance_model",
    "sfx_model",
    "sfx_checkpoint_fingerprint",
    "sfx_license",
)
_PUBLIC_GPU_FIELDS = ("available", "name", "cuda", "driver", "free_vram_mib", "total_vram_mib")
_PUBLIC_MODEL_KINDS = ("tts", "music", "sfx", "performance")


def public_health_report(raw: Any, *, secret_values: tuple[str, ...] = ()) -> dict[str, Any]:
    """Project an untrusted node health response to public capability fields only."""
    if not isinstance(raw, dict):
        return {"ok": False}
    public: dict[str, Any] = {"ok": raw.get("ok") is True}
    if raw.get("node") == "private-lan":
        public["node"] = "private-lan"
    models = raw.get("models")
    if isinstance(models, dict):
        public_models = {
            kind: models[kind] for kind in _PUBLIC_MODEL_KINDS if isinstance(models.get(kind), bool)
        }
        if public_models:
            public["models"] = public_models
    if isinstance(raw.get("music_batch"), bool):
        public["music_batch"] = raw["music_batch"]
    for field in _PUBLIC_MODEL_FIELDS:
        value = raw.get(field)
        if (
            isinstance(value, str)
            and len(value) <= 256
            and not any(secret and secret in value for secret in secret_values)
        ):
            public[field] = value
    gpu = raw.get("gpu")
    if isinstance(gpu, dict):
        public_gpu: dict[str, Any] = {}
        for field in _PUBLIC_GPU_FIELDS:
            value = gpu.get(field)
            if (
                field == "available"
                and isinstance(value, bool)
                or (
                    field in {"name", "cuda"}
                    and isinstance(value, str)
                    and len(value) <= 128
                    and not any(secret and secret in value for secret in secret_values)
                )
                or (
                    field == "driver"
                    and isinstance(value, str)
                    and bool(re.fullmatch(r"[0-9][0-9.]{0,30}", value))
                )
                or field.endswith("_mib")
                and isinstance(value, int)
                and value >= 0
            ):
                public_gpu[field] = value
        if public_gpu:
            public["gpu"] = public_gpu
    return public


def _json_response(payload: bytes, *, context: str) -> dict[str, Any]:
    try:
        data = json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AudioNodeError(f"audio node returned invalid {context} JSON") from exc
    if not isinstance(data, dict):
        raise AudioNodeError(f"audio node returned invalid {context} JSON")
    return data


def _url(base_url: str, path: str) -> str:
    if not base_url.startswith(("http://", "https://")):
        raise AudioNodeError("audio node URL must use http(s)")
    return base_url.rstrip("/") + path


def _request(
    base_url: str,
    token: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    raw_body: bytes | None = None,
    content_type: str = "application/json",
    timeout: int = 30,
    expect_wav: bool = False,
) -> bytes:
    if len(token) < 24:
        raise AudioNodeError("AIFILM_AUDIO_NODE_TOKEN is too short")
    if body is not None and raw_body is not None:
        raise AudioNodeError("audio node request has conflicting bodies")
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else raw_body
    req = urllib.request.Request(
        _url(base_url, path),
        data=data,
        method="POST" if data is not None else "GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if expect_wav:
                content_type = response.headers.get_content_type()
                if content_type not in {"audio/wav", "audio/x-wav"}:
                    raise AudioNodeError("audio node returned invalid MIME type")
            return response.read()
    except urllib.error.HTTPError as exc:
        raise AudioNodeError(f"audio node HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise AudioNodeError("audio node unreachable") from exc


def health(base_url: str, token: str) -> dict[str, Any]:
    return _json_response(_request(base_url, token, "/health", timeout=15), context="health")


def _validate_wav(path: Path) -> None:
    """Require the node's delivery format before promoting an artifact."""
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,sample_rate,channels:format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(probe.stdout)
        stream = (data.get("streams") or [])[0]
        duration = float((data.get("format") or {}).get("duration") or 0)
    except (
        IndexError,
        OSError,
        ValueError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ) as exc:
        raise AudioNodeError("audio node WAV failed ffprobe") from exc
    if (
        stream.get("codec_name") != "pcm_s16le"
        or str(stream.get("sample_rate")) != "44100"
        or stream.get("channels") != 2
        or duration <= 0
    ):
        raise AudioNodeError("audio node WAV does not meet delivery format")


def render(
    base_url: str,
    token: str,
    kind: str,
    payload: dict[str, Any],
    out: Path,
    timeout: int = 900,
) -> dict[str, Any]:
    if kind not in {"tts", "music", "sfx", "performance"} or not base_url.startswith(
        ("http://", "https://")
    ):
        raise AudioNodeError("invalid private audio node request")
    if len(token) < 24:
        raise AudioNodeError("invalid private audio node request")

    job_id = _json_response(
        _request(base_url, token, f"/v1/{kind}", body=payload), context="submission"
    ).get("job_id")
    if not job_id:
        raise AudioNodeError("audio node did not return job id")
    for _ in range(timeout * 2):
        status = _json_response(
            _request(base_url, token, f"/v1/jobs/{job_id}"), context="job status"
        )
        if status.get("status") == "failed":
            raise AudioNodeError("audio node job failed")
        if status.get("status") == "completed":
            wav = _request(base_url, token, f"/v1/jobs/{job_id}/audio", expect_wav=True)
            if len(wav) < 512 or wav[:4] != b"RIFF":
                raise AudioNodeError("audio node returned invalid wav")
            temporary = out.with_name(f".{out.name}.{job_id}.partial")
            try:
                atomic_write_bytes(temporary, wav)
                _validate_wav(temporary)
                actual_hash = hashlib.sha256(temporary.read_bytes()).hexdigest()
                if actual_hash != status.get("sha256"):
                    raise AudioNodeError("audio node WAV hash does not match receipt")
                temporary.replace(out)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            return {"job_id": job_id, "path": str(out), "sha256": actual_hash}
        if status.get("status") not in {"queued", "running"}:
            raise AudioNodeError("audio node job entered an unknown terminal state")
        time.sleep(0.5)
    raise AudioNodeError("audio node job timed out")


def render_sfx(
    base_url: str,
    token: str,
    *,
    prompt: str,
    duration: float,
    seed: int,
    out: Path,
    source_video: Path | None = None,
    noncommercial_research_ok: bool = False,
    timeout: int = 900,
) -> dict[str, Any]:
    """Render one provenance-bound, non-commercial MMAudio experiment."""
    if noncommercial_research_ok is not True:
        raise AudioNodeError("MMAudio requires explicit non-commercial research approval")
    text = prompt.strip()
    if not 1 <= len(text) <= 512:
        raise AudioNodeError("MMAudio prompt must contain 1-512 characters")
    if not 1 <= duration <= 30:
        raise AudioNodeError("MMAudio duration must be between 1 and 30 seconds")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise AudioNodeError("MMAudio seed must be an integer")
    node = public_health_report(health(base_url, token), secret_values=(token,))
    models = node.get("models") if isinstance(node.get("models"), dict) else {}
    if (
        node.get("ok") is not True
        or models.get("sfx") is not True
        or node.get("sfx_model") != "hkchengrex/MMAudio-large-44k-v2"
        or node.get("sfx_license") != "CC-BY-NC-4.0"
        or not _is_sha256(node.get("sfx_checkpoint_fingerprint"))
    ):
        raise AudioNodeError("trusted non-commercial MMAudio capability is unavailable")
    payload: dict[str, Any] = {
        "prompt": text,
        "duration": duration,
        "seed": seed,
        "noncommercial_research_ok": True,
    }
    source_hash: str | None = None
    if source_video is not None:
        source_input = source_video.expanduser()
        if source_input.is_symlink():
            raise AudioNodeError("MMAudio source video is missing or symlinked")
        source = source_input.resolve()
        if not source.is_file() or source.stat().st_size > 128 * 1024 * 1024:
            raise AudioNodeError("MMAudio source video is missing, symlinked, or exceeds 128 MiB")
        raw = source.read_bytes()
        source_hash = hashlib.sha256(raw).hexdigest()
        receipt = _json_response(
            _request(
                base_url,
                token,
                "/v1/sfx-source",
                raw_body=raw,
                content_type="video/mp4",
                timeout=120,
            ),
            context="SFX source upload",
        )
        if receipt.get("source_id") != source_hash or receipt.get("source_sha256") != source_hash:
            raise AudioNodeError("audio node returned invalid SFX source receipt")
        payload["source_video_id"] = source_hash
    result = render(base_url, token, "sfx", payload, out, timeout=timeout)
    return {
        **result,
        "model": node["sfx_model"],
        "checkpoint_fingerprint": node["sfx_checkpoint_fingerprint"],
        "license": node["sfx_license"],
        "source_video_sha256": source_hash,
    }


def render_batch(
    base_url: str,
    token: str,
    *,
    payload: dict[str, Any],
    out_dir: Path,
    timeout: int = 1800,
) -> dict[str, Any]:
    """Render one hash-bound ACE-Step batch without exposing its prompt.

    The node returns only indexes, seeds, hashes, and model provenance. Audio is
    downloaded separately so a partial or mismatched batch can never be
    promoted as a complete candidate set.
    """
    if not base_url.startswith(("http://", "https://")) or len(token) < 24:
        raise AudioNodeError("invalid private audio node request")
    try:
        batch_size = int(payload.get("batch_size") or 0)
        seeds = [int(seed) for seed in payload.get("seeds") or []]
    except (TypeError, ValueError) as exc:
        raise AudioNodeError("invalid ACE-Step batch request") from exc
    if not 1 <= batch_size <= 8 or len(seeds) != batch_size or len(set(seeds)) != batch_size:
        raise AudioNodeError("invalid ACE-Step batch request")

    request_payload = dict(payload)
    reference_audio = str(request_payload.pop("reference_audio", "") or "").strip()
    if reference_audio:
        reference_input = Path(reference_audio).expanduser()
        if reference_input.is_symlink():
            raise AudioNodeError("ACE-Step reference audio is missing or symlinked")
        reference_path = reference_input.resolve()
        if not reference_path.is_file():
            raise AudioNodeError("ACE-Step reference audio is missing or symlinked")
        _validate_wav(reference_path)
        raw_reference = reference_path.read_bytes()
        if len(raw_reference) > 64 * 1024 * 1024:
            raise AudioNodeError("ACE-Step reference audio exceeds 64 MiB")
        reference_receipt = _json_response(
            _request(
                base_url,
                token,
                "/v1/music-reference",
                raw_body=raw_reference,
                content_type="audio/wav",
                timeout=120,
            ),
            context="reference upload",
        )
        reference_id = str(reference_receipt.get("reference_id") or "")
        source_hash = hashlib.sha256(raw_reference).hexdigest()
        if len(reference_id) != 64 or reference_receipt.get("source_sha256") != source_hash:
            raise AudioNodeError("audio node returned invalid reference receipt")
        request_payload["reference_audio_id"] = reference_id

    job_id = _json_response(
        _request(base_url, token, "/v1/music-batch", body=request_payload),
        context="batch submission",
    ).get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise AudioNodeError("audio node did not return batch job id")

    status: dict[str, Any] = {}
    for _ in range(timeout * 2):
        status = _json_response(
            _request(base_url, token, f"/v1/jobs/{job_id}"), context="batch job status"
        )
        state = status.get("status")
        if state == "failed":
            raise AudioNodeError("audio node batch job failed")
        if state == "completed":
            break
        if state not in {"queued", "running"}:
            raise AudioNodeError("audio node batch job entered an unknown terminal state")
        time.sleep(0.5)
    else:
        raise AudioNodeError("audio node batch job timed out")

    artifacts = status.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != batch_size:
        raise AudioNodeError("audio node returned incomplete batch receipt")
    sanitized: list[dict[str, Any]] = []
    indexes: set[int] = set()
    receipt_seeds: set[int] = set()
    created: list[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        for raw in artifacts:
            if not isinstance(raw, dict):
                raise AudioNodeError("audio node returned invalid batch artifact")
            index = int(raw.get("index"))
            seed = int(raw.get("seed"))
            expected_hash = str(raw.get("sha256") or "")
            if (
                index < 0
                or index >= batch_size
                or index in indexes
                or seed not in seeds
                or seed in receipt_seeds
                or len(expected_hash) != 64
            ):
                raise AudioNodeError("audio node returned invalid batch artifact")
            wav = _request(
                base_url,
                token,
                f"/v1/jobs/{job_id}/audio/{index}",
                expect_wav=True,
            )
            if len(wav) < 512 or wav[:4] != b"RIFF":
                raise AudioNodeError("audio node returned invalid batch wav")
            target = out_dir / f"{job_id}-{index:02d}.wav"
            if target.exists():
                raise AudioNodeError("audio node batch output already exists")
            temporary = out_dir / f".{job_id}-{index:02d}.partial.wav"
            atomic_write_bytes(temporary, wav)
            _validate_wav(temporary)
            actual_hash = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                raise AudioNodeError("audio node batch WAV hash does not match receipt")
            temporary.replace(target)
            created.append(target)
            indexes.add(index)
            receipt_seeds.add(seed)
            sanitized.append(
                {
                    "index": index,
                    "seed": seed,
                    "sha256": actual_hash,
                    "path": str(target),
                }
            )
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        for path in out_dir.glob(f".{job_id}-*.partial.wav"):
            path.unlink(missing_ok=True)
        raise

    return {
        "job_id": job_id,
        "model": str(status.get("model") or "ACE-Step-1.5"),
        "checkpoint_fingerprint": str(status.get("checkpoint_fingerprint") or "unknown"),
        "artifacts": sorted(sanitized, key=lambda item: int(item["index"])),
    }
