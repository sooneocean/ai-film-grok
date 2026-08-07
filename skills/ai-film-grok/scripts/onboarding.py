"""Web-facing onboarding wizard core.

Guides a fresh user through the three prerequisite inputs a film needs before
anything can be produced:

1. **references** (参考物)  — visual / style references
2. **story**      (故事)    — the narrative / script
3. **characters** (角色)    — the cast

Each step is validated and recorded, and a terminal ``go`` persists the inputs
into the *canonical* workspace files the pipeline already consumes
(``intake/story/story.md`` + ``intake-manifest.json``, ``style-bible.json``,
``references.json``) and then triggers the workflow advance
(``spine.advance.advance_local``).

Design rules (same as the rest of the console):

* The browser never invents production state.  ``go`` writes the *same* shapes
  the CLI ``intake`` / ``visual_bible`` modules read.
* All writes go through ``web_core.write_json_locked`` (exclusive lock, 0o600).
* The wizard keeps its own resumable state in ``onboarding.json``, hash-bound
  to the workspace so two tabs cannot clobber each other (revision conflict →
  ``WebConsoleConflict``, surfaced as HTTP 409 by the gateways).
* The advance step is lazy-imported and fail-soft: if the pipeline is not
  ready to advance, the intake is still recorded and the status reports it.

No third-party dependency beyond the repo's own ``util`` / ``web_core``.
"""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from typing import Any

from util import read_json
from web_core import (
    WebConsoleConflict,
    WebConsoleError,
    now_iso,
    write_json_locked,
)

ONBOARDING_FILE = "onboarding.json"
STEPS = ("references", "story", "characters")
SCHEMA_VERSION = 1

# Image upload: decoded-pixel budget + magic-byte allow-list (content-type is
# untrusted on the browser side, so we verify the bytes, not the MIME string).
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
IMAGE_MAGIC = {
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
    b"RIFF....WEBP": ".webp",  # matched via regex below (4 bytes + 4 + 4)
}
_IMAGE_EXT = {"png": ".png", "jpg": ".jpg", "jpeg": ".jpeg", "webp": ".webp"}


def _image_ext_from_bytes(data: bytes) -> str | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    # WEBP: "RIFF" <4 bytes> "WEBP"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


# --------------------------------------------------------------------------- #
# state
# --------------------------------------------------------------------------- #
def _state_path(root: Path) -> Path:
    return Path(root) / ONBOARDING_FILE


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "onboarding",
        "revision": 0,
        "stage": "brief",  # brief | decomposing | plan | committed
        "steps": {s: {"done": False, "data": {}} for s in STEPS},
        "brief": {"story_text": "", "image_paths": [], "hints": []},
        "plan": None,
        "plan_source": None,  # "llm" | "heuristic"
        "go_status": None,
        "completed_at": None,
    }


def get_state(root: Path | str) -> dict[str, Any]:
    """Return the current onboarding state (always a well-formed dict)."""
    value = read_json(_state_path(root))
    if isinstance(value, dict) and value.get("schema_version") == SCHEMA_VERSION:
        steps = value.setdefault("steps", {})
        for s in STEPS:
            steps.setdefault(s, {"done": False, "data": {}})
        value.setdefault("revision", 0)
        value.setdefault("stage", "brief")
        value.setdefault("brief", {"story_text": "", "image_paths": [], "hints": []})
        value.setdefault("plan", None)
        value.setdefault("plan_source", None)
        value.setdefault("go_status", None)
        value.setdefault("completed_at", None)
        return value
    return _empty_state()


def save_state(root: Path | str, state: dict[str, Any]) -> None:
    write_json_locked(_state_path(root), state)


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def validate_step(step: str, payload: Any) -> list[str]:
    """Return a list of human-readable issues (empty == valid)."""
    issues: list[str] = []
    if not isinstance(payload, dict):
        return [f"{step} 数据必须是对象"]
    if step == "references":
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            issues.append("参考物至少需要 1 条")
        else:
            for it in items:
                if not isinstance(it, dict) or not str(
                    it.get("url") or it.get("path") or ""
                ).strip():
                    issues.append("每条参考物需提供 url 或 path")
    elif step == "story":
        text = str(payload.get("text") or "").strip()
        fpath = str(payload.get("path") or "").strip()
        if not text and not fpath:
            issues.append("故事需提供 text 或 path")
    elif step == "characters":
        items = payload.get("items") or payload.get("characters")
        if not isinstance(items, list) or not items:
            issues.append("角色至少需要 1 个")
        else:
            for it in items:
                if not isinstance(it, dict) or not str(it.get("id") or "").strip():
                    issues.append("每个角色需有 id")
    else:
        issues.append(f"未知步骤：{step}")
    return issues


# --------------------------------------------------------------------------- #
# submit one step
# --------------------------------------------------------------------------- #
def submit_step(
    root: Path | str,
    step: str,
    payload: Any,
    *,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Validate + record one onboarding step; returns the full state."""
    if step not in STEPS:
        raise WebConsoleError(f"unknown onboarding step: {step}")
    issues = validate_step(step, payload)
    if issues:
        raise WebConsoleError("; ".join(issues))

    base = Path(root).expanduser().resolve()
    state = get_state(base)
    if expected_revision is not None and int(expected_revision) != int(state["revision"]):
        raise WebConsoleConflict("onboarding revision is stale")

    state["steps"][step] = {"done": True, "data": payload, "updated_at": now_iso()}
    state["revision"] = int(state["revision"]) + 1
    save_state(base, state)
    return state


# --------------------------------------------------------------------------- #
# go — persist to canonical files + trigger advance
# --------------------------------------------------------------------------- #
def handle_upload(root: Path | str, *, filename: str, data_url: str) -> dict[str, Any]:
    """Validate + store an uploaded image; return its relative workspace path.

    Transport-agnostic: the gateway passes a base64 data URL, so the same logic
    works for both the FastAPI and stdlib servers without multipart parsing.
    Security is byte-based (magic bytes + size), never trusting the client MIME.
    """
    if not isinstance(data_url, str) or "," not in data_url:
        raise WebConsoleError("upload must be a data: URL")
    meta, _, b64 = data_url.partition(",")
    if not meta.lower().startswith("data:image/"):
        raise WebConsoleError("upload must be an image data URL")
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise WebConsoleError("upload payload is not valid base64")
    if len(raw) == 0 or len(raw) > MAX_UPLOAD_BYTES:
        raise WebConsoleError("upload image is empty or too large")
    ext = _image_ext_from_bytes(raw)
    if ext is None:
        raise WebConsoleError("upload is not a PNG/JPEG/WEBP image")
    import hashlib

    digest = hashlib.sha256(raw).hexdigest()[:16]
    base = Path(root).expanduser().resolve()
    dest_dir = base / "intake" / "characters"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{digest}{ext}"
    dest.write_bytes(raw)
    os.chmod(dest, 0o600)
    return {"ok": True, "path": f"intake/characters/{dest.name}", "bytes": len(raw)}


def submit_brief(
    root: Path | str,
    *,
    story_text: str,
    image_paths: list[str] | None = None,
    hints: list[str] | None = None,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Record the minimal brief (the only required input): story + optional lead image(s)."""
    base = Path(root).expanduser().resolve()
    state = get_state(base)
    if expected_revision is not None and int(expected_revision) != int(state["revision"]):
        raise WebConsoleConflict("onboarding revision is stale")
    if not str(story_text or "").strip():
        raise WebConsoleError("story text is required")
    state["brief"] = {
        "story_text": str(story_text).strip(),
        "image_paths": [str(p) for p in (image_paths or []) if str(p).strip()],
        "hints": [str(h) for h in (hints or []) if str(h).strip()],
    }
    state["stage"] = "brief"
    state["revision"] = int(state["revision"]) + 1
    save_state(base, state)
    return state


def save_plan(
    root: Path | str,
    plan: dict[str, Any],
    *,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Persist user-edited decomposition (revision-bound)."""
    base = Path(root).expanduser().resolve()
    state = get_state(base)
    if expected_revision is not None and int(expected_revision) != int(state["revision"]):
        raise WebConsoleConflict("onboarding revision is stale")
    if not isinstance(plan, dict):
        raise WebConsoleError("plan must be an object")
    state["plan"] = plan
    state["stage"] = "plan"
    state["revision"] = int(state["revision"]) + 1
    save_state(base, state)
    return state


def decompose(
    root: Path | str,
    *,
    expected_revision: int | None = None,
    brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Trigger agent-style decomposition of the brief into a reviewable plan.

    Delegates to ``onboarding_planner`` (private local LLM when configured, else
    a deterministic heuristic). Saves the resulting plan and returns the full
    state. The plan is a *proposal* (human_apply_required) — it never becomes
    production truth until ``go``.
    """
    base = Path(root).expanduser().resolve()
    state = get_state(base)
    if expected_revision is not None and int(expected_revision) != int(state["revision"]):
        raise WebConsoleConflict("onboarding revision is stale")
    if brief is not None:
        if not isinstance(brief, dict) or not str(brief.get("story_text") or "").strip():
            raise WebConsoleError("brief.story_text is required")
        state["brief"] = {
            "story_text": str(brief.get("story_text")).strip(),
            "image_paths": [str(p) for p in (brief.get("image_paths") or []) if str(p).strip()],
            "hints": [str(h) for h in (brief.get("hints") or []) if str(h).strip()],
        }
        state["revision"] = int(state["revision"]) + 1
    if not str(state["brief"].get("story_text") or "").strip():
        raise WebConsoleError("no brief to decompose; submit a story first")

    import onboarding_planner

    plan, source = onboarding_planner.decompose(base, state["brief"])
    state["plan"] = plan
    state["plan_source"] = source
    state["stage"] = "plan"
    state["revision"] = int(state["revision"]) + 1
    save_state(base, state)
    return state


def _try_derive_graph(base: Path) -> bool:
    """Best-effort: build drama-graph.json from the freshly written plan. Fail-soft."""
    try:
        from drama_graph import derive_graph

        derive_graph(base, write=True)
    except Exception:  # noqa: BLE001 -- never let go crash on graph build
        return False
    return (base / "drama-graph.json").is_file()


def _persist_canonical_v2(
    base: Path, plan: dict[str, Any], brief: dict[str, Any]
) -> dict[str, str]:
    """Persist a decomposed plan into the canonical pipeline shapes (v2 flow)."""
    out: dict[str, str] = {}
    genre = str(plan.get("genre") or "").strip() or "adult"
    heat_scale = str(plan.get("heat_scale") or "").strip() or "max"

    # film-spec.json — merge, never clobber other keys (so gates can read it).
    spec = read_json(base / "film-spec.json")
    if not isinstance(spec, dict):
        spec = {"schema_version": 1, "kind": "film-spec"}
    spec["genre"] = genre
    spec["heat_scale"] = heat_scale
    if str(plan.get("title") or "").strip():
        spec["title"] = str(plan["title"]).strip()
    if str(plan.get("theme") or "").strip():
        spec["theme"] = str(plan["theme"]).strip()
    write_json_locked(base / "film-spec.json", spec)
    out["film-spec"] = "film-spec.json (genre/heat_scale)"

    # story text
    text = str(brief.get("story_text") or "").strip()
    if text:
        (base / "intake" / "story").mkdir(parents=True, exist_ok=True)
        (base / "intake" / "story" / "story.md").write_text(text, encoding="utf-8")
        out["story"] = "intake/story/story.md"

    # characters -> style-bible.json + intake-manifest.json
    lead_image = (brief.get("image_paths") or [None])[0]
    chars = plan.get("characters") or []
    records: list[dict[str, Any]] = []
    for c in chars:
        cid = str(c.get("id") or "").strip()
        if not cid:
            continue
        ref_image = str(c.get("reference_image") or (lead_image if c.get("is_lead") else ""))
        rec = {
            "id": cid,
            "name": str(c.get("name") or cid),
            "aliases": c.get("aliases") or [],
            "reference_role": "costume_identity",
            "reference_image": {
                "path": ref_image,
                "name": ref_image.split("/")[-1] or ref_image,
                "source": "path",
            },
            "visual_features": {
                "status": "needs_visual_review",
                "identity": [str(c.get("description") or "")],
                "wardrobe": [],
                "signature_features": [],
            },
            "review_status": "needs_review",
        }
        records.append(rec)

    bible = read_json(base / "style-bible.json")
    if not isinstance(bible, dict):
        bible = {}
    chars_map = bible.get("characters") if isinstance(bible.get("characters"), dict) else {}
    cast = bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
    for rec in records:
        cid = rec["id"]
        chars_map[cid] = {
            "name": rec["name"],
            "reference_image": rec["reference_image"],
            "visual_features": rec["visual_features"],
        }
        cast[cid] = {"id": cid, "name": rec["name"], "reference_image": rec["reference_image"]}
    bible["characters"] = chars_map
    bible["cast_masters"] = cast
    if str(plan.get("theme") or "").strip():
        bible["theme"] = str(plan["theme"]).strip()
    write_json_locked(base / "style-bible.json", bible)
    out["style-bible"] = "style-bible.json"

    manifest = {
        "schema_version": 1,
        "kind": "ai-film-intake",
        "created_at": now_iso(),
        "language": "zh-CN",
        "story": {"kind": "paste", "source_ref": "intake/story/story.md", "text_len": len(text)},
        "characters": records,
        "status": "staged",
    }
    (base / "intake").mkdir(parents=True, exist_ok=True)
    write_json_locked(base / "intake-manifest.json", manifest)
    out["characters"] = f"intake-manifest.json ({len(records)} characters)"
    return out


def go(root: Path | str, *, expected_revision: int | None = None) -> dict[str, Any]:
    """Fail-closed launch.

    Two entry shapes are supported (both revision-bound):
      * new flow — a decomposed ``plan`` is present: persist it, derive graph, advance;
      * legacy flow — the three ``steps`` are done: behave exactly as before.
    """
    base = Path(root).expanduser().resolve()
    state = get_state(base)
    if expected_revision is not None and int(expected_revision) != int(state["revision"]):
        raise WebConsoleConflict("onboarding revision is stale")

    plan = state.get("plan")
    if plan:
        brief = state.get("brief") or {}
        persisted = _persist_canonical_v2(base, plan, brief)
        advanced, advanced_detail = _try_advance(base)
        graph_written = _try_derive_graph(base)
        state["go_status"] = "done"
        state["completed_at"] = now_iso()
        state["stage"] = "committed"
        state["revision"] = int(state["revision"]) + 1
        save_state(base, state)
        return {
            "ok": True,
            "revision": state["revision"],
            "go_status": state["go_status"],
            "persisted": persisted,
            "advanced": advanced,
            "advanced_detail": advanced_detail,
            "graph_written": graph_written,
        }

    missing = [s for s in STEPS if not state["steps"].get(s, {}).get("done")]
    if missing:
        raise WebConsoleError(f"onboarding incomplete, missing steps: {', '.join(missing)}")

    persisted = _persist_canonical(base, state)
    advanced, advanced_detail = _try_advance(base)
    graph_written = _try_derive_graph(base)

    state["go_status"] = "done"
    state["completed_at"] = now_iso()
    state["revision"] = int(state["revision"]) + 1
    save_state(base, state)
    return {
        "ok": True,
        "revision": state["revision"],
        "go_status": state["go_status"],
        "persisted": persisted,
        "advanced": advanced,
        "advanced_detail": advanced_detail,
        "graph_written": graph_written,
    }


def _try_advance(base: Path) -> tuple[bool, str]:
    """Lazy-import + run the workflow advance, fail-soft."""
    try:
        from spine.advance import advance_local

        result = advance_local(base, max_local=1)
    except Exception as exc:  # noqa: BLE001 -- never let "go" crash the wizard
        return False, f"advance not run: {type(exc).__name__}: {exc}"
    advanced = bool(result)
    return advanced, _summarize_advance(result)


def _summarize_advance(result: Any) -> str:
    if result is None:
        return "no dispatchable action"
    if isinstance(result, dict):
        return "advanced: " + ", ".join(f"{k}={result[k]}" for k in list(result)[:6])
    return str(result)[:200]


# --------------------------------------------------------------------------- #
# canonical file writers (shapes the pipeline already consumes)
# --------------------------------------------------------------------------- #
def _character_record(c: dict[str, Any]) -> dict[str, Any]:
    cid = str(c.get("id") or "").strip()
    ref = str(c.get("reference_image") or c.get("image") or "").strip()
    desc = str(c.get("description") or "").strip()
    return {
        "id": cid,
        "name": str(c.get("name") or cid),
        "aliases": c.get("aliases") or [],
        "reference_role": "costume_identity",
        "reference_image": {
            "path": ref,
            "name": ref.split("/")[-1] or ref,
            "source": "url" if ref.startswith("http") else "path",
        },
        "visual_features": {
            "status": "needs_visual_review",
            "identity": [desc] if desc else [],
            "wardrobe": [],
            "signature_features": [],
        },
        "review_status": "needs_review",
    }


def _persist_canonical(base: Path, state: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}

    # 1) references -> references.json + style-bible.json
    refs = state["steps"]["references"]["data"].get("items", [])
    write_json_locked(
        base / "references.json",
        {"schema_version": 1, "kind": "aifilm-references", "items": refs},
    )
    _merge_style_bible(base, references=refs)
    out["references"] = f"references.json ({len(refs)} items)"

    # 2) story -> intake/story/story.md
    story = state["steps"]["story"]["data"]
    text = str(story.get("text") or "").strip()
    if text:
        (base / "intake" / "story").mkdir(parents=True, exist_ok=True)
        (base / "intake" / "story" / "story.md").write_text(text, encoding="utf-8")
        out["story"] = "intake/story/story.md"
    else:
        out["story"] = "skipped (no text)"

    # 3) characters -> intake-manifest.json + style-bible.json
    chars = (
        state["steps"]["characters"]["data"].get("items")
        or state["steps"]["characters"]["data"].get("characters")
        or []
    )
    manifest = {
        "schema_version": 1,
        "kind": "ai-film-intake",
        "created_at": now_iso(),
        "language": str(story.get("language") or "zh-CN"),
        "story": {
            "kind": "paste",
            "source_ref": "intake/story/story.md",
            "text_len": len(text),
        },
        "characters": [_character_record(c) for c in chars],
        "status": "staged",
    }
    (base / "intake").mkdir(parents=True, exist_ok=True)
    write_json_locked(base / "intake-manifest.json", manifest)
    _merge_style_bible(base, characters=chars)
    out["characters"] = f"intake-manifest.json ({len(chars)} characters)"
    return out


def _merge_style_bible(
    base: Path,
    *,
    references: list[dict[str, Any]] | None = None,
    characters: list[dict[str, Any]] | None = None,
) -> None:
    """Merge wizard inputs into style-bible.json without clobbering other keys."""
    path = base / "style-bible.json"
    bible = read_json(path)
    if not isinstance(bible, dict):
        bible = {}

    if references is not None:
        lst = bible.get("references") if isinstance(bible.get("references"), list) else []
        seen = {r.get("url") or r.get("path") for r in lst}
        for r in references:
            key = r.get("url") or r.get("path")
            if key and key not in seen:
                lst.append(r)
                seen.add(key)
        bible["references"] = lst

    if characters is not None:
        chars = bible.get("characters") if isinstance(bible.get("characters"), dict) else {}
        cast = bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
        for c in characters:
            rec = _character_record(c)
            cid = rec["id"]
            if not cid:
                continue
            chars[cid] = {
                "name": rec["name"],
                "reference_image": rec["reference_image"],
                "visual_features": rec["visual_features"],
            }
            cast[cid] = {"id": cid, "name": rec["name"], "reference_image": rec["reference_image"]}
        bible["characters"] = chars
        bible["cast_masters"] = cast

    write_json_locked(path, bible)
