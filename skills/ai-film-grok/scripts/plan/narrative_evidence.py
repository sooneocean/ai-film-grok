"""Plan-vs-executed evidence for episode hooks and plot points."""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

from util import canonical_json_sha256, read_json, sha256_file, utc_now, write_json

EVIDENCE_NAME = "narrative-evidence.json"
VALID_STATUSES = frozenset({"verified", "missing", "uncertain"})


class NarrativeEvidenceError(ValueError):
    def __init__(self, message: str, *, code: str = "NARRATIVE_EVIDENCE_INVALID") -> None:
        super().__init__(message)
        self.code = code


def _graph_fingerprint(root: Path, graph: dict[str, Any]) -> str:
    graph_path = root / "drama-graph.json"
    if graph_path.is_file():
        return sha256_file(graph_path)
    return canonical_json_sha256(graph)


def _planned(graph: dict[str, Any]) -> list[dict[str, Any]]:
    graph = normalize_story_graph(graph)
    rows: list[dict[str, Any]] = []
    points = {
        str(p.get("point_id")): p for p in graph.get("plot_points") or [] if isinstance(p, dict)
    }
    for ep in graph.get("episodes") or []:
        if not isinstance(ep, dict):
            continue
        episode_id = str(ep.get("id") or "")
        for kind, hook in (
            ("opening_hook", ep.get("opening_hook")),
            ("ending_hook", ep.get("ending_hook")),
        ):
            if isinstance(hook, dict):
                point = points.get(str(hook.get("point_id"))) or {}
                rows.append(
                    {
                        "evidence_id": f"{episode_id}:{kind}",
                        "episode_id": episode_id,
                        "kind": kind,
                        "point_id": hook.get("point_id"),
                        "beat_id": hook.get("beat_id"),
                        "shot_ids": list(hook.get("shot_ids") or []),
                        "source_refs": list(
                            hook.get("source_refs") or point.get("source_refs") or []
                        ),
                        "question": hook.get("question") or point.get("audience_question") or "",
                        "visible_evidence": hook.get("visible_evidence")
                        or point.get("visible_evidence")
                        or "",
                    }
                )
        for point_id in ep.get("mid_episode_points") or []:
            point = points.get(str(point_id)) or {}
            rows.append(
                {
                    "evidence_id": f"{episode_id}:mid:{point_id}",
                    "episode_id": episode_id,
                    "kind": "mid_episode_point",
                    "point_id": point_id,
                    "beat_id": point.get("introduced_beat_id"),
                    "shot_ids": list(point.get("introduced_shot_ids") or []),
                    "source_refs": list(point.get("source_refs") or []),
                    "question": point.get("audience_question") or "",
                    "visible_evidence": point.get("visible_evidence") or "",
                }
            )
    return rows


def _media_probe(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise NarrativeEvidenceError(f"media does not exist: {path}", code="MEDIA_MISSING")
    try:
        raw = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            text=True,
            timeout=30,
        )
        duration = float(json.loads(raw)["format"]["duration"])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("media duration must be finite and positive")
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise NarrativeEvidenceError(
            f"cannot probe media duration: {path}", code="MEDIA_UNREADABLE"
        ) from exc
    return {"sha256": sha256_file(path), "duration_sec": duration}


def _read_or_init(root: Path, graph: dict[str, Any]) -> dict[str, Any]:
    report = read_json(root / EVIDENCE_NAME) or {}
    if not isinstance(report, dict):
        report = {}
    return report


def build_narrative_evidence(root: Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    graph = read_json(root / "drama-graph.json") or {}
    existing = _read_or_init(root, graph)
    planned = _planned(graph)
    prior = {
        str(item.get("evidence_id")): item
        for item in existing.get("items") or []
        if isinstance(item, dict) and item.get("evidence_id")
    }
    fingerprint = _graph_fingerprint(root, graph)
    stale_graph = bool(
        existing.get("graph_fingerprint") and existing.get("graph_fingerprint") != fingerprint
    )
    items: list[dict[str, Any]] = []
    for item in planned:
        old = prior.get(str(item["evidence_id"]), {})
        merged = {
            **item,
            "executed": old.get("executed") or {},
            "human_review": old.get("human_review") or {},
        }
        status = str(old.get("evidence_status") or "missing")
        merged["evidence_status"] = (
            "uncertain" if stale_graph else (status if status in VALID_STATUSES else "uncertain")
        )
        if stale_graph and old.get("executed"):
            merged["stale_reason"] = "drama graph changed after evidence was recorded"
        items.append(merged)
    report = {
        "schema_version": 2,
        "kind": "narrative-evidence",
        "at": utc_now(),
        "graph_fingerprint": fingerprint,
        "planned": planned,
        "items": items,
        "policy": graph.get("narrative_policy") or {},
    }
    if write:
        write_json(root / EVIDENCE_NAME, report)
    return report


def init_narrative_evidence(root: Path) -> dict[str, Any]:
    return build_narrative_evidence(root, write=True)


def record_narrative_evidence(
    root: Path,
    *,
    evidence_id: str,
    status: str,
    shot_id: str | None = None,
    start_sec: float | None = None,
    end_sec: float | None = None,
    media_path: str | None = None,
    reviewer: str | None = None,
    user_phrase: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    graph = read_json(root / "drama-graph.json") or {}
    report = build_narrative_evidence(root, write=False)
    rows = {str(row.get("evidence_id")): row for row in report.get("planned") or []}
    if evidence_id not in rows:
        raise NarrativeEvidenceError(
            f"unknown evidence id: {evidence_id}", code="EVIDENCE_ID_UNKNOWN"
        )
    planned = rows[evidence_id]
    if status not in VALID_STATUSES:
        raise NarrativeEvidenceError(f"invalid status: {status}", code="EVIDENCE_STATUS_INVALID")
    item = next(x for x in report["items"] if str(x.get("evidence_id")) == evidence_id)
    if status == "verified":
        if not shot_id or shot_id not in {str(x) for x in planned.get("shot_ids") or []}:
            raise NarrativeEvidenceError(
                "shot is not planned for this evidence", code="EVIDENCE_SHOT_UNPLANNED"
            )
        if (
            start_sec is None
            or end_sec is None
            or not math.isfinite(float(start_sec))
            or not math.isfinite(float(end_sec))
            or end_sec <= start_sec
            or start_sec < 0
        ):
            raise NarrativeEvidenceError(
                "invalid evidence time range", code="EVIDENCE_TIME_INVALID"
            )
        if not media_path:
            raise NarrativeEvidenceError("media_path is required", code="MEDIA_MISSING")
        media = Path(media_path).expanduser()
        if not media.is_absolute():
            media = root / media
        media = media.resolve()
        try:
            media.relative_to(root)
        except ValueError as exc:
            raise NarrativeEvidenceError(
                "media_path must be inside film root", code="MEDIA_PATH_OUTSIDE_ROOT"
            ) from exc
        probe = _media_probe(media)
        if end_sec > probe["duration_sec"] + 0.001:
            raise NarrativeEvidenceError(
                "evidence time exceeds media duration", code="EVIDENCE_TIME_OUT_OF_RANGE"
            )
        if not reviewer or not reviewer.strip() or not user_phrase or not user_phrase.strip():
            raise NarrativeEvidenceError(
                "reviewer and explicit user_phrase are required", code="HUMAN_REVIEW_MISSING"
            )
        item["executed"] = {
            "shot_ids": [shot_id],
            "time_range": {"start_sec": float(start_sec), "end_sec": float(end_sec)},
            "media_path": str(media.relative_to(root)),
            "media_sha256": probe["sha256"],
            "duration_sec": probe["duration_sec"],
            "recorded_at": utc_now(),
        }
        item["human_review"] = {
            "approved": True,
            "reviewer": reviewer.strip(),
            "user_phrase": user_phrase.strip(),
            "reviewed_at": utc_now(),
            "note": note or "",
        }
    else:
        item["executed"] = {}
        item["human_review"] = {
            "approved": False,
            "reviewer": reviewer or "",
            "user_phrase": user_phrase or "",
            "reviewed_at": utc_now(),
            "note": note or "",
        }
    item["evidence_status"] = status
    report["graph_fingerprint"] = _graph_fingerprint(root, graph)
    report["at"] = utc_now()
    write_json(root / EVIDENCE_NAME, report)
    return {
        "ok": True,
        "evidence_id": evidence_id,
        "evidence_status": status,
        "path": str(root / EVIDENCE_NAME),
    }


def validate_narrative_evidence(root: Path, *, require_verified: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    graph = read_json(root / "drama-graph.json") or {}
    semantic = (
        validate_narrative_graph(graph, strict=True) if graph else {"ok": False, "errors": []}
    )
    report = read_json(root / EVIDENCE_NAME) or {}
    expected = _planned(graph)
    by_id = {
        str(item.get("evidence_id")): item
        for item in report.get("items") or []
        if isinstance(item, dict)
    }
    issues: list[dict[str, Any]] = list(semantic.get("errors") or [])
    if report.get("graph_fingerprint") != _graph_fingerprint(root, graph):
        issues.append(
            {
                "code": "NARRATIVE_EVIDENCE_STALE",
                "message": "evidence was recorded against another drama graph",
            }
        )
    for planned in expected:
        item = by_id.get(str(planned["evidence_id"]))
        if not item:
            issues.append(
                {
                    "code": "NARRATIVE_EVIDENCE_MISSING",
                    "message": f"missing evidence item: {planned['evidence_id']}",
                }
            )
            continue
        if require_verified and item.get("evidence_status") != "verified":
            issues.append(
                {
                    "code": "NARRATIVE_EVIDENCE_UNVERIFIED",
                    "message": f"narrative evidence is not verified: {planned['evidence_id']}",
                }
            )
        executed = item.get("executed") if isinstance(item.get("executed"), dict) else {}
        human = item.get("human_review") if isinstance(item.get("human_review"), dict) else {}
        if require_verified and (not executed or human.get("approved") is not True):
            issues.append(
                {
                    "code": "NARRATIVE_EXECUTED_EVIDENCE_MISSING",
                    "message": f"executed and human evidence required: {planned['evidence_id']}",
                }
            )
        if executed:
            # Preserve read-back compatibility with v1 ledgers; v2 records use a
            # structured time_range plus media hash and are checked below.
            if isinstance(executed.get("time_range"), list) and not executed.get("media_path"):
                continue
            if (
                not executed.get("shot_ids")
                or not executed.get("media_path")
                or not executed.get("media_sha256")
            ):
                issues.append(
                    {
                        "code": "NARRATIVE_EXECUTED_EVIDENCE_MISSING",
                        "message": f"executed evidence fields are incomplete: {planned['evidence_id']}",
                    }
                )
            if not isinstance(executed.get("time_range"), dict):
                issues.append(
                    {
                        "code": "EVIDENCE_TIME_INVALID",
                        "message": f"structured time range required: {planned['evidence_id']}",
                    }
                )
            if (
                human.get("approved") is not True
                or not human.get("reviewer")
                or not human.get("user_phrase")
                or not human.get("reviewed_at")
            ):
                issues.append(
                    {
                        "code": "HUMAN_REVIEW_MISSING",
                        "message": f"reviewer, time and explicit phrase required: {planned['evidence_id']}",
                    }
                )
            for sid in executed.get("shot_ids") or []:
                if str(sid) not in {str(x) for x in planned.get("shot_ids") or []}:
                    issues.append(
                        {
                            "code": "EVIDENCE_SHOT_UNPLANNED",
                            "message": f"unplanned shot in evidence: {planned['evidence_id']}",
                        }
                    )
            try:
                media = (root / str(executed.get("media_path") or "")).resolve()
                media.relative_to(root)
            except ValueError:
                issues.append(
                    {
                        "code": "MEDIA_PATH_OUTSIDE_ROOT",
                        "message": f"evidence media escapes film root: {planned['evidence_id']}",
                    }
                )
                continue
            try:
                probe = _media_probe(media)
                if probe["sha256"] != executed.get("media_sha256"):
                    issues.append(
                        {
                            "code": "NARRATIVE_MEDIA_HASH_STALE",
                            "message": f"media changed after evidence record: {planned['evidence_id']}",
                        }
                    )
                tr = executed.get("time_range") or {}
                if (
                    float(tr.get("start_sec")) < 0
                    or float(tr.get("end_sec")) > probe["duration_sec"]
                    or float(tr.get("end_sec")) <= float(tr.get("start_sec"))
                ):
                    issues.append(
                        {
                            "code": "EVIDENCE_TIME_OUT_OF_RANGE",
                            "message": f"evidence time is outside media: {planned['evidence_id']}",
                        }
                    )
            except NarrativeEvidenceError as exc:
                issues.append(
                    {
                        "code": exc.code,
                        "message": f"invalid evidence media: {planned['evidence_id']}",
                    }
                )
            except (TypeError, ValueError):
                issues.append(
                    {
                        "code": "MEDIA_MISSING",
                        "message": f"evidence media is unavailable: {planned['evidence_id']}",
                    }
                )
    required = bool(
        graph.get("episodes")
        and graph.get("plot_points")
        and graph.get("narrative_policy", {}).get("require_executed_evidence", True)
    )
    return {
        "ok": not issues,
        "required": required,
        "planned_count": len(expected),
        "verified_count": sum(
            1 for item in by_id.values() if item.get("evidence_status") == "verified"
        ),
        "issues": issues,
        "path": str(root / EVIDENCE_NAME),
    }
