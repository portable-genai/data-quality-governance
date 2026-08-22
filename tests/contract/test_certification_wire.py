"""Pin the certification-status wire H1 consumes, as an explicit consumption contract.

H4 hands its per-dataset certification verdict to H1 as DATA over this API (never as code: H1
never imports H4). The hand-off requires this schema to be pinned before H1's fixture-feed mirror
is built against it, so a field renamed, dropped or retyped here breaks THIS test rather than
silently breaking H1 at integration time. Every field H1 reads is asserted by name and type,
and a real serialised response is asserted to carry exactly those keys.
"""

from __future__ import annotations

from data_quality_governance.api.schemas import CertificationResponseModel
from data_quality_governance.domain.scorecard_service import certify, to_response

from tests.fixtures import sample_cases

#: The frozen field set and types H1 resolves a certified metric against. Changing this is a
#: breaking change to the cross-system contract, not a local edit.
_WIRE: dict[str, object] = {
    "dataset_id": str,
    "status": str,
    "certified_metrics": list[str],
    "as_of": str,
    "pass_ratio": float,
    "tenant": str,
}


def test_the_certification_wire_pins_exactly_the_fields_h1_consumes() -> None:
    annotations = {
        name: info.annotation for name, info in CertificationResponseModel.model_fields.items()
    }
    assert annotations == _WIRE, (
        "the certification response is H1's consumption contract; a changed field set is a "
        "breaking cross-system change and must be made deliberately, in step with H1's mirror"
    )
    fields = CertificationResponseModel.model_fields
    required = {name for name, info in fields.items() if info.is_required()}
    assert required == {"dataset_id", "status", "certified_metrics", "as_of", "pass_ratio"}


def test_a_real_serialised_response_carries_exactly_the_wire_keys() -> None:
    scorecard = sample_cases.escalating_scorecard()
    # Route the domain scorecard through the same projection the API returns.
    response = to_response(scorecard, as_of="2026-08-08T00:00:00", tenant=sample_cases.TENANT)
    body = CertificationResponseModel.from_domain(response).model_dump()
    assert set(body) == set(_WIRE)
    assert isinstance(body["certified_metrics"], list)
    assert all(isinstance(m, str) for m in body["certified_metrics"])


def test_the_pipeline_projection_matches_the_wire_for_a_certified_dataset() -> None:
    # A freshly-certified fixture scorecard projects onto the same keys, so the certify path and
    # the status path expose the identical contract H1 reads.
    scorecard = certify(
        sample_cases.CERTIFIED_DATASET,
        pass_ratio=1.0,
        dq_findings=(),
        freshness=None,
        drift=(),
        pii=(),
        tickets=(),
        lineage=None,
        as_of="2026-08-08T00:00:00",
    )
    body = CertificationResponseModel.from_domain(
        to_response(scorecard, as_of="2026-08-08T00:00:00", tenant="t")
    ).model_dump()
    assert set(body) == set(_WIRE)
