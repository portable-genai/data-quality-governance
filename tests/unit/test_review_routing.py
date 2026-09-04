"""Rule R8: an escalated scorecard is ROUTED to human-review-console, not left in a per-repo
boolean.

This is the standing gate for the failure the rule exists to prevent. A repo can set
``requires_human_review = True``, pass every other test, and still auto-execute in practice
because nothing ever reads the flag. So the assertions here are about the ROUTING, not the flag:
a consequential scorecard produces an outbound review, a clean one produces none, the payload
leaves redacted, and the on-prem placeholder refuses rather than swallowing the escalation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from data_quality_governance.adapters.gcp.review_router import (
    CloudReviewRouter,
)
from data_quality_governance.adapters.local.review_router import (
    LocalReviewRouter,
)
from data_quality_governance.adapters.onprem.review_router import (
    OnPremReviewRouter,
)
from data_quality_governance.api.app import (
    app,
)
from data_quality_governance.config import (
    Settings,
    build_container,
)
from data_quality_governance.domain.kernel import Severity
from data_quality_governance.domain.models import DatasetScorecard
from data_quality_governance.service_factory import (
    build_certification_service,
)

from tests.fixtures import sample_cases


def _settings(profile: str = "local") -> Settings:
    return Settings(profile=profile, audit_path=":memory:", tenant="demo-bank")


def _scorecard(dataset_id: str) -> DatasetScorecard:
    service = build_certification_service(build_container(_settings()))
    return service.certify(dataset_id, actor=sample_cases.ACTOR, tenant=sample_cases.TENANT)


def test_a_sensitive_finding_produces_an_outbound_review() -> None:
    router = LocalReviewRouter(_settings())
    result = _scorecard(sample_cases.REVIEW_DATASET)
    assert result.requires_human_review, "a sensitive-category PII finding must escalate"
    ref = router.route(result, maker=sample_cases.ACTOR)
    assert ref, "routing must return a reference, so the caller can record where it went"
    pending = router.outbox.pending()
    assert len(pending) == 1
    review = pending[0].review
    assert review.maker == sample_cases.ACTOR
    assert review.tenant == "demo-bank"
    assert review.source_key, "a durable outbox needs an idempotency key"


def test_a_critical_scorecard_demands_dual_control() -> None:
    router = LocalReviewRouter(_settings())
    result = _scorecard(sample_cases.UNCERTIFIED_DATASET)
    assert result.severity is Severity.CRITICAL, "a stale-past-2x-SLA dataset is CRITICAL"
    router.route(result, maker=sample_cases.ACTOR)
    assert router.outbox.pending()[0].review.required_approvals == 2


def test_the_payload_is_redacted_before_it_leaves_the_process() -> None:
    """human-review-console is a shared sink; a raw identifier must never reach the wire."""
    router = LocalReviewRouter(_settings())
    router.route(sample_cases.escalating_scorecard(), maker=sample_cases.ACTOR)
    review = router.outbox.pending()[0].review
    wire = repr(review.to_payload())
    assert sample_cases.PLANTED_NRIC not in wire
    assert "REDACTED" in wire


def test_the_managed_router_refuses_when_no_console_is_configured() -> None:
    """An escalation with nowhere to go must fail loudly, not return as if it were reviewed."""
    router = CloudReviewRouter(Settings(profile="gcp", audit_path=":memory:", review_url=""))
    with pytest.raises(RuntimeError, match="R8"):
        router.route(sample_cases.escalating_scorecard(), maker=sample_cases.ACTOR)


def test_the_onprem_placeholder_refuses_rather_than_dropping_the_escalation() -> None:
    router = OnPremReviewRouter(_settings("onprem"))
    with pytest.raises(NotImplementedError, match="R8"):
        router.route(sample_cases.escalating_scorecard(), maker=sample_cases.ACTOR)


def test_the_api_routes_the_escalation_in_the_same_request() -> None:
    """The serving path, not just the adapter: an escalation must not depend on a later job."""
    client = TestClient(app, client=("127.0.0.1", 50000))
    escalated = client.post(
        "/v1/certify",
        json={"dataset_id": sample_cases.REVIEW_DATASET},
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assert escalated["requires_human_review"] is True
    assert escalated["review_ref"], "an escalation with no routing reference went nowhere"

    routine = client.post(
        "/v1/certify",
        json={"dataset_id": sample_cases.CERTIFIED_DATASET},
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assert routine["requires_human_review"] is False
    assert routine["review_ref"] == "", "a certified dataset must not manufacture a review"
