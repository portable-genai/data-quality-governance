"""Vertical artifact models: the data-quality and governance types this service reasons over.

The artifacts THIS vertical produces, as opposed to the vertical-neutral machinery in
``kernel.py`` (``Severity``, ``Decision``, ``Citation``, ``AuditEvent``). A fork building a
different vertical rewrites this module and keeps ``kernel.py`` untouched.

Everything here is a frozen, slotted dataclass or a ``LenientStrEnum`` (a member IS its wire
value), pure standard library plus the commons enums. No number on any of these types is ever
produced by a model: the engines in this package compute them and a narrator only describes
them. ``DatasetScorecard`` is the aggregate the API returns and the object rule R8 routes to
human review, so it carries the review-compatible surface (``subject`` / ``severity`` /
``decision`` / ``summary`` / ``requires_human_review`` / ``citations``) alongside the rich,
per-check evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hex_service_kit.enums import LenientStrEnum

from .kernel import Citation, Decision, Severity


class CertificationStatus(LenientStrEnum):
    """The per-dataset verdict H1 (and any downstream consumer) reads over the wire."""

    CERTIFIED = "certified"
    CONDITIONAL = "conditionally_certified"
    UNCERTIFIED = "uncertified"


class ColumnCategory(LenientStrEnum):
    """The PII classification an auditor can recompute from the signal breakdown."""

    PII_DIRECT = "pii_direct"
    PII_QUASI = "pii_quasi"
    SENSITIVE = "sensitive"
    NON_PII = "non_pii"


class RuleType(LenientStrEnum):
    """The data-quality check families a rule pack may declare. Fail-closed at load."""

    COMPLETENESS = "completeness"
    UNIQUENESS = "uniqueness"
    VALIDITY = "validity"
    REFERENTIAL_INTEGRITY = "referential_integrity"
    TIMELINESS = "timeliness"


class DriftKind(LenientStrEnum):
    """How a live column differs from its declared baseline, on a severity ladder."""

    ADDED = "added"
    REMOVED = "removed"
    RETYPED = "retyped"
    RENAMED = "renamed"


#: The direct-identifier entity kinds a strong pattern match implies a PII_DIRECT column.
DIRECT_ENTITIES: frozenset[str] = frozenset(
    {"EMAIL_ADDRESS", "PHONE_NUMBER", "SG_NRIC_FIN", "HK_HKID", "JP_MY_NUMBER", "AU_TFN"}
)


# --------------------------------------------------------------------------- warehouse inputs
@dataclass(frozen=True, slots=True)
class ColumnSample:
    """A bounded sample of one column's values, as text (the warehouse port's output)."""

    name: str
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SchemaColumn:
    """One column of a live or baseline schema: a name and a declared type."""

    name: str
    data_type: str


@dataclass(frozen=True, slots=True)
class TableMetadata:
    """Dataset-level metadata the warehouse reports, independent of the column samples."""

    dataset_id: str
    row_count: int
    load_timestamp: str
    partition_timestamp: str
    schema: tuple[SchemaColumn, ...] = ()


# --------------------------------------------------------------------------- profiling output
@dataclass(frozen=True, slots=True)
class ColumnProfile:
    """Deterministic per-column statistics computed by ``profile_service`` (pure stdlib).

    Ratios are derived properties rather than stored fields so a profile cannot carry a
    null-ratio that disagrees with its own counts.
    """

    name: str
    inferred_type: str
    sample_size: int
    non_null_count: int
    null_count: int
    distinct_count: int
    min_length: int
    max_length: int

    @property
    def null_ratio(self) -> float:
        return 0.0 if self.sample_size == 0 else round(self.null_count / self.sample_size, 6)

    @property
    def cardinality_ratio(self) -> float:
        base = self.non_null_count
        return 0.0 if base == 0 else round(self.distinct_count / base, 6)


@dataclass(frozen=True, slots=True)
class DatasetProfile:
    """A dataset's metadata plus one ``ColumnProfile`` per column, at a fixed ``as_of``."""

    dataset_id: str
    metadata: TableMetadata
    columns: tuple[ColumnProfile, ...]
    as_of: str

    def column(self, name: str) -> ColumnProfile | None:
        return next((c for c in self.columns if c.name == name), None)


# --------------------------------------------------------------------------- rule packs (data)
@dataclass(frozen=True, slots=True)
class Rule:
    """One configured data-quality check. Loaded from YAML, never hand-coded in the engine."""

    id: str
    rule_type: RuleType
    column: str
    severity: Severity
    owner: str
    description: str
    params: tuple[tuple[str, str], ...] = ()

    def param(self, key: str, default: str = "") -> str:
        return next((v for k, v in self.params if k == key), default)


@dataclass(frozen=True, slots=True)
class RulePack:
    """The rules configured for one dataset, plus its declared freshness SLA and owner."""

    dataset_id: str
    owner: str
    sla_hours: int
    rules: tuple[Rule, ...]


# --------------------------------------------------------------------------- findings
@dataclass(frozen=True, slots=True)
class DQFinding:
    """One rule's verdict on one column, with the sampled evidence an auditor recomputes from."""

    dataset_id: str
    column: str
    rule_id: str
    rule_type: RuleType
    passed: bool
    severity: Severity
    observed: str
    expected: str
    evidence: tuple[str, ...]
    citation: Citation


@dataclass(frozen=True, slots=True)
class FreshnessResult:
    """Recency of a dataset scored against its declared SLA, at a caller-supplied ``as_of``."""

    dataset_id: str
    sla_hours: int
    age_hours: float
    breached: bool
    severity: Severity
    citation: Citation


@dataclass(frozen=True, slots=True)
class DriftFinding:
    """One schema difference between the live schema and the stored baseline."""

    dataset_id: str
    kind: DriftKind
    column: str
    from_type: str
    to_type: str
    severity: Severity
    citation: Citation


@dataclass(frozen=True, slots=True)
class PiiSignal:
    """One explainable contribution to a column's PII score (name / pattern / shape)."""

    code: str
    weight: float
    detail: str


@dataclass(frozen=True, slots=True)
class PiiClassification:
    """A column's PII category and the arithmetic that produced it (recomputable)."""

    dataset_id: str
    column: str
    category: ColumnCategory
    score: float
    signals: tuple[PiiSignal, ...]
    entity_type: str
    needs_review: bool
    recommended_action: str
    citation: Citation


# --------------------------------------------------------------------------- remediation
@dataclass(frozen=True, slots=True)
class RemediationTicket:
    """A deterministically assembled remediation item for one failed check."""

    dataset_id: str
    rule_id: str
    column: str
    severity: Severity
    owner: str
    action: str
    citation: Citation


@dataclass(frozen=True, slots=True)
class LineageImpact:
    """The downstream datasets touched if this dataset's certification changes."""

    dataset_id: str
    downstream: tuple[str, ...]


# --------------------------------------------------------------------------- the aggregate
@dataclass(frozen=True, slots=True)
class DatasetScorecard:
    """The cited certification scorecard: the API's return and rule R8's routed payload.

    The review-compatible surface (``subject`` == dataset id, ``severity``, ``decision``,
    ``summary``, ``requires_human_review``, ``citations``) lets the shared review-kit converter
    and the audit sink consume a scorecard exactly as they consumed the template's result, while
    the per-check fields carry the evidence a reviewer and the panel render.
    """

    subject: str
    status: CertificationStatus
    decision: Decision
    severity: Severity
    summary: str
    requires_human_review: bool
    pass_ratio: float
    dq_findings: tuple[DQFinding, ...] = ()
    freshness: FreshnessResult | None = None
    drift: tuple[DriftFinding, ...] = ()
    pii: tuple[PiiClassification, ...] = ()
    tickets: tuple[RemediationTicket, ...] = ()
    lineage: LineageImpact | None = None
    certified_metrics: tuple[str, ...] = ()
    narrative: str = ""
    citations: tuple[Citation, ...] = ()

    @property
    def dataset_id(self) -> str:
        return self.subject


@dataclass(frozen=True, slots=True)
class CertificationResponse:
    """The narrow wire contract H1 (and any downstream) consumes: status + certified metrics.

    Pinned by an API contract test. H1's ``local`` certification adapter is a fixture feed that
    mirrors THIS schema, so H1's offline gate never needs a running H4. Keep it minimal and
    additive: a downstream reads ``status`` and ``certified_metrics`` and nothing structural
    beyond them.
    """

    dataset_id: str
    status: CertificationStatus
    certified_metrics: tuple[str, ...]
    as_of: str
    pass_ratio: float
    tenant: str = ""
    citations: tuple[Citation, ...] = field(default_factory=tuple)
