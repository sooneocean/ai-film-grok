"""Receipt-backed, no-implicit-spend experiment contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from optimization_metrics import emit_metrics
from util import canonical_json_sha256, read_json, utc_now, write_json

EXPERIMENT_VERSION = 1
CANARY_SUITE = (
    {"id": "C-identity", "minimum_shots": 3, "focus": "identity"},
    {"id": "C-motion", "minimum_shots": 2, "focus": "motion"},
    {"id": "C-continue", "minimum_shots": 3, "focus": "continuity"},
    {"id": "C-audio", "minimum_seconds": 20, "focus": "audio-captions"},
    {"id": "C-genre", "minimum_shots": 1, "focus": "narrative"},
)


def _base(root: Path | str, experiment_id: str) -> Path:
    cleaned = str(experiment_id).strip()
    if not cleaned or any(token in cleaned for token in ("/", "\\", "..")):
        raise ValueError("experiment id must be a safe local identifier")
    return Path(root).expanduser().resolve() / "receipts" / "experiments" / cleaned


def init_experiment(
    root: Path | str,
    *,
    experiment_id: str,
    hypothesis: str,
    treatment_axis: str,
    primary_metric: str,
    min_effect: float,
    fixtures: list[str],
    seed: str,
    shot_count: int,
    aspect: str,
    duration_budget_sec: float,
) -> dict[str, Any]:
    if not hypothesis.strip() or not treatment_axis.strip() or not primary_metric.strip():
        raise ValueError("hypothesis, treatment_axis, and primary_metric are required")
    if len([item for item in treatment_axis.split(",") if item.strip()]) != 1:
        raise ValueError("exactly one treatment axis is allowed")
    if min_effect <= 0 or shot_count <= 0 or duration_budget_sec <= 0 or not fixtures or not seed:
        raise ValueError(
            "min_effect, fixtures, seed, shot_count, and duration budget must be positive/non-empty"
        )
    target = _base(root, experiment_id)
    manifest = target / "experiment.json"
    if manifest.exists():
        raise ValueError(f"experiment already exists: {experiment_id}")
    data = {
        "schema_version": EXPERIMENT_VERSION,
        "kind": "optimization-experiment",
        "id": experiment_id,
        "created_at": utc_now(),
        "hypothesis": hypothesis.strip(),
        "treatment_axis": treatment_axis.strip(),
        "primary_metric": primary_metric.strip(),
        "min_effect": min_effect,
        "fixture_contract": {
            "fixtures": fixtures,
            "seed": seed,
            "shot_count": shot_count,
            "aspect": aspect,
            "duration_budget_sec": duration_budget_sec,
            "repeat": 3,
        },
        "canary_suite": list(CANARY_SUITE),
        "arms": {},
        "decision": None,
    }
    data["content_sha256"] = canonical_json_sha256(data)
    write_json(manifest, data)
    return data


def _read(root: Path | str, experiment_id: str) -> tuple[Path, dict[str, Any]]:
    target = _base(root, experiment_id)
    data = read_json(target / "experiment.json")
    if not isinstance(data, dict):
        raise ValueError("experiment is missing or corrupt")
    return target, data


def import_arm(
    root: Path | str,
    *,
    experiment_id: str,
    arm: str,
    metrics_root: Path | str,
    config: dict[str, Any],
) -> dict[str, Any]:
    if arm not in {"baseline", "treatment"}:
        raise ValueError("arm must be baseline|treatment")
    target, experiment = _read(root, experiment_id)
    metrics = emit_metrics(metrics_root, run_id=f"{experiment_id}:{arm}")
    contract = experiment["fixture_contract"]
    candidate = {
        key: config.get(key)
        for key in ("fixtures", "seed", "shot_count", "aspect", "duration_budget_sec")
    }
    expected = {
        "fixtures": contract["fixtures"],
        "seed": contract["seed"],
        "shot_count": contract["shot_count"],
        "aspect": contract["aspect"],
        "duration_budget_sec": contract["duration_budget_sec"],
    }
    if candidate != expected:
        raise ValueError("arm config must exactly match the experiment fixture contract")
    arm_payload = {
        "metrics_root": str(Path(metrics_root).expanduser().resolve()),
        "metrics_sha256": metrics["content_sha256"],
        "metrics": metrics,
        "config": config,
        "imported_at": utc_now(),
    }
    experiment.setdefault("arms", {})[arm] = arm_payload
    experiment["content_sha256"] = canonical_json_sha256(
        {key: value for key, value in experiment.items() if key != "content_sha256"}
    )
    write_json(target / "experiment.json", experiment)
    return experiment


def run_request(
    root: Path | str, *, experiment_id: str, arm: str, authorize_spend: bool, max_usd: float | None
) -> dict[str, Any]:
    """Persist an execution request; provider dispatch remains explicit and external."""
    if arm not in {"baseline", "treatment"}:
        raise ValueError("arm must be baseline|treatment")
    if authorize_spend != (max_usd is not None):
        raise ValueError("--authorize-spend and --max-usd must be provided together")
    if max_usd is not None and max_usd <= 0:
        raise ValueError("max_usd must be > 0")
    target, experiment = _read(root, experiment_id)
    receipt = {
        "schema_version": 1,
        "kind": "experiment-run-request",
        "experiment_id": experiment_id,
        "arm": arm,
        "requested_at": utc_now(),
        "spend_authorized": authorize_spend,
        "max_usd": max_usd,
        "execution": "manual_provider_dispatch_required",
        "reason": "The optimisation layer never dispatches provider jobs or changes routing defaults.",
    }
    write_json(target / "run-requests" / f"{arm}.json", receipt)
    return receipt


def _value(metrics: dict[str, Any], metric: str) -> float | None:
    lookup = {
        "cost_usd": ("l3", "cost_usd"),
        "wall_sec": ("l3", "wall_sec_init_to_verified"),
        "grade_p50": ("l2", "grade_summary", "p50"),
        "motion_p10": ("l1", "motion_score", "p10"),
    }
    path = lookup.get(metric)
    if not path:
        return None
    value: Any = metrics
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _metric_evidence_known(metrics: dict[str, Any], metric: str) -> bool:
    if metrics.get("data_quality", {}).get("state") != "known":
        return False
    if metric == "cost_usd":
        return metrics.get("l3", {}).get("i2v_cost_state") == "known"
    if metric == "wall_sec":
        return metrics.get("l3", {}).get("wall_sec_init_to_verified") is not None
    if metric == "grade_p50":
        return metrics.get("l2", {}).get("grade_summary", {}).get("state") == "known"
    if metric == "motion_p10":
        return metrics.get("l1", {}).get("motion_score", {}).get("state") == "known"
    return False


def diff_experiment(root: Path | str, *, experiment_id: str) -> dict[str, Any]:
    target, experiment = _read(root, experiment_id)
    arms = experiment.get("arms") or {}
    if not isinstance(arms.get("baseline"), dict) or not isinstance(arms.get("treatment"), dict):
        raise ValueError("both baseline and treatment must be imported")
    baseline, treatment = arms["baseline"]["metrics"], arms["treatment"]["metrics"]
    metric = experiment["primary_metric"]
    before, after = _value(baseline, metric), _value(treatment, metric)
    unknown = (
        before is None
        or after is None
        or not _metric_evidence_known(baseline, metric)
        or not _metric_evidence_known(treatment, metric)
    )
    change = None if unknown or before == 0 else (after - before) / abs(before)
    l0_ok = bool(baseline.get("l0", {}).get("all_pass")) and bool(
        treatment.get("l0", {}).get("all_pass")
    )
    report = {
        "schema_version": 1,
        "kind": "experiment-diff",
        "experiment_id": experiment_id,
        "primary_metric": metric,
        "baseline": before,
        "treatment": after,
        "relative_change": change,
        "l0_non_regression": l0_ok,
        "unknown": unknown,
        "adoption": "insufficient_evidence" if unknown else "pending_decision",
    }
    write_json(target / "diff.json", report)
    return report


def decide(root: Path | str, *, experiment_id: str, decision: str) -> dict[str, Any]:
    if decision not in {"ship", "reject"}:
        raise ValueError("decision must be ship|reject")
    target, experiment = _read(root, experiment_id)
    diff = read_json(target / "diff.json")
    if not isinstance(diff, dict):
        raise ValueError("run experiment diff before deciding")
    permitted = not diff.get("unknown") and bool(diff.get("l0_non_regression"))
    if decision == "ship":
        metric = experiment["primary_metric"]
        change = diff.get("relative_change")
        threshold = float(experiment["min_effect"])
        lower_is_better = metric in {"cost_usd", "wall_sec"}
        achieved = isinstance(change, (int, float)) and (
            (-change >= threshold) if lower_is_better else (change >= threshold)
        )
        if not permitted or not achieved:
            raise ValueError("ship rejected: adoption evidence does not meet the contract")
    receipt = {
        "schema_version": 1,
        "kind": "experiment-decision",
        "experiment_id": experiment_id,
        "decision": decision,
        "decided_at": utc_now(),
        "automatic_apply": False,
        "diff_sha256": canonical_json_sha256(diff),
    }
    experiment["decision"] = receipt
    experiment["content_sha256"] = canonical_json_sha256(
        {key: value for key, value in experiment.items() if key != "content_sha256"}
    )
    write_json(target / "experiment.json", experiment)
    write_json(target / "decision.json", receipt)
    return receipt
