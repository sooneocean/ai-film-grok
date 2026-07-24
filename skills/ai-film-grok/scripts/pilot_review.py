#!/usr/bin/env python3
"""Pilot three-shot scorecard assist + user approval writer.

Does NOT allow agent self-approve. Approval requires approved_by=user and a
user_phrase (or notes) that carries user intent such as 「pilot 过」.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from director_review import DirectorReviewError, normalize_score_value
from production_gates import (
    PILOT_MAX_SHOTS_WITHOUT_APPROVAL,
    load_pilot_approval,
    pilot_approval_path,
    pilot_is_user_approved,
)
from security_policy import SecurityPolicyError, safe_workspace_directory
from util import read_json as _util_read_json
from util import utc_now, write_json

# Pilot scorecard is the pre-batch gate — three dimensions, not full final seven.
PILOT_SCORE_DIMS: tuple[str, ...] = ("identity", "style", "motion")
PREFERRED_BEATS: tuple[str, ...] = (
    "hook",
    "reaction",
    "action",
    "sensory",
    "approach",
    "afterglow",
    "bridge",
)
# Adult max pilot: undress + union + rhythm prove wardrobe ladder + mute-frame + motion
ADULT_PILOT_COITUS: tuple[str, ...] = ("undress", "union", "rhythm", "entry", "finish", "lock")


class PilotReviewError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    """Permissive read_json — returns {} on missing/error (unlike util.read_json's None)."""
    return _util_read_json(path) or {}


def flatten_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict) and shot.get("id"):
                out.append(shot)
    return out


def pick_pilot_shots(
    spec: dict[str, Any], *, n: int = PILOT_MAX_SHOTS_WITHOUT_APPROVAL
) -> list[str]:
    """Prefer hook + reaction + action; heat=max prefers undress/union/rhythm first."""
    shots = flatten_shots(spec)
    if not shots:
        raise PilotReviewError("film-spec has no shots — write-spec first")
    heat = str(spec.get("heat_scale") or "").strip().lower()
    picked: list[str] = []

    # Adult canary: wardrobe undress + coitus-readable union + rhythm hips
    if heat in {"max", "hot"}:
        by_coitus: dict[str, list[str]] = {}
        for shot in shots:
            dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
            cb = str(shot.get("coitus_beat") or dsl.get("coitus_beat") or "").strip().lower()
            if cb:
                by_coitus.setdefault(cb, []).append(str(shot["id"]))
        for cb in ADULT_PILOT_COITUS:
            # one shot per coitus beat — diversify undress / union / rhythm
            for sid in by_coitus.get(cb) or []:
                if sid not in picked:
                    picked.append(sid)
                    break
            if len(picked) >= n:
                return picked

    by_beat: dict[str, list[str]] = {}
    for shot in shots:
        beat = str(shot.get("dramatic_function") or "bridge")
        by_beat.setdefault(beat, []).append(str(shot["id"]))
    for beat in PREFERRED_BEATS:
        for sid in by_beat.get(beat) or []:
            if sid not in picked:
                picked.append(sid)
            if len(picked) >= n:
                return picked
    for shot in shots:
        sid = str(shot["id"])
        if sid not in picked:
            picked.append(sid)
        if len(picked) >= n:
            break
    return picked[:n]


def media_status_for_shot(root: Path, manifest: dict[str, Any], shot_id: str) -> dict[str, Any]:
    stills = manifest.get("stills") if isinstance(manifest.get("stills"), dict) else {}
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    still = stills.get(shot_id) if isinstance(stills.get(shot_id), dict) else None
    clip = clips.get(shot_id) if isinstance(clips.get(shot_id), dict) else None

    def _summ(rec: dict[str, Any] | None, kind: str) -> dict[str, Any]:
        if not rec:
            return {"present": False, "status": None, "path": None}
        path = rec.get("path")
        exists = False
        if isinstance(path, str):
            p = Path(path)
            if not p.is_absolute():
                p = root / path
            exists = p.is_file()
        return {
            "present": exists,
            "status": rec.get("status"),
            "path": path,
            "identity_approved": rec.get("identity_approved"),
            "motion_approved": rec.get("motion_approved") if kind == "clip" else None,
            "source_endpoint": rec.get("source_endpoint") if kind == "clip" else None,
        }

    return {
        "shot_id": shot_id,
        "still": _summ(still, "still"),
        "clip": _summ(clip, "clip"),
        "ready_for_batch_sample": bool(
            still
            and still.get("status") == "approved"
            and clip
            and clip.get("status") == "approved"
        ),
    }


def pilot_scorecard_path(root: Path) -> Path:
    return Path(root).expanduser().resolve() / "receipts" / "pilot-scorecard.json"


def build_pilot_scorecard(
    *,
    shots: list[str],
    scores: dict[str, bool],
    reviewer: str,
    notes: str,
    per_shot: dict[str, dict[str, bool]] | None = None,
) -> dict[str, Any]:
    missing = [d for d in PILOT_SCORE_DIMS if d not in scores]
    if missing:
        raise PilotReviewError(
            "pilot scorecard missing: "
            + ", ".join(f"--score-{d}" for d in missing)
            + f" (required: {', '.join(PILOT_SCORE_DIMS)})"
        )
    if not shots:
        raise PilotReviewError("pilot scorecard needs at least one shot id")
    if not (reviewer or "").strip():
        raise PilotReviewError("pilot scorecard requires --reviewer")
    if not (notes or "").strip():
        raise PilotReviewError("pilot scorecard requires --notes")

    dims: dict[str, bool] = {}
    for d in PILOT_SCORE_DIMS:
        try:
            dims[d] = normalize_score_value(scores[d], field=f"score.{d}")
        except DirectorReviewError as exc:
            raise PilotReviewError(str(exc)) from exc
    all_pass = all(dims.values())
    failures = [d for d, ok in dims.items() if not ok]

    per: dict[str, Any] = {}
    if per_shot:
        for sid, card in per_shot.items():
            per[sid] = {d: bool(card.get(d)) for d in PILOT_SCORE_DIMS}

    return {
        "schema_version": 1,
        "kind": "pilot-scorecard",
        "created_at": utc_now(),
        "shots": list(shots),
        "reviewer": reviewer.strip(),
        "notes": notes.strip(),
        "dimensions": dims,
        "all_pass": all_pass,
        "failures": failures,
        "per_shot": per or None,
        "checklist": {
            "identity": "脸/发型/服装/签名配件 vs cast master",
            "style": "介质/色板/线稿 vs style-v1（无换模感）",
            "motion": "真实动态可见；静戏有 blink/breath/push-in",
        },
        "next": (
            ['aifilm pilot-approve --root … --user-phrase "pilot 过" --shots ' + ",".join(shots)]
            if all_pass
            else [
                "修 still/I2V 后重跑 pilot-score",
                "失败维度: " + ", ".join(failures),
            ]
        ),
    }


def write_pilot_scorecard(root: Path, card: dict[str, Any]) -> Path:
    try:
        receipts = safe_workspace_directory(root, "receipts", field="receipts")
    except SecurityPolicyError as exc:
        raise PilotReviewError(str(exc)) from exc
    receipts.mkdir(parents=True, exist_ok=True)
    path = pilot_scorecard_path(root)
    write_json(path, card)
    return path


def fail_scorecard_to_director_notes(
    root: Path,
    card: dict[str, Any],
    *,
    enabled: bool = True,
) -> list[dict[str, Any]]:
    """When pilot score has fails, open director_notes reshoot items for each shot×dim."""
    if not enabled:
        return []
    failures = [str(x) for x in (card.get("failures") or []) if x]
    shots = [str(x) for x in (card.get("shots") or []) if x]
    if not failures or not shots:
        return []
    try:
        from director_review import add_reshoot_item, empty_director_notes
    except ImportError:
        return []

    notes_path = Path(root).expanduser().resolve() / "director_notes.json"
    package = read_json(notes_path) if notes_path.is_file() else empty_director_notes()
    if not package:
        package = empty_director_notes()
    created: list[dict[str, Any]] = []
    note_txt = str(card.get("notes") or "pilot score fail")
    for sid in shots:
        for dim in failures:
            if dim not in {"identity", "style", "motion"}:
                continue
            item = add_reshoot_item(
                package,
                action="reshoot",
                reason_code=dim,
                note=f"pilot-scorecard: {note_txt}",
                shot_id=sid,
                source="pilot-scorecard",
            )
            created.append(item)
    package["source"] = "pilot-scorecard"
    package["scorecard"] = {
        "dimensions": card.get("dimensions"),
        "all_pass": card.get("all_pass"),
        "failures": failures,
    }
    write_json(notes_path, package)
    return created


def load_pilot_scorecard(root: Path) -> dict[str, Any]:
    return read_json(pilot_scorecard_path(root))


def pilot_scorecard_ready(card: dict[str, Any] | None) -> bool:
    if not isinstance(card, dict) or card.get("kind") != "pilot-scorecard":
        return False
    dims = card.get("dimensions")
    if not isinstance(dims, dict):
        return False
    return all(dims.get(d) is True for d in PILOT_SCORE_DIMS)


def user_phrase_is_approval(phrase: str) -> bool:
    """Detect user pilot approval intent (never invent approval for the agent).

    Accepts short confirmations like 「可以」「ok」and run-to-completion phrasing
    like 「直接做到生成完成」, while rejecting 「可以改 / 不行 / 重做」.
    """
    p = (phrase or "").strip()
    if not p:
        return False
    low = p.lower()
    # Explicit rejections / revision requests — not approval
    reject_markers = (
        "不行",
        "不过",
        "不批",
        "重做",
        "重拍",
        "改一下",
        "改一改",
        "修改",
        "fail",
        "reject",
        "no pass",
        "not ok",
    )
    if any(m in p or m in low for m in reject_markers):
        return False
    markers = (
        "pilot 过",
        "pilot过",
        "pilot ok",
        "pilot pass",
        "pilot passed",
        "user approved pilot",
        "定妆过了",
        "三镜过了",
        "可以批量",
        "可以量产",
        "可以继续",
        "可以",  # short ok — reject_markers already filtered 「可以改」
        "生成完成",
        "做到完成",
        "做成完整",
        "做成全片",
        "做完",
        "一路做完",
        "直接完成",
        "直接进行到生成完成",
        "继续做完",
        "完整 60",
        "完整60",
        "run to completion",
        "go ahead",
        "lgtm",
        "looks good",
        "approved",
    )
    if any(m in p or m in low for m in markers):
        return True
    # Exact short affirmations only (avoid matching random long text)
    return low in {"ok", "okay", "yes", "y", "好", "好的", "行", "过", "通过"}


def user_phrase_wants_run_to_completion(phrase: str) -> bool:
    """User wants bulk → final without another stop after pilot approve."""
    p = (phrase or "").strip()
    if not p:
        return False
    low = p.lower()
    markers = (
        "生成完成",
        "做到完成",
        "做成完整",
        "做成全片",
        "做完",
        "一路做完",
        "直接完成",
        "直接进行",
        "继续做完",
        "一口气",
        "跑完",
        "到成片",
        "完整 60",
        "完整60",
        "到 final",
        "到final",
        "run to completion",
        "finish the film",
        "all the way",
    )
    return any(m in p or m in low for m in markers)


def build_pilot_approval(
    *,
    shots: list[str],
    user_phrase: str,
    notes: str = "",
    compared_to_cast: str | None = None,
    scorecard: dict[str, Any] | None = None,
    require_scorecard: bool = True,
) -> dict[str, Any]:
    if not shots:
        raise PilotReviewError("pilot-approve needs --shots")
    if not user_phrase_is_approval(user_phrase):
        raise PilotReviewError(
            "pilot-approve 需要用户原话痕迹（如「pilot 过」「可以批量」）。"
            f" got user_phrase={user_phrase!r}。禁止 agent 自拟批准。"
        )
    if require_scorecard:
        if not pilot_scorecard_ready(scorecard):
            raise PilotReviewError(
                "pilot-approve 默认要求 pilot-scorecard 三维全 pass。"
                "先 aifilm pilot-score … 或显式 --no-require-scorecard（不推荐）"
            )
    phrase = user_phrase.strip()
    payload = {
        "approved": True,
        "approved_by": "user",
        "user_phrase": phrase,
        "shots": list(shots),
        "compared_to_cast": compared_to_cast,
        "notes": (notes or "").strip() or f"user: {phrase}",
        "approved_at": utc_now(),
        "scorecard_ref": "receipts/pilot-scorecard.json" if scorecard else None,
        "scorecard_all_pass": pilot_scorecard_ready(scorecard) if scorecard else None,
        "run_to_completion": user_phrase_wants_run_to_completion(phrase),
        "schema_version": 1,
    }
    return payload


def write_pilot_approval(root: Path, approval: dict[str, Any]) -> Path:
    try:
        receipts = safe_workspace_directory(root, "receipts", field="receipts")
    except SecurityPolicyError as exc:
        raise PilotReviewError(str(exc)) from exc
    receipts.mkdir(parents=True, exist_ok=True)
    path = pilot_approval_path(root)
    write_json(path, approval)
    return path


def pilot_report(root: Path, *, shots: list[str] | None = None) -> dict[str, Any]:
    root = root.expanduser().resolve()
    spec_path = root / "film-spec.json"
    man_path = root / "manifest.json"
    if not spec_path.is_file():
        raise PilotReviewError("film-spec.json missing")
    if not man_path.is_file():
        raise PilotReviewError("manifest.json missing")
    spec = read_json(spec_path)
    manifest = read_json(man_path)
    picked = shots or pick_pilot_shots(spec)
    media = [media_status_for_shot(root, manifest, sid) for sid in picked]
    scorecard = load_pilot_scorecard(root)
    approval = load_pilot_approval(root)
    ready_count = sum(1 for m in media if m.get("ready_for_batch_sample"))
    return {
        "ok": True,
        "root": str(root),
        "pilot_max_without_approval": PILOT_MAX_SHOTS_WITHOUT_APPROVAL,
        "suggested_shots": pick_pilot_shots(spec),
        "shots": picked,
        "media": media,
        "ready_count": ready_count,
        "all_media_ready": ready_count == len(picked) and len(picked) > 0,
        "scorecard": scorecard or None,
        "scorecard_all_pass": pilot_scorecard_ready(scorecard),
        "approval": approval or None,
        "user_approved": pilot_is_user_approved(approval),
        "checklist": {
            "identity": "vs cast master",
            "style": "vs style-v1 medium/palette",
            "motion": "real motion / micro-motion on reaction shots",
        },
        "next": _next_actions(
            all_media_ready=ready_count == len(picked) and len(picked) > 0,
            score_ok=pilot_scorecard_ready(scorecard),
            approved=pilot_is_user_approved(approval),
            shots=picked,
        ),
    }


def _next_actions(
    *,
    all_media_ready: bool,
    score_ok: bool,
    approved: bool,
    shots: list[str],
) -> list[str]:
    if approved:
        return ["pilot 已用户批准 → 可 bulk media-queue add"]
    shot_csv = ",".join(shots)
    if not all_media_ready:
        return [
            f"先生成并 register pilot 三镜 still+clip: {shot_csv}",
            "再 aifilm pilot-report --root …",
        ]
    if not score_ok:
        return [
            f"aifilm pilot-score --root … --shots {shot_csv} "
            "--score-identity pass --score-style pass --score-motion pass "
            '--reviewer <you> --notes "…"',
        ]
    return [
        f'aifilm pilot-approve --root … --shots {shot_csv} --user-phrase "pilot 过"',
    ]


def _parse_scores(args: argparse.Namespace) -> dict[str, bool]:
    scores: dict[str, bool] = {}
    for dim in PILOT_SCORE_DIMS:
        val = getattr(args, f"score_{dim}", None)
        if val is None:
            continue
        try:
            scores[dim] = normalize_score_value(val, field=f"--score-{dim}")
        except DirectorReviewError as exc:
            raise PilotReviewError(str(exc)) from exc
    return scores


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pilot scorecard assist")
    sub = p.add_subparsers(dest="action", required=True)

    pick = sub.add_parser("pick", help="Suggest pilot shot ids")
    pick.add_argument("--root", required=True)
    pick.add_argument("--n", type=int, default=PILOT_MAX_SHOTS_WITHOUT_APPROVAL)

    rep = sub.add_parser("report", help="Pilot media + scorecard + approval status")
    rep.add_argument("--root", required=True)
    rep.add_argument("--shots", default="", help="Comma shot ids (default: auto-pick)")

    sc = sub.add_parser("score", help="Write receipts/pilot-scorecard.json")
    sc.add_argument("--root", required=True)
    sc.add_argument("--shots", required=True, help="Comma shot ids")
    sc.add_argument("--reviewer", required=True)
    sc.add_argument("--notes", required=True)
    for dim in PILOT_SCORE_DIMS:
        sc.add_argument(f"--score-{dim}", choices=["pass", "fail"], required=True)
    sc.add_argument(
        "--no-notes-on-fail",
        action="store_true",
        help="Do not write director_notes reshoot items when score fails",
    )

    ap = sub.add_parser("approve", help="Write user pilot-approval.json (needs user phrase)")
    ap.add_argument("--root", required=True)
    ap.add_argument("--shots", default="", help="Comma shot ids (default: from scorecard or pick)")
    ap.add_argument("--user-phrase", required=True, help='User words e.g. "pilot 过"')
    ap.add_argument("--notes", default="")
    ap.add_argument("--compared-to-cast", default=None)
    ap.add_argument(
        "--no-require-scorecard",
        action="store_true",
        help="Allow approve without pilot-scorecard all-pass (not recommended)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = Path(args.root).expanduser().resolve()
        if args.action == "pick":
            spec = read_json(root / "film-spec.json")
            if not spec:
                raise PilotReviewError("film-spec.json missing")
            shots = pick_pilot_shots(spec, n=int(args.n))
            print(
                json.dumps(
                    {"ok": True, "shots": shots, "n": len(shots)},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.action == "report":
            shots = [s.strip() for s in str(args.shots or "").split(",") if s.strip()] or None
            print(json.dumps(pilot_report(root, shots=shots), ensure_ascii=False, indent=2))
            return 0
        if args.action == "score":
            shots = [s.strip() for s in str(args.shots).split(",") if s.strip()]
            scores = _parse_scores(args)
            card = build_pilot_scorecard(
                shots=shots,
                scores=scores,
                reviewer=str(args.reviewer),
                notes=str(args.notes),
            )
            path = write_pilot_scorecard(root, card)
            notes_items = fail_scorecard_to_director_notes(
                root,
                card,
                enabled=not bool(getattr(args, "no_notes_on_fail", False)),
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "path": str(path),
                        "scorecard": card,
                        "director_notes_items": notes_items,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.action == "approve":
            scorecard = load_pilot_scorecard(root)
            shots = [s.strip() for s in str(args.shots or "").split(",") if s.strip()]
            if not shots and isinstance(scorecard.get("shots"), list):
                shots = [str(x) for x in scorecard["shots"]]
            if not shots:
                spec = read_json(root / "film-spec.json")
                shots = pick_pilot_shots(spec) if spec else []
            approval = build_pilot_approval(
                shots=shots,
                user_phrase=str(args.user_phrase),
                notes=str(args.notes or ""),
                compared_to_cast=args.compared_to_cast,
                scorecard=scorecard or None,
                require_scorecard=not bool(args.no_require_scorecard),
            )
            path = write_pilot_approval(root, approval)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "path": str(path),
                        "approval": approval,
                        "user_approved": pilot_is_user_approved(approval),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        raise PilotReviewError(f"unknown action {args.action}")
    except PilotReviewError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
