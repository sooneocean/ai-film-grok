"""Approval-gated, fixed-profile adult female dialogue and breath candidates."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from audio_node_client import AudioNodeError, _validate_wav, health, render
from performance_candidates import _sha256, receipt_is_signed, sign_receipt
from security_policy import atomic_write_text
from util import read_json, write_json
from voice_armory import render_ready_tts_profile


class AdultFemaleVoicePackError(RuntimeError):
    pass


PACK_ID = "zh-adult-female-breath-v1"
SCHEMA = "aifilm-adult-female-breath-pack-v1"
RECEIPT_SCHEMA = "aifilm-adult-female-breath-candidate-v1"


def _root(root: Path) -> Path:
    return root.expanduser().resolve()


def _pack_path(root: Path) -> Path:
    return _root(root) / "dialogue-packs" / f"{PACK_ID}.json"


def _pending(root: Path) -> Path:
    return _root(root) / "audio" / "candidates" / "adult-female-breath" / "pending"


def _approved(root: Path) -> Path:
    return _root(root) / "audio" / "candidates" / "adult-female-breath" / "approved"


def _items() -> list[dict[str, Any]]:
    groups = (
        (
            "gentle",
            "qwen_zh_female_gentle",
            "温柔靠近",
            (
                "别一直看着我……我会不好意思的。",
                "再靠近一点，不过慢一点。",
                "你这样说，我真的会脸红。",
            ),
        ),
        (
            "playful",
            "qwen_zh_female_playful",
            "轻快挑逗",
            ("你是不是故意的？", "嗯……那你可别临阵退缩。", "现在换我逗你了。"),
        ),
        (
            "breathy",
            "qwen_zh_female_breathy",
            "害羞停顿",
            ("等一下……让我先缓一下。", "嗯……别急。", "你靠得太近了。"),
        ),
        (
            "husky",
            "qwen_zh_female_husky",
            "低声挽留",
            ("先别走，好不好？", "再陪我一下。", "我还想听你说话。"),
        ),
    )
    items: list[dict[str, Any]] = []
    for group_id, profile, mood, lines in groups:
        for index, text in enumerate(lines, start=1):
            items.append(
                {
                    "asset_id": f"{PACK_ID}-dialogue-{group_id}-{index}",
                    "kind": "dialogue",
                    "voice_profile": profile,
                    "language": "Chinese",
                    "mood": mood,
                    "text": text,
                    "instruction": "成年中文女声，近距离自然说话；情绪克制，保留自然呼吸与停顿，不加入背景音乐或环境声。",
                    "target_duration_sec": 3.0,
                    "seed": 7200 + len(items) + 1,
                }
            )
    breaths = (
        (
            "short-intake",
            "短促吸气",
            "嗯……",
            "一次短促自然吸气后轻轻收住；成年中文女声，非语言演出，不说出动作文字。",
        ),
        (
            "close-breath",
            "近距轻喘",
            "嗯……",
            "近距离、平稳而轻微的呼吸感；成年中文女声，非语言演出，不说出动作文字。",
        ),
        (
            "shy-release",
            "害羞停顿后呼气",
            "嗯……",
            "短暂停顿后轻轻呼出一口气；成年中文女声，害羞但自然，非语言演出。",
        ),
        ("soft-sigh", "低声轻叹", "唉……", "一声轻柔低叹，成年中文女声，近距离且克制，非语言演出。"),
    )
    for index, (slug, mood, text, instruction) in enumerate(breaths, start=1):
        items.append(
            {
                "asset_id": f"{PACK_ID}-breath-{slug}",
                "kind": "breath",
                "voice_profile": "qwen_zh_female_breathy",
                "language": "Chinese",
                "mood": mood,
                "text": text,
                "instruction": instruction,
                "target_duration_sec": 2.0,
                "seed": 7300 + index,
            }
        )
    return items


def initialize(root: Path) -> dict[str, Any]:
    """Create the immutable v1 plan before the node is asked to synthesize it."""
    path = _pack_path(root)
    if path.exists():
        data = read_json(path)
        if _is_fixed_plan(data):
            return data
        raise AdultFemaleVoicePackError("existing voice-pack manifest is not the fixed v1 plan")
    data = {
        "schema": SCHEMA,
        "pack_id": PACK_ID,
        "status": "planned_pending_render_and_human_review",
        "language": "zh-CN",
        "adult_only": True,
        "source_authorization": "original",
        "render_backend": "audio_node/qwen3-tts-5090",
        "created_at": datetime.now(UTC).isoformat(),
        "items": [{**item, "status": "planned"} for item in _items()],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, data)
    return data


def _is_fixed_plan(data: object) -> bool:
    """Do not let a mutable JSON manifest change the locked v1 voice inventory."""
    if not isinstance(data, dict):
        return False
    expected = [{**item, "status": "planned"} for item in _items()]
    return (
        data.get("schema") == SCHEMA
        and data.get("pack_id") == PACK_ID
        and data.get("language") == "zh-CN"
        and data.get("adult_only") is True
        and data.get("source_authorization") == "original"
        and data.get("render_backend") == "audio_node/qwen3-tts-5090"
        and data.get("items") == expected
    )


def _load_pack(root: Path) -> dict[str, Any]:
    data = initialize(root)
    if not _is_fixed_plan(data):
        raise AdultFemaleVoicePackError("voice-pack manifest is invalid")
    return data


def _receipt_path(root: Path, asset_id: str) -> Path:
    return _pending(root) / f"{asset_id}.json"


def _existing_valid(root: Path, asset_id: str) -> bool:
    receipt_path = _receipt_path(root, asset_id)
    wav = _pending(root) / f"{asset_id}.wav"
    if not receipt_path.is_file() or not wav.is_file():
        return False
    record = read_json(receipt_path)
    if not isinstance(record, dict) or record.get("status") != "pending_human_review":
        return False
    try:
        _validate_wav(wav)
    except AudioNodeError:
        return False
    return receipt_is_signed(record) and _sha256(wav) == record.get("sha256")


def render_pending(root: Path, *, base_url: str, token: str) -> dict[str, Any]:
    """Render all fixed-profile candidates, never approving them automatically."""
    root = _root(root)
    pack = _load_pack(root)
    try:
        node = health(base_url, token)
    except AudioNodeError as exc:
        raise AdultFemaleVoicePackError(f"private audio node is unavailable: {exc}") from exc
    variants = node.get("tts_variants", {})
    if not isinstance(variants, dict):
        raise AdultFemaleVoicePackError("private audio node did not report TTS variants")
    rendered, reused = [], []
    pending = _pending(root)
    pending.mkdir(parents=True, exist_ok=True)
    for item in pack["items"]:
        asset_id = str(item["asset_id"])
        if _existing_valid(root, asset_id):
            reused.append(asset_id)
            continue
        profile_id = str(item["voice_profile"])
        try:
            profile = render_ready_tts_profile(profile_id, variants)
            wav = pending / f"{asset_id}.wav"
            node_result = render(
                base_url,
                token,
                "tts",
                {
                    "text": item["text"],
                    "model_variant": profile["variant"],
                    "voice_profile_id": profile.get("speaker", ""),
                    "language": profile["language"],
                    "performance": {
                        "instruction": f"{profile.get('instruction_prefix', '')} {item['instruction']}".strip()
                    },
                },
                wav,
            )
            _validate_wav(wav)
        except (AudioNodeError, ValueError, OSError) as exc:
            raise AdultFemaleVoicePackError(f"failed to render {asset_id}: {exc}") from exc
        digest = _sha256(wav)
        if digest != node_result.get("sha256"):
            raise AdultFemaleVoicePackError(f"node hash mismatch for {asset_id}")
        record = {
            "schema": RECEIPT_SCHEMA,
            "asset_id": asset_id,
            "pack_id": PACK_ID,
            "status": "pending_human_review",
            "kind": item["kind"],
            "voice_profile": profile_id,
            "language": "zh-CN",
            "mood": item["mood"],
            "target_duration_sec": item["target_duration_sec"],
            "seed": item["seed"],
            "node_job_id": node_result["job_id"],
            "sha256": digest,
            "text_sha256": hashlib.sha256(str(item["text"]).encode("utf-8")).hexdigest(),
            "path": str(wav.relative_to(root)),
            "created_at": datetime.now(UTC).isoformat(),
        }
        sign_receipt(record)
        write_json(_receipt_path(root, asset_id), record)
        rendered.append(asset_id)
    pack["status"] = "pending_human_review"
    pack["rendered_at"] = datetime.now(UTC).isoformat()
    write_json(_pack_path(root), pack)
    return {"pack_id": PACK_ID, "rendered": rendered, "reused": reused}


def list_candidates(root: Path) -> list[dict[str, Any]]:
    pending = _pending(root)
    if not pending.exists():
        return []
    candidates = []
    for receipt_path in sorted(pending.glob("*.json")):
        record = read_json(receipt_path)
        if isinstance(record, dict) and record.get("schema") == RECEIPT_SCHEMA:
            candidates.append(record)
    return candidates


def approve(
    root: Path,
    asset_id: str,
    *,
    reviewer: str,
    female_voice_confirmed: bool,
    breath_confirmed: bool,
    artifact_free_confirmed: bool,
) -> dict[str, Any]:
    """Move one heard candidate to approved only after all human checks pass."""
    if not reviewer.strip() or not all(
        (female_voice_confirmed, breath_confirmed, artifact_free_confirmed)
    ):
        raise AdultFemaleVoicePackError(
            "reviewer and all three human hearing confirmations are required"
        )
    source = _pending(root) / f"{asset_id}.wav"
    receipt_path = _receipt_path(root, asset_id)
    record = read_json(receipt_path)
    if (
        not isinstance(record, dict)
        or record.get("status") != "pending_human_review"
        or not receipt_is_signed(record)
    ):
        raise AdultFemaleVoicePackError("candidate receipt is not approvable")
    if not source.is_file() or _sha256(source) != record.get("sha256"):
        raise AdultFemaleVoicePackError("candidate audio is missing or changed")
    try:
        _validate_wav(source)
    except AudioNodeError as exc:
        raise AdultFemaleVoicePackError("candidate audio is not a valid delivery WAV") from exc
    destination = _approved(root) / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        destination.with_suffix(".license.txt"),
        "Private original adult female voice candidate; human approved.\n",
    )
    destination.write_bytes(source.read_bytes())
    if _sha256(destination) != record["sha256"]:
        raise AdultFemaleVoicePackError("approved candidate hash mismatch")
    record.update(
        {
            "status": "approved",
            "approved_at": datetime.now(UTC).isoformat(),
            "approved_by": reviewer.strip(),
            "female_voice_confirmed": True,
            "breath_confirmed": True,
            "artifact_free_confirmed": True,
            "approved_path": str(destination.relative_to(_root(root))),
        }
    )
    sign_receipt(record)
    write_json(receipt_path, record)
    write_json(destination.with_suffix(".receipt.json"), record)
    return record
