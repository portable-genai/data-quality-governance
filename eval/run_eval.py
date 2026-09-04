#!/usr/bin/env python3
"""Evaluation gate for Data Quality and Governance Agent (H4).

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change: it drives the REAL
  deterministic engines and the certification orchestrator against a golden set with SDK-free local
  adapters and scores the ``h4-data-quality`` bundle. * **gate** - the promotion verdict from the
  shared model-quality-gate authority (requires the ``gcp`` profile), via
  ``agent_eval_kit.PromotionGateClient``.

Every metric scores against the DATASET'S OWN ``expected_*`` label (an independent golden
oracle), NEVER against the pipeline's own verdict, and every metric is proved able to go RED via
``agent_eval_kit.assert_each_can_go_red`` before the report is trusted. Exit is ``0`` iff every
metric meets its threshold (and, in gate mode, the authority agrees).
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from pathlib import Path
from typing import Any

from agent_eval_kit import (
    EvalMetricResult,
    EvalReport,
    PromotionGateClient,
    assert_can_go_red,
    assert_each_can_go_red,
    eval_main,
)

from data_quality_governance.config import Settings, build_container
from data_quality_governance.domain import (
    dq_rule_engine,
    drift_service,
    profile_service,
)
from data_quality_governance.domain.certification_service import (
    CertificationService,
    ScorecardStore,
)
from data_quality_governance.domain.kernel import Severity
from data_quality_governance.domain.models import (
    ColumnSample,
    Rule,
    RulePack,
    RuleType,
    SchemaColumn,
    TableMetadata,
)
from data_quality_governance.domain.pii_classifier import PiiClassifier
from data_quality_governance.domain.thresholds import bundle_thresholds
from data_quality_governance.service_factory import build_certification_service

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"

THRESHOLDS: dict[str, float] = bundle_thresholds("h4-data-quality")
#: The registered model-quality-gate metric bundle for this vertical (model-quality-gate owns the
#: metrics + thresholds).
_BUNDLE = "h4-data-quality"

_NUM = re.compile(r"\d+(?:\.\d+)?")


def _load(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 1.0


# --------------------------------------------------------------------------- scorers (pure)


def _finding_correct(case: dict[str, Any]) -> float:
    """1.0 when the engine's pass/fail matches the row's independent expected_pass."""
    values = tuple(str(v) for v in case["values"])
    meta = TableMetadata("d", len(values), "2026-01-01T00:00:00", "2026-01-01T00:00:00")
    profile = profile_service.profile_dataset(
        meta, (ColumnSample(case["column"], values),), as_of="x"
    )
    rule = Rule(
        id="r",
        rule_type=RuleType(case["rule_type"]),
        column=case["column"],
        severity=Severity.HIGH,
        owner="o",
        description="d",
        params=tuple((k, str(v)) for k, v in case.get("params", {}).items()),
    )
    findings = dq_rule_engine.evaluate(
        RulePack("d", "o", 24, (rule,)),
        profile,
        {case["column"]: ColumnSample(case["column"], values)},
        age_hours=1.0,
    )
    return 1.0 if findings[0].passed == bool(case["expected_pass"]) else 0.0


def _drift_counts(case: dict[str, Any]) -> tuple[int, int, int]:
    """Return (true positives, predicted, expected) for one drift row."""
    base = tuple(SchemaColumn(n, t) for n, t in case["baseline"])
    live = tuple(SchemaColumn(n, t) for n, t in case["live"])
    predicted = {f.kind.value for f in drift_service.diff_schema("d", base, live)}
    expected = set(case["expected_kinds"])
    return len(predicted & expected), len(predicted), len(expected)


def _pii_predicts_pii(case: dict[str, Any]) -> bool:
    values = tuple(str(v) for v in case["values"])
    prof = profile_service.profile_column(ColumnSample(case["column"], values))
    result = PiiClassifier().classify("d", prof, ColumnSample(case["column"], values))
    return result.category.value != "non_pii"


def _pii_correct(case: dict[str, Any]) -> float:
    return 1.0 if _pii_predicts_pii(case) == bool(case["expected_pii"]) else 0.0


# --------------------------------------------------------------------------- smoke


def _fresh_service() -> CertificationService:
    service = build_certification_service(
        build_container(Settings(profile="local", audit_path=":memory:"))
    )
    service._store = ScorecardStore()
    return service


def run_smoke(dataset: Path) -> EvalReport:
    cases = _load(dataset)
    _prove_metrics_can_go_red()

    verdict, review, grounded = [], [], []
    findings, drift_tp, drift_pred, drift_exp, pii = [], 0, 0, 0, []

    service = _fresh_service()
    for case in cases:
        kind = case["kind"]
        if kind == "verdict":
            result = service.certify(case["dataset_id"], actor="eval-bot", tenant="eval")
            verdict.append(1.0 if result.status.value == case["expected_status"] else 0.0)
            review.append(
                1.0
                if result.requires_human_review == bool(case["expected_requires_review"])
                else 0.0
            )
            grounded.append(_narrative_grounded(result))
        elif kind == "finding":
            findings.append(_finding_correct(case))
        elif kind == "drift":
            tp, pred, exp = _drift_counts(case)
            drift_tp, drift_pred, drift_exp = drift_tp + tp, drift_pred + pred, drift_exp + exp
        elif kind == "pii":
            pii.append(_pii_correct(case))

    recall = round(drift_tp / drift_exp, 4) if drift_exp else 1.0
    precision = round(drift_tp / drift_pred, 4) if drift_pred else 1.0

    results = (
        EvalMetricResult.scored(
            "finding_accuracy", _mean(findings), THRESHOLDS["finding_accuracy"]
        ),
        EvalMetricResult.scored("drift_recall", recall, THRESHOLDS["drift_recall"]),
        EvalMetricResult.scored("drift_precision", precision, THRESHOLDS["drift_precision"]),
        EvalMetricResult.scored("pii_f1", _mean(pii), THRESHOLDS["pii_f1"]),
        EvalMetricResult.scored("verdict_accuracy", _mean(verdict), THRESHOLDS["verdict_accuracy"]),
        EvalMetricResult.scored(
            "narrative_groundedness", _mean(grounded), THRESHOLDS["narrative_groundedness"]
        ),
        EvalMetricResult.scored("review_safety", _mean(review), THRESHOLDS["review_safety"]),
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(cases))


def _narrative_grounded(result: Any) -> float:
    """Every number the narrative states must appear in the engine's structured output.

    Grounded by construction here (the narrator only echoes engine facts), which is exactly what
    this metric checks: a drafting model that invented a figure would score below 1.0.
    """
    facts = {str(result.pass_ratio), str(len(result.dq_findings))}
    facts |= {str(sum(1 for f in result.dq_findings if not f.passed))}
    if result.freshness is not None:
        facts |= {str(result.freshness.age_hours), str(result.freshness.sla_hours)}
    facts |= {
        str(len(result.drift)),
        str(sum(1 for c in result.pii if c.category.value == "sensitive")),
    }
    numbers = set(_NUM.findall(result.narrative))
    if not numbers:
        return 1.0
    return round(sum(1 for n in numbers if n in facts) / len(numbers), 4)


def _verdict_score(case: dict[str, Any]) -> float:
    """1.0 when the engine's verdict equals the row's INDEPENDENT ``expected_status``."""
    result = _fresh_service().certify(case["dataset_id"], actor="rb", tenant="rb")
    return 1.0 if result.status.value == case["expected_status"] else 0.0


def _review_score(case: dict[str, Any]) -> float:
    """1.0 when the engine's review flag equals the row's independent expected-review label."""
    result = _fresh_service().certify(case["dataset_id"], actor="rb", tenant="rb")
    return 1.0 if result.requires_human_review == bool(case["expected_requires_review"]) else 0.0


def _drift_recall_case(case: dict[str, Any]) -> float:
    """Per-case recall: 1.0 iff every expected drift kind was predicted (no misses)."""
    tp, _pred, exp = _drift_counts(case)
    return 1.0 if tp == exp else 0.0


def _drift_precision_case(case: dict[str, Any]) -> float:
    """Per-case precision: 1.0 iff every predicted drift kind was expected (no false positives)."""
    tp, pred, _exp = _drift_counts(case)
    return 1.0 if tp == pred else 0.0


def _prove_metrics_can_go_red() -> None:
    """A metric that cannot go red is not a metric. Prove ALL SEVEN on crafted green/red pairs.

    Every scored metric in :func:`run_smoke` is proven here (finding accuracy, drift recall and
    precision, PII F1, verdict accuracy, narrative groundedness and review safety), so the report
    the gate trusts carries no metric that would score a vacuous green on the very defect it
    exists to catch.
    """
    uniq = {"rule_type": "uniqueness", "params": {"min_unique_ratio": "1.0"}, "expected_pass": True}
    assert_each_can_go_red(
        _finding_correct,
        {
            "uniqueness": (
                {"column": "id", "values": ["1", "2"], **uniq},
                {"column": "id", "values": ["1", "1"], **uniq},
            )
        },
        threshold=THRESHOLDS["finding_accuracy"],
        metric="finding_accuracy",
    )
    email = ["a@x.example", "b@y.example"]
    assert_each_can_go_red(
        _pii_correct,
        {
            "email": (
                {"column": "email", "values": email, "expected_pii": True},
                {"column": "email", "values": email, "expected_pii": False},
            )
        },
        threshold=THRESHOLDS["pii_f1"],
        metric="pii_f1",
    )
    # One schema pair the engine reads as a REMOVED column, labelled truthfully (green) then
    # mislabelled as an addition (red): recall misses it, and precision counts it a false positive.
    base = {"baseline": [["a", "STRING"], ["b", "STRING"]], "live": [["a", "STRING"]]}
    right = {**base, "expected_kinds": ["removed"]}
    wrong = {**base, "expected_kinds": ["added"]}
    assert_each_can_go_red(
        _drift_recall_case,
        {"removed": (right, wrong)},
        threshold=THRESHOLDS["drift_recall"],
        metric="drift_recall",
    )
    assert_each_can_go_red(
        _drift_precision_case,
        {"removed": (right, wrong)},
        threshold=THRESHOLDS["drift_precision"],
        metric="drift_precision",
    )
    # Verdict accuracy and review safety run the REAL certification engine over a fixture dataset;
    # the green row carries the true label, the red row the opposite, so a metric that could not
    # tell a right verdict from a wrong one, or a routed escalation from a dropped one, fails here.
    assert_each_can_go_red(
        _verdict_score,
        {
            "certified": (
                {"dataset_id": "customer_master", "expected_status": "certified"},
                {"dataset_id": "customer_master", "expected_status": "uncertified"},
            )
        },
        threshold=THRESHOLDS["verdict_accuracy"],
        metric="verdict_accuracy",
    )
    assert_each_can_go_red(
        _review_score,
        {
            "sensitive": (
                {"dataset_id": "marketing_events", "expected_requires_review": True},
                {"dataset_id": "marketing_events", "expected_requires_review": False},
            )
        },
        threshold=THRESHOLDS["review_safety"],
        metric="review_safety",
    )
    # Narrative groundedness: the real (grounded) narrative scores 1.0; the same scorecard with an
    # invented figure spliced into its narrative must score below the bar, or the metric could not
    # catch a drafting model that fabricated a number.
    grounded = _fresh_service().certify("marketing_events", actor="rb", tenant="rb")
    fabricated = dataclasses.replace(
        grounded, narrative=grounded.narrative + " An unsupported figure 987654 appears."
    )
    assert_can_go_red(
        _narrative_grounded,
        green=grounded,
        red=fabricated,
        threshold=THRESHOLDS["narrative_groundedness"],
        metric="narrative_groundedness",
    )


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"DATAQUALITY_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    client = PromotionGateClient(
        os.environ.get("DATAQUALITY_QUALITY_URL", "http://localhost:8084"),
        bundle=_BUNDLE,
        model="gemini-3.5-flash",
    )
    return client.evaluate(str(dataset)), client.gate(str(dataset))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / model-quality-gate for H4.",
        )
    )
