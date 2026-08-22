"""Canonical synthetic fixtures, shared by the unit and contract suites.

Every dataset id names a fixture in the local warehouse and every party is obviously fictional
(``.example`` domains, RFC 5737 / RFC 3849 literals, plainly invented names). The three datasets
are engineered for a certified / uncertified / conditional arc, and a hand-built escalating
scorecard gives the contract suite one canonical R8 payload with a single home.
"""

from __future__ import annotations

from data_quality_governance.domain.kernel import Citation, Decision, Severity
from data_quality_governance.domain.models import (
    CertificationStatus,
    DatasetScorecard,
)

#: The verified principal the tests attribute work to (never a client-asserted actor).
ACTOR = "analyst@bank.example"

#: A tenant partition, so the outbound-review assertions are not all on the empty string.
TENANT = "demo-bank"

#: The seeded fixture datasets, by intended verdict.
CERTIFIED_DATASET = "customer_master"
UNCERTIFIED_DATASET = "transactions_daily"
REVIEW_DATASET = "marketing_events"

#: A planted identifier, so a redaction assertion has an independent literal to look for rather
#: than trusting the pattern pack to agree with itself.
PLANTED_NRIC = "S1234567D"


def escalating_scorecard(dataset_id: str = REVIEW_DATASET) -> DatasetScorecard:
    """A scorecard that MUST escalate (rule R8 routing applies), carrying a planted identifier.

    The citation snippet carries an NRIC so the redact-before-anything proofs have a literal to
    assert is gone from the routed payload.
    """
    return DatasetScorecard(
        subject=dataset_id,
        status=CertificationStatus.CONDITIONAL,
        decision=Decision.ESCALATED,
        severity=Severity.HIGH,
        summary=f"{dataset_id}: conditionally_certified (pass_ratio 1.0)",
        requires_human_review=True,
        pass_ratio=1.0,
        certified_metrics=("campaign", "customer_id", "event_id"),
        narrative=(
            f"Dataset {dataset_id} is conditionally_certified. A sensitive-category PII column "
            f"requires review. Contact NRIC {PLANTED_NRIC} on file."
        ),
        citations=(
            Citation(
                source_id=f"pii:{dataset_id}:health_condition",
                title="PII classification",
                snippet=f"sensitive column; sample NRIC {PLANTED_NRIC}",
            ),
        ),
    )
