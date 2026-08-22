"""Fold every check into one cited scorecard and a deterministic certification verdict.

The verdict is PURE code, replayable, and the wire H1 consumes. A model produces no part of it;
the ``narrative`` field is a deterministic, grounded description (every figure it states is
lifted from the engine outputs, never invented), which is the seam a real drafting model would
later replace while the numbers stay owned by the engine.

Verdict ladder (fail-closed):

* **UNCERTIFIED** when any HIGH/CRITICAL check fails: a failed high-severity DQ rule, a stale
  dataset (freshness breached at HIGH+), or breaking schema drift (a removed or retyped column).
  Also when the DQ pass ratio falls below the conditional bar.
* **CONDITIONAL** when only MEDIUM/LOW issues remain and the pass ratio clears the conditional
  bar: usable, with the open items tracked as tickets.
* **CERTIFIED** when the pass ratio clears the certified bar, nothing high-severity is open, the
  data is fresh, and no sensitive-category PII column is awaiting review.

``requires_human_review`` (rule R8) is set for the two consequential outcomes the plan names:
DECERTIFYING a previously certified dataset, and ANY sensitive-category PII finding.
"""

from __future__ import annotations

from .kernel import Citation, Decision, Severity
from .models import (
    CertificationResponse,
    CertificationStatus,
    ColumnCategory,
    DatasetScorecard,
    DQFinding,
    DriftFinding,
    FreshnessResult,
    LineageImpact,
    PiiClassification,
    RemediationTicket,
)
from .thresholds import CERT_MIN_PASS_RATIO, CONDITIONAL_MIN_PASS_RATIO

_SEVERITY_ORDER = {Severity.CRITICAL: 3, Severity.HIGH: 2, Severity.MEDIUM: 1, Severity.LOW: 0}
_HIGH = (Severity.HIGH, Severity.CRITICAL)


def _has_sensitive(pii: tuple[PiiClassification, ...]) -> bool:
    return any(c.category is ColumnCategory.SENSITIVE for c in pii)


def _worst_severity(
    dq: tuple[DQFinding, ...],
    freshness: FreshnessResult | None,
    drift: tuple[DriftFinding, ...],
) -> Severity:
    severities = [f.severity for f in dq if not f.passed]
    severities += [d.severity for d in drift]
    if freshness is not None and freshness.breached:
        severities.append(freshness.severity)
    return max(severities, key=lambda s: _SEVERITY_ORDER[s], default=Severity.LOW)


def _certified_metrics(
    dq: tuple[DQFinding, ...], pii: tuple[PiiClassification, ...]
) -> tuple[str, ...]:
    """Columns safe for a downstream to build a metric on: all checks pass, not direct/sensitive.

    This is the list H1 reads to decide whether a requested metric's backing column is usable.
    """
    failed_cols = {f.column for f in dq if not f.passed}
    barred = {
        c.column for c in pii if c.category in (ColumnCategory.PII_DIRECT, ColumnCategory.SENSITIVE)
    }
    checked = {f.column for f in dq}
    return tuple(sorted(c for c in checked if c not in failed_cols and c not in barred))


def certify(
    dataset_id: str,
    *,
    pass_ratio: float,
    dq_findings: tuple[DQFinding, ...],
    freshness: FreshnessResult | None,
    drift: tuple[DriftFinding, ...],
    pii: tuple[PiiClassification, ...],
    tickets: tuple[RemediationTicket, ...],
    lineage: LineageImpact | None,
    as_of: str,
    prior_status: CertificationStatus | None = None,
) -> DatasetScorecard:
    """Fold the per-check results into a cited scorecard and a deterministic verdict."""
    high_dq = any(not f.passed and f.severity in _HIGH for f in dq_findings)
    stale = freshness is not None and freshness.breached and freshness.severity in _HIGH
    breaking_drift = any(d.severity in _HIGH for d in drift)
    sensitive = _has_sensitive(pii)

    blocking = high_dq or stale or breaking_drift
    if blocking or pass_ratio < CONDITIONAL_MIN_PASS_RATIO:
        status = CertificationStatus.UNCERTIFIED
    elif (
        pass_ratio >= CERT_MIN_PASS_RATIO
        and not any(d.severity is Severity.MEDIUM for d in drift)
        and not sensitive
    ):
        status = CertificationStatus.CERTIFIED
    else:
        status = CertificationStatus.CONDITIONAL

    decertified = (
        prior_status is CertificationStatus.CERTIFIED
        and status is not CertificationStatus.CERTIFIED
    )
    requires_review = decertified or sensitive
    decision = Decision.ESCALATED if requires_review else Decision.ALLOWED
    severity = _worst_severity(dq_findings, freshness, drift)

    certified_metrics = (
        () if status is CertificationStatus.UNCERTIFIED else _certified_metrics(dq_findings, pii)
    )
    summary = f"{dataset_id}: {status.value} (pass_ratio {pass_ratio})"
    narrative = narrate(
        dataset_id, status, pass_ratio, dq_findings, freshness, drift, pii, decertified
    )

    citations = _collect_citations(dq_findings, freshness, drift, pii)
    return DatasetScorecard(
        subject=dataset_id,
        status=status,
        decision=decision,
        severity=severity,
        summary=summary,
        requires_human_review=requires_review,
        pass_ratio=pass_ratio,
        dq_findings=dq_findings,
        freshness=freshness,
        drift=drift,
        pii=pii,
        tickets=tickets,
        lineage=lineage,
        certified_metrics=certified_metrics,
        narrative=narrative,
        citations=citations,
    )


def _collect_citations(
    dq: tuple[DQFinding, ...],
    freshness: FreshnessResult | None,
    drift: tuple[DriftFinding, ...],
    pii: tuple[PiiClassification, ...],
) -> tuple[Citation, ...]:
    cites = [f.citation for f in dq]
    if freshness is not None:
        cites.append(freshness.citation)
    cites += [d.citation for d in drift]
    cites += [c.citation for c in pii]
    return tuple(cites)


def narrate(
    dataset_id: str,
    status: CertificationStatus,
    pass_ratio: float,
    dq: tuple[DQFinding, ...],
    freshness: FreshnessResult | None,
    drift: tuple[DriftFinding, ...],
    pii: tuple[PiiClassification, ...],
    decertified: bool,
) -> str:
    """A deterministic, grounded one-paragraph description. Every figure comes from the engine.

    This stands in for a drafting model: a real model would replace this text, its output
    schema-validated and DISCARDED on failure, over PII-redacted input. Because this version
    states only counts the engine produced, it is grounded by construction, which is exactly the
    property the narrative-groundedness metric checks.
    """
    failed = sum(1 for f in dq if not f.passed)
    sensitive = sum(1 for c in pii if c.category is ColumnCategory.SENSITIVE)
    parts = [
        f"Dataset {dataset_id} is {status.value} with a DQ pass ratio of {pass_ratio}.",
        f"{failed} of {len(dq)} configured checks failed.",
    ]
    if freshness is not None:
        parts.append(
            f"Freshness age is {freshness.age_hours}h against a {freshness.sla_hours}h SLA."
        )
    if drift:
        parts.append(f"{len(drift)} schema-drift finding(s) were detected.")
    if sensitive:
        parts.append(f"{sensitive} sensitive-category PII column(s) require review.")
    if decertified:
        parts.append("This dataset was previously certified and is being decertified.")
    return " ".join(parts)


def to_response(
    scorecard: DatasetScorecard, *, as_of: str, tenant: str = ""
) -> CertificationResponse:
    """Project a scorecard onto the narrow certification wire H1 consumes."""
    return CertificationResponse(
        dataset_id=scorecard.subject,
        status=scorecard.status,
        certified_metrics=scorecard.certified_metrics,
        as_of=as_of,
        pass_ratio=scorecard.pass_ratio,
        tenant=tenant,
        citations=scorecard.citations[:8],
    )
