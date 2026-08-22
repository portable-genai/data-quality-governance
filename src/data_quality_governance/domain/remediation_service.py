"""Deterministic remediation-ticket assembly and lineage impact (pure stdlib).

A ticket is assembled from a failed check, never drafted by a model: dataset, failed rule,
column, severity, owner and the recommended action. The lineage-impact list is the downstream
datasets a certification change touches, taken from the catalog's edges (supplied by the caller
from ``CatalogPort``, so this module stays pure).
"""

from __future__ import annotations

from .kernel import Citation, Severity
from .models import (
    ColumnCategory,
    DQFinding,
    DriftFinding,
    DriftKind,
    LineageImpact,
    PiiClassification,
    RemediationTicket,
)

_DRIFT_ACTION = {
    DriftKind.REMOVED: "restore the removed column or update every downstream contract",
    DriftKind.RETYPED: "reconcile the type change with downstream readers before promotion",
    DriftKind.RENAMED: "alias the renamed column or migrate downstream queries",
    DriftKind.ADDED: "document the new column and extend the rule pack to cover it",
}


def _ticket(
    dataset_id: str,
    rule_id: str,
    column: str,
    severity: Severity,
    owner: str,
    action: str,
    citation: Citation,
) -> RemediationTicket:
    return RemediationTicket(
        dataset_id=dataset_id,
        rule_id=rule_id,
        column=column,
        severity=severity,
        owner=owner,
        action=action,
        citation=citation,
    )


def build_tickets(
    dataset_id: str,
    owner: str,
    dq_findings: tuple[DQFinding, ...],
    drift: tuple[DriftFinding, ...],
    pii: tuple[PiiClassification, ...],
) -> tuple[RemediationTicket, ...]:
    """Assemble one ticket per failed DQ check, per drift finding, and per sensitive PII column."""
    tickets: list[RemediationTicket] = []
    for f in dq_findings:
        if not f.passed:
            action = (
                f"fix {f.rule_type.value} on {f.column}: "
                f"observed {f.observed}, expected {f.expected}"
            )
            tickets.append(
                _ticket(dataset_id, f.rule_id, f.column, f.severity, owner, action, f.citation)
            )
    for d in drift:
        tickets.append(
            _ticket(
                dataset_id,
                f"drift:{d.kind.value}",
                d.column,
                d.severity,
                owner,
                _DRIFT_ACTION[d.kind],
                d.citation,
            )
        )
    for c in pii:
        if c.category is ColumnCategory.SENSITIVE or (
            c.category is ColumnCategory.PII_DIRECT and c.needs_review
        ):
            tickets.append(
                _ticket(
                    dataset_id,
                    f"pii:{c.column}",
                    c.column,
                    Severity.HIGH,
                    owner,
                    c.recommended_action,
                    c.citation,
                )
            )
    return tuple(tickets)


def lineage_impact(dataset_id: str, downstream: tuple[str, ...]) -> LineageImpact:
    """The downstream datasets touched if this dataset's certification changes."""
    return LineageImpact(dataset_id=dataset_id, downstream=tuple(downstream))
