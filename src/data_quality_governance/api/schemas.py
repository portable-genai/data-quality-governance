"""API request/response schemas (Pydantic) mapped to/from the pure-domain models.

The request carries a dataset id only: the client never asserts the verdict, the metrics or the
actor. The response projects a ``DatasetScorecard``; ``CertificationResponseModel`` is the narrow
wire H1 (and any downstream) consumes, pinned by the API contract test.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..domain.models import CertificationResponse, DatasetScorecard


class CertifyRequest(BaseModel):
    dataset_id: str


class CitationModel(BaseModel):
    source_id: str
    title: str
    snippet: str = ""


class DQFindingModel(BaseModel):
    column: str
    rule_id: str
    rule_type: str
    passed: bool
    severity: str
    observed: str
    expected: str
    evidence: list[str] = []


class DriftModel(BaseModel):
    kind: str
    column: str
    from_type: str
    to_type: str
    severity: str


class PiiModel(BaseModel):
    column: str
    category: str
    score: float
    entity_type: str
    needs_review: bool
    recommended_action: str
    signals: list[dict[str, object]] = []


class TicketModel(BaseModel):
    rule_id: str
    column: str
    severity: str
    owner: str
    action: str


class ScorecardResponse(BaseModel):
    dataset_id: str
    status: str
    decision: str
    severity: str
    summary: str
    narrative: str
    requires_human_review: bool
    pass_ratio: float
    certified_metrics: list[str] = []
    #: Where the escalation WENT (rule R8): the Hrz7 review id, or the local queue reference.
    #: Empty only when the scorecard did not escalate.
    review_ref: str = ""
    dq_findings: list[DQFindingModel] = []
    drift: list[DriftModel] = []
    pii: list[PiiModel] = []
    tickets: list[TicketModel] = []
    lineage_downstream: list[str] = []
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(cls, s: DatasetScorecard, *, review_ref: str = "") -> ScorecardResponse:
        return cls(
            dataset_id=s.subject,
            status=s.status.value,
            decision=s.decision.value,
            severity=s.severity.value,
            summary=s.summary,
            narrative=s.narrative,
            requires_human_review=s.requires_human_review,
            pass_ratio=s.pass_ratio,
            certified_metrics=list(s.certified_metrics),
            review_ref=review_ref,
            dq_findings=[
                DQFindingModel(
                    column=f.column,
                    rule_id=f.rule_id,
                    rule_type=f.rule_type.value,
                    passed=f.passed,
                    severity=f.severity.value,
                    observed=f.observed,
                    expected=f.expected,
                    evidence=list(f.evidence),
                )
                for f in s.dq_findings
            ],
            drift=[
                DriftModel(
                    kind=d.kind.value,
                    column=d.column,
                    from_type=d.from_type,
                    to_type=d.to_type,
                    severity=d.severity.value,
                )
                for d in s.drift
            ],
            pii=[
                PiiModel(
                    column=c.column,
                    category=c.category.value,
                    score=c.score,
                    entity_type=c.entity_type,
                    needs_review=c.needs_review,
                    recommended_action=c.recommended_action,
                    signals=[
                        {"code": sig.code, "weight": sig.weight, "detail": sig.detail}
                        for sig in c.signals
                    ],
                )
                for c in s.pii
            ],
            tickets=[
                TicketModel(
                    rule_id=t.rule_id,
                    column=t.column,
                    severity=t.severity.value,
                    owner=t.owner,
                    action=t.action,
                )
                for t in s.tickets
            ],
            lineage_downstream=list(s.lineage.downstream) if s.lineage else [],
            citations=[
                CitationModel(source_id=c.source_id, title=c.title, snippet=c.snippet)
                for c in s.citations
            ],
        )


class CertificationResponseModel(BaseModel):
    """The narrow certification-status wire H1 consumes (dataset + status + certified metrics)."""

    dataset_id: str
    status: str
    certified_metrics: list[str]
    as_of: str
    pass_ratio: float
    tenant: str = ""

    @classmethod
    def from_domain(cls, r: CertificationResponse) -> CertificationResponseModel:
        return cls(
            dataset_id=r.dataset_id,
            status=r.status.value,
            certified_metrics=list(r.certified_metrics),
            as_of=r.as_of,
            pass_ratio=r.pass_ratio,
            tenant=r.tenant,
        )


class HealthResponse(BaseModel):
    status: str
    profile: str
    region: str
    #: Provenance the UI banner states on every page: where the runtime sits and which model
    #: answers. Both are read off the service because the browser cannot know either.
    runtime: str = "local"  # "gcp" | "local"
    generator_model: str = "deterministic-offline-stub"
