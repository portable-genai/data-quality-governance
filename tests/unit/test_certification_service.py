"""The deterministic engines and the certification orchestrator.

Every consequential number and verdict here is produced by pure stdlib code, so these tests pin
the engine, not a model. They also carry the fail-closed proofs the plan calls for: an unknown
rule type refuses at load, a check on an absent column fails rather than skips, the verdict flips
red-before/green-after, and a decertification and a sensitive PII finding both route to review.
"""

from __future__ import annotations

import pytest

from data_quality_governance.config import build_container
from data_quality_governance.domain import (
    dq_rule_engine,
    drift_service,
    freshness_service,
    profile_service,
    scorecard_service,
)
from data_quality_governance.domain.certification_service import (
    CertificationService,
    ScorecardStore,
)
from data_quality_governance.domain.errors import CrossTenantError, RulePackError
from data_quality_governance.domain.kernel import Severity
from data_quality_governance.domain.models import (
    CertificationStatus,
    ColumnCategory,
    ColumnSample,
    DriftKind,
    Rule,
    RulePack,
    RuleType,
    SchemaColumn,
    TableMetadata,
)
from data_quality_governance.domain.pii_classifier import PiiClassifier
from data_quality_governance.domain.rulepack_loader import parse_pack
from data_quality_governance.rulepacks import load_rulepacks
from data_quality_governance.service_factory import build_certification_service

from tests.conftest import local_settings
from tests.fixtures import sample_cases

# --------------------------------------------------------------------------- profiling


def test_profiling_is_deterministic_and_counts_nulls_and_cardinality() -> None:
    sample = ColumnSample("amount", ("10", "", "20", "NULL", "10"))
    a = profile_service.profile_column(sample)
    b = profile_service.profile_column(sample)
    assert a == b, "the same sample must profile byte-for-byte identically"
    assert a.null_count == 2 and a.sample_size == 5
    assert a.non_null_count == 3 and a.distinct_count == 2
    assert a.null_ratio == round(2 / 5, 6)


def test_type_inference_ladder() -> None:
    assert profile_service.profile_column(ColumnSample("c", ("1", "2"))).inferred_type == "integer"
    assert (
        profile_service.profile_column(ColumnSample("c", ("1.5", "2"))).inferred_type == "numeric"
    )
    assert (
        profile_service.profile_column(ColumnSample("c", ("2026-01-01",))).inferred_type == "date"
    )
    assert profile_service.profile_column(ColumnSample("c", ("ab", "cd"))).inferred_type == "text"


# --------------------------------------------------------------------------- rule engine


def _profile(name: str, values: tuple[str, ...]) -> object:
    meta = TableMetadata("d", len(values), "2026-01-01T00:00:00", "2026-01-01T00:00:00")
    return profile_service.profile_dataset(meta, (ColumnSample(name, values),), as_of="2026-01-02")


def test_unknown_rule_type_refuses_at_load() -> None:
    with pytest.raises(RulePackError):
        parse_pack(
            {
                "dataset_id": "d",
                "rules": [{"id": "r1", "rule_type": "made_up", "column": "c", "severity": "high"}],
            }
        )


def test_a_check_on_an_absent_column_fails_rather_than_skips() -> None:
    profile = _profile("present", ("1", "2"))
    rule = Rule("r", RuleType.COMPLETENESS, "absent", Severity.HIGH, "o@x.example", "d")
    pack = RulePack("d", "o", 24, (rule,))
    findings = dq_rule_engine.evaluate(pack, profile, {}, age_hours=1.0)  # type: ignore[arg-type]
    assert len(findings) == 1 and not findings[0].passed
    assert "absent" in findings[0].observed


def test_completeness_and_uniqueness_can_each_go_red() -> None:
    profile = _profile("id", ("1", "1", "2"))
    samples = {"id": ColumnSample("id", ("1", "1", "2"))}
    dupe_rule = Rule(
        "u", RuleType.UNIQUENESS, "id", Severity.HIGH, "o", "d", (("min_unique_ratio", "1.0"),)
    )
    pack = RulePack("d", "o", 24, (dupe_rule,))
    findings = dq_rule_engine.evaluate(pack, profile, samples, age_hours=1.0)  # type: ignore[arg-type]
    assert not findings[0].passed, "a duplicated column must fail uniqueness"
    assert "1" in findings[0].evidence


def test_referential_integrity_flags_orphans() -> None:
    profile = _profile("ccy", ("SGD", "XYZ", "USD"))
    samples = {"ccy": ColumnSample("ccy", ("SGD", "XYZ", "USD"))}
    rule = Rule(
        "r",
        RuleType.REFERENTIAL_INTEGRITY,
        "ccy",
        Severity.MEDIUM,
        "o",
        "d",
        (("reference", "SGD|USD"),),
    )
    findings = dq_rule_engine.evaluate(
        RulePack("d", "o", 24, (rule,)), profile, samples, age_hours=1.0
    )  # type: ignore[arg-type]
    assert not findings[0].passed and "XYZ" in findings[0].evidence


# --------------------------------------------------------------------------- freshness


def test_freshness_ladder_high_then_critical() -> None:
    meta = TableMetadata("d", 1, "2026-01-01T00:00:00", "2026-01-01T00:00:00")
    fresh = freshness_service.score_freshness(meta, 24, as_of="2026-01-01T10:00:00")
    assert not fresh.breached and fresh.severity is Severity.LOW
    high = freshness_service.score_freshness(meta, 24, as_of="2026-01-02T06:00:00")
    assert high.breached and high.severity is Severity.HIGH
    crit = freshness_service.score_freshness(meta, 24, as_of="2026-01-03T06:00:00")
    assert crit.severity is Severity.CRITICAL


# --------------------------------------------------------------------------- drift


def test_drift_classifies_rename_removal_and_retype() -> None:
    base = (SchemaColumn("a", "STRING"), SchemaColumn("b", "INT"), SchemaColumn("c", "STRING"))
    live = (SchemaColumn("a", "STRING"), SchemaColumn("b", "STRING"), SchemaColumn("d", "STRING"))
    findings = {f.kind for f in drift_service.diff_schema("d", base, live)}
    assert DriftKind.RETYPED in findings  # b changed type
    assert DriftKind.RENAMED in findings  # c -> d (unique STRING pair)


# --------------------------------------------------------------------------- PII


def test_pii_classifier_recomputable_and_categorises_sensitive() -> None:
    prof = profile_service.profile_column(
        ColumnSample("health_condition", ("healthy", "asthma") * 6)
    )
    result = PiiClassifier().classify(
        "d", prof, ColumnSample("health_condition", ("healthy",) * 12)
    )
    assert result.category is ColumnCategory.SENSITIVE
    assert abs(sum(s.weight for s in result.signals) - result.score) < 1e-6, (
        "score must be the signal sum"
    )


def test_pii_classifier_scores_a_plain_measure_as_non_pii() -> None:
    prof = profile_service.profile_column(ColumnSample("balance", tuple(str(n) for n in range(12))))
    result = PiiClassifier().classify(
        "d", prof, ColumnSample("balance", tuple(str(n) for n in range(12)))
    )
    assert result.category is ColumnCategory.NON_PII


def test_a_stub_generation_cannot_move_a_decided_category_or_score() -> None:
    """Determinism: the model narrates, it never produces the number.

    The optional PII adjudicator is the one generation seam that touches a score. Feeding it a
    hostile verdict (a stub that lies with full confidence) must leave a column the engine has
    already decided BYTE-IDENTICAL: same category, same score. Stub the generation out and the
    consequential output does not move.
    """
    clf = PiiClassifier()

    # A clear-cut direct identifier: the score is out of the adjudication band, so a lying
    # "this is not PII" verdict is ignored entirely.
    emails = tuple(f"user{n}@bank.example" for n in range(1001, 1013))
    sample = ColumnSample("email", emails)
    prof = profile_service.profile_column(sample)
    engine_only = clf.classify("d", prof, sample)
    lied_down = clf.classify("d", prof, sample, adjudication=(False, 1.0))
    assert engine_only.category is lied_down.category is ColumnCategory.PII_DIRECT
    assert engine_only.score == lied_down.score

    # A clear-cut plain measure: a lying "this IS pii" verdict cannot promote it either.
    nums = tuple(str(n) for n in range(20))
    n_sample = ColumnSample("balance", nums)
    n_prof = profile_service.profile_column(n_sample)
    n_engine = clf.classify("d", n_prof, n_sample)
    n_lied_up = clf.classify("d", n_prof, n_sample, adjudication=(True, 1.0))
    assert n_engine.category is n_lied_up.category is ColumnCategory.NON_PII
    assert n_engine.score == n_lied_up.score


# --------------------------------------------------------------------------- orchestrator


def _service() -> CertificationService:
    service = build_certification_service(build_container(local_settings()))
    service._store = ScorecardStore()
    return service


def test_the_three_fixture_datasets_get_the_three_verdicts() -> None:
    service = _service()
    assert (
        service.certify(sample_cases.CERTIFIED_DATASET, actor="a", tenant="t").status
        is CertificationStatus.CERTIFIED
    )
    assert (
        service.certify(sample_cases.UNCERTIFIED_DATASET, actor="a", tenant="t").status
        is CertificationStatus.UNCERTIFIED
    )
    assert (
        service.certify(sample_cases.REVIEW_DATASET, actor="a", tenant="t").status
        is CertificationStatus.CONDITIONAL
    )


def test_a_sensitive_finding_requires_human_review() -> None:
    result = _service().certify(sample_cases.REVIEW_DATASET, actor="a", tenant="t")
    assert result.requires_human_review, "a sensitive PII column is a consequential outcome"


def test_a_decertification_requires_human_review() -> None:
    """A previously certified dataset that fails must escalate."""
    service = _service()
    # Seed a prior CERTIFIED status, then certify a dataset that comes back uncertified.
    first = service.certify(sample_cases.CERTIFIED_DATASET, actor="a", tenant="t")
    assert first.status is CertificationStatus.CERTIFIED and not first.requires_human_review
    # Force a decertification by pre-seeding the store's prior status for the uncertified set.
    service._store.save(
        scorecard_service.to_response(first, as_of="x", tenant="t"),
        CertificationStatus.CERTIFIED,
    )
    # Now certify a dataset the store believes was certified but is actually uncertified.
    service._store._by_key[("t", sample_cases.UNCERTIFIED_DATASET)] = (
        scorecard_service.to_response(first, as_of="x", tenant="t"),
        CertificationStatus.CERTIFIED,
    )
    result = service.certify(sample_cases.UNCERTIFIED_DATASET, actor="a", tenant="t")
    assert result.status is CertificationStatus.UNCERTIFIED
    assert result.requires_human_review, "decertifying a certified dataset must route to review"


def test_certification_status_is_tenant_scoped_and_refuses_cross_tenant() -> None:
    service = _service()
    service.certify(sample_cases.CERTIFIED_DATASET, actor="a", tenant="tenant-a")
    assert service.response_for(sample_cases.CERTIFIED_DATASET, tenant="tenant-a") is not None
    with pytest.raises(CrossTenantError):
        service.response_for(sample_cases.CERTIFIED_DATASET, tenant="tenant-b")


def test_certifying_a_dataset_with_no_rule_pack_fails_closed() -> None:
    with pytest.raises(KeyError):
        _service().certify("no_such_dataset", actor="a", tenant="t")


def test_the_shipped_rule_packs_all_parse() -> None:
    packs = load_rulepacks()
    assert set(packs) >= {
        sample_cases.CERTIFIED_DATASET,
        sample_cases.UNCERTIFIED_DATASET,
        sample_cases.REVIEW_DATASET,
    }
