"""The deterministic data-quality rule engine (pure stdlib, frozen, fail-closed).

Evaluates a dataset's configured ``RulePack`` against its ``DatasetProfile`` and sampled values.
Every verdict is computed here; a model never decides pass or fail. The engine is fail-closed:

* an unknown rule type is refused AT LOAD by the rule-pack loader (``RulePackError``), never
  silently skipped at scoring time;
* a rule whose column is absent from the dataset is a FAILING finding (a gap in the control),
  not a skipped one, because a check that cannot run has not passed;
* a validity or referential rule with no configured expectation fails closed rather than
  vacuously passing.

Every finding cites its dataset, column and rule id and carries the sampled evidence rows an
auditor recomputes the verdict from. ``as_of`` is explicit so a run is replayable.
"""

from __future__ import annotations

import re

from .kernel import Citation, Severity
from .models import (
    ColumnSample,
    DatasetProfile,
    DQFinding,
    Rule,
    RulePack,
    RuleType,
)
from .profile_service import is_null

#: Cap the evidence rows carried on a finding: enough to recompute, not the whole column.
_MAX_EVIDENCE = 5


def _citation(rule: Rule, dataset_id: str, snippet: str) -> Citation:
    return Citation(
        source_id=f"rule:{rule.id}",
        title=f"{rule.rule_type.value} check on {dataset_id}.{rule.column}",
        snippet=snippet[:120],
    )


def _finding(
    rule: Rule,
    profile: DatasetProfile,
    *,
    passed: bool,
    observed: str,
    expected: str,
    evidence: tuple[str, ...],
) -> DQFinding:
    return DQFinding(
        dataset_id=profile.dataset_id,
        column=rule.column,
        rule_id=rule.id,
        rule_type=rule.rule_type,
        passed=passed,
        severity=rule.severity,
        observed=observed,
        expected=expected,
        evidence=evidence,
        citation=_citation(rule, profile.dataset_id, f"observed {observed}, expected {expected}"),
    )


def _non_null_values(sample: ColumnSample | None) -> list[str]:
    return [] if sample is None else [v.strip() for v in sample.values if not is_null(v)]


def _completeness(rule: Rule, profile: DatasetProfile) -> DQFinding:
    col = profile.column(rule.column)
    assert col is not None  # caller guarantees column presence
    max_null = float(rule.param("max_null_ratio", "0.0"))
    ratio = col.null_ratio
    return _finding(
        rule,
        profile,
        passed=ratio <= max_null,
        observed=f"null_ratio={ratio}",
        expected=f"<= {max_null}",
        evidence=(f"{col.null_count}/{col.sample_size} sampled values null",),
    )


def _uniqueness(rule: Rule, profile: DatasetProfile, sample: ColumnSample | None) -> DQFinding:
    col = profile.column(rule.column)
    assert col is not None
    min_ratio = float(rule.param("min_unique_ratio", "1.0"))
    ratio = col.cardinality_ratio
    values = _non_null_values(sample)
    seen: set[str] = set()
    dupes = [v for v in values if v in seen or seen.add(v)]  # type: ignore[func-returns-value]
    return _finding(
        rule,
        profile,
        passed=ratio >= min_ratio,
        observed=f"cardinality_ratio={ratio}",
        expected=f">= {min_ratio}",
        evidence=tuple(sorted(set(dupes))[:_MAX_EVIDENCE]),
    )


def _validity(rule: Rule, profile: DatasetProfile, sample: ColumnSample | None) -> DQFinding:
    values = _non_null_values(sample)
    pattern = rule.param("pattern")
    allowed = tuple(v for v in rule.param("allowed").split("|") if v)
    min_ratio = float(rule.param("min_valid_ratio", "1.0"))
    if not pattern and not allowed:
        # Fail closed: a validity rule that expresses no expectation checks nothing.
        return _finding(
            rule,
            profile,
            passed=False,
            observed="no pattern or allowed set configured",
            expected="a pattern or an allowed value set",
            evidence=(),
        )
    compiled = re.compile(pattern) if pattern else None

    def _ok(value: str) -> bool:
        if compiled is not None:
            return compiled.match(value) is not None
        return value in allowed

    invalid = [v for v in values if not _ok(v)]
    ratio = 1.0 if not values else round((len(values) - len(invalid)) / len(values), 6)
    return _finding(
        rule,
        profile,
        passed=ratio >= min_ratio,
        observed=f"valid_ratio={ratio}",
        expected=f">= {min_ratio}",
        evidence=tuple(invalid[:_MAX_EVIDENCE]),
    )


def _referential(rule: Rule, profile: DatasetProfile, sample: ColumnSample | None) -> DQFinding:
    reference = tuple(v for v in rule.param("reference").split("|") if v)
    values = _non_null_values(sample)
    if not reference:
        return _finding(
            rule,
            profile,
            passed=False,
            observed="no reference set configured",
            expected="a non-empty reference set",
            evidence=(),
        )
    orphans = [v for v in values if v not in reference]
    return _finding(
        rule,
        profile,
        passed=not orphans,
        observed=f"{len(orphans)} orphan value(s)",
        expected="every value present in the referenced set",
        evidence=tuple(sorted(set(orphans))[:_MAX_EVIDENCE]),
    )


def _timeliness(rule: Rule, profile: DatasetProfile, age_hours: float) -> DQFinding:
    max_age = float(rule.param("max_age_hours", "24"))
    return _finding(
        rule,
        profile,
        passed=age_hours <= max_age,
        observed=f"age_hours={round(age_hours, 3)}",
        expected=f"<= {max_age}",
        evidence=(f"partition loaded at {profile.metadata.partition_timestamp}",),
    )


def evaluate(
    pack: RulePack,
    profile: DatasetProfile,
    samples: dict[str, ColumnSample],
    *,
    age_hours: float,
) -> tuple[DQFinding, ...]:
    """Evaluate every rule in ``pack`` against ``profile`` and ``samples``. Fail-closed."""
    findings: list[DQFinding] = []
    for rule in pack.rules:
        sample = samples.get(rule.column)
        if rule.rule_type is not RuleType.TIMELINESS and profile.column(rule.column) is None:
            # A configured check that cannot run is a gap, and a gap fails: certifying against a
            # column that is not there would count a check the dataset never actually passed.
            findings.append(
                DQFinding(
                    dataset_id=profile.dataset_id,
                    column=rule.column,
                    rule_id=rule.id,
                    rule_type=rule.rule_type,
                    passed=False,
                    severity=rule.severity,
                    observed="column absent from dataset",
                    expected="column present",
                    evidence=(),
                    citation=_citation(rule, profile.dataset_id, "configured column is absent"),
                )
            )
            continue
        if rule.rule_type is RuleType.COMPLETENESS:
            findings.append(_completeness(rule, profile))
        elif rule.rule_type is RuleType.UNIQUENESS:
            findings.append(_uniqueness(rule, profile, sample))
        elif rule.rule_type is RuleType.VALIDITY:
            findings.append(_validity(rule, profile, sample))
        elif rule.rule_type is RuleType.REFERENTIAL_INTEGRITY:
            findings.append(_referential(rule, profile, sample))
        elif rule.rule_type is RuleType.TIMELINESS:
            findings.append(_timeliness(rule, profile, age_hours))
        else:  # pragma: no cover - RuleType is exhaustive and validated at load
            raise AssertionError(f"unhandled rule type {rule.rule_type!r}")
    return tuple(findings)


def pass_ratio(findings: tuple[DQFinding, ...]) -> float:
    """The fraction of DQ findings that passed (1.0 when there are none to run)."""
    if not findings:
        return 1.0
    return round(sum(1 for f in findings if f.passed) / len(findings), 6)


def worst_failure(findings: tuple[DQFinding, ...]) -> Severity:
    """The most severe FAILED check's severity, or ``LOW`` when nothing failed."""
    order = {Severity.CRITICAL: 3, Severity.HIGH: 2, Severity.MEDIUM: 1, Severity.LOW: 0}
    failed = [f.severity for f in findings if not f.passed]
    return max(failed, key=lambda s: order[s], default=Severity.LOW)
