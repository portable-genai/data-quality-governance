"""The certification path opens ONE span, and that span carries no content.

A trace backend is not the WORM audit trail. It has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit
store. So the value of tracing the certification path depends entirely on the span carrying
structural attributes only: which action, whose, which tenant. A dataset id, a column
sample, a finding or the narrative reaching a span has left the boundary the service's
redact call exists to hold, and it has left it silently.

The content case drives the review dataset, whose seeded warehouse sample carries
sensitive-category health values, so the check runs against input that would actually leak
if any attribute were content-shaped.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from data_quality_governance.config import Settings, build_container
from data_quality_governance.domain.certification_service import (
    CertificationService,
    ScorecardStore,
)
from data_quality_governance.domain.models import DatasetScorecard
from data_quality_governance.rulepacks import load_rulepacks

from tests.fixtures import sample_cases

#: Every attribute key the certify span is allowed to carry. A verdict that started
#: explaining itself on the span (a status, a dataset id, a finding) would widen this set,
#: which is the point of asserting on the set rather than on the individual keys.
_CERTIFY_KEYS = {"action", "actor", "tenant"}


class _RecordingTracer:
    """Captures every span name and attribute so the test can inspect what was emitted."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str) -> Iterator[None]:
        self.spans.append((name, dict(attributes)))
        yield

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


def _certify(dataset_id: str) -> tuple[_RecordingTracer, DatasetScorecard]:
    """The REAL local adapters, exactly as ``service_factory`` wires them, tracer swapped."""
    tracer = _RecordingTracer()
    container = build_container(Settings(profile="local", audit_path=":memory:"))
    service = CertificationService(
        warehouse=container.warehouse,
        catalog=container.catalog,
        baseline_store=container.baseline_store,
        audit=container.audit,
        tracer=tracer,  # type: ignore[arg-type]
        rulepacks=load_rulepacks(),
        store=ScorecardStore(),
    )
    scorecard = service.certify(dataset_id, actor=sample_cases.ACTOR, tenant=sample_cases.TENANT)
    return tracer, scorecard


def _emitted(tracer: _RecordingTracer) -> str:
    """Every attribute KEY and VALUE that was emitted, as one searchable blob."""
    parts: list[str] = []
    for name, attributes in tracer.spans:
        parts.append(name)
        parts.extend(attributes)
        parts.extend(attributes.values())
    return " ".join(parts)


def test_certifying_a_dataset_opens_exactly_one_named_span() -> None:
    tracer, _ = _certify(sample_cases.CERTIFIED_DATASET)
    assert [name for name, _ in tracer.spans] == ["dq_governance.certify"]


def test_the_span_carries_the_structural_attributes_an_operator_needs() -> None:
    """Enough to answer "whose certification is slow, in which tenant", and nothing more."""
    tracer, _ = _certify(sample_cases.CERTIFIED_DATASET)
    _, attributes = tracer.spans[0]
    assert attributes["action"] == "certify"
    assert attributes["actor"] == sample_cases.ACTOR
    assert attributes["tenant"] == sample_cases.TENANT


@pytest.mark.parametrize(
    "dataset_id",
    [
        sample_cases.CERTIFIED_DATASET,
        sample_cases.UNCERTIFIED_DATASET,
        sample_cases.REVIEW_DATASET,
    ],
    ids=["certified", "uncertified", "review"],
)
def test_the_attribute_set_is_a_fixed_allowlist_whatever_the_verdict(dataset_id: str) -> None:
    """A failing dataset must not start attaching its findings, or its id, to the span."""
    tracer, _ = _certify(dataset_id)
    for _, attributes in tracer.spans:
        assert set(attributes) == _CERTIFY_KEYS, (
            "a new span attribute appeared; confirm it is structural, then widen "
            "_CERTIFY_KEYS here deliberately"
        )


def test_no_span_attribute_carries_dataset_content_or_a_sensitive_sample() -> None:
    """The review dataset's seeded sample carries health values, so a leak would show."""
    tracer, scorecard = _certify(sample_cases.REVIEW_DATASET)
    emitted = _emitted(tracer).lower()
    forbidden = [
        sample_cases.REVIEW_DATASET,
        scorecard.summary,
        scorecard.narrative,
        "diabetes",
        *(c.snippet for c in scorecard.citations),
    ]
    for literal in forbidden:
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal.lower() not in emitted, f"a span attribute carried {literal!r}"


def test_every_emitted_attribute_value_is_a_string_the_port_declares() -> None:
    """``span(name, **attributes: str)``: a non-string would serialise however the SDK felt."""
    tracer, _ = _certify(sample_cases.UNCERTIFIED_DATASET)
    values = [v for _, attributes in tracer.spans for v in attributes.values()]
    assert values
    assert all(isinstance(value, str) for value in values)
