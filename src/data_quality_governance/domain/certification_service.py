"""The certification orchestrator: pull from the ports, run the engines, fold one scorecard.

The consequential outcome (the certification verdict, every number on the scorecard) is produced
by the pure engines in this package; this service only sequences them and writes an
already-redacted audit record. A model produces nothing here. The ports are injected, so the
orchestrator itself does no I/O beyond what a port performs and stays unit-testable with fakes.

A tenant-scoped :class:`ScorecardStore` holds the last verdict per ``(tenant, dataset)``. It
serves two jobs: detecting a DECERTIFICATION (a previously certified dataset that is no longer
certified is a consequential outcome routed to human review, rule R8), and answering the
certification-status API H1 consumes, authorising every read against the caller's tenant so one
tenant can never read another's scorecard (403, never 404-that-leaks-existence).
"""

from __future__ import annotations

from ..ports.observability import ObservabilityTracerPort
from .errors import CrossTenantError
from .kernel import AuditEvent, utcnow
from .models import (
    CertificationResponse,
    CertificationStatus,
    ColumnSample,
    DatasetScorecard,
    RulePack,
)
from .pii import PII_PATTERNS
from .pii_classifier import PiiClassifier

_TS_FMT = "%Y-%m-%dT%H:%M:%S"

#: One span per certified dataset. Structural attributes only: see
#: :meth:`CertificationService.certify`.
_CERTIFY_SPAN = "dq_governance.certify"


class ScorecardStore:
    """A tenant-scoped store of the last certification per dataset (in-memory, per process)."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], tuple[CertificationResponse, CertificationStatus]] = {}

    def prior_status(self, dataset_id: str, tenant: str) -> CertificationStatus | None:
        entry = self._by_key.get((tenant, dataset_id))
        return None if entry is None else entry[1]

    def save(self, response: CertificationResponse, status: CertificationStatus) -> None:
        self._by_key[(response.tenant, response.dataset_id)] = (response, status)

    def get(self, dataset_id: str, *, tenant: str) -> CertificationResponse | None:
        """Return the caller-tenant's scorecard, or refuse cross-tenant, or None if absent.

        A scorecard that exists under a DIFFERENT tenant raises :class:`CrossTenantError`: the
        API turns that into 403. Returning 404 there would leak whether the dataset exists at all
        to a tenant with no right to know.
        """
        entry = self._by_key.get((tenant, dataset_id))
        if entry is not None:
            return entry[0]
        if any(ds == dataset_id and tn != tenant for (tn, ds) in self._by_key):
            raise CrossTenantError(
                f"dataset {dataset_id!r} is not certified under tenant {tenant!r}"
            )
        return None


#: One process-wide store, so decertification detection and the status API see the same history
#: across requests regardless of how many service instances a surface builds.
STORE = ScorecardStore()


class CertificationService:
    """Orchestrate a full dataset certification from the injected ports and engines."""

    def __init__(
        self,
        *,
        warehouse: object,
        catalog: object,
        baseline_store: object,
        audit: object,
        tracer: ObservabilityTracerPort,
        rulepacks: dict[str, RulePack],
        pii_classifier: PiiClassifier | None = None,
        store: ScorecardStore | None = None,
    ) -> None:
        self._warehouse = warehouse
        self._catalog = catalog
        self._baseline_store = baseline_store
        self._audit = audit
        self._tracer = tracer
        self._rulepacks = rulepacks
        self._pii = pii_classifier or PiiClassifier()
        self._store = store or STORE

    def certify(self, dataset_id: str, *, actor: str, tenant: str = "") -> DatasetScorecard:
        """Profile, check, score and certify one dataset, writing a redacted audit record.

        The whole path runs inside one span. Its attributes are STRUCTURAL only, never the
        dataset id, a column sample, a finding or the narrative: a trace backend is not the
        WORM audit trail; it has no redaction stage, a wider read audience and no retention
        rule written against a regulator's requirement, so anything content-shaped that
        reaches a span has left the boundary the redact call in ``_write_audit`` exists to
        hold, and left it silently.
        """
        with self._tracer.span(_CERTIFY_SPAN, action="certify", actor=actor, tenant=tenant):
            return self._certify(dataset_id, actor=actor, tenant=tenant)

    def _certify(self, dataset_id: str, *, actor: str, tenant: str = "") -> DatasetScorecard:
        from . import dq_rule_engine as dq
        from . import drift_service, freshness_service, profile_service, remediation_service
        from . import scorecard_service as sc

        pack = self._rulepacks.get(dataset_id)
        if pack is None:
            # Fail closed: certifying a dataset with no configured checks would certify against
            # nothing. An unconfigured dataset is not a passing one.
            raise KeyError(
                f"no rule pack configured for dataset {dataset_id!r}; add "
                f"config/rulepacks/{dataset_id}.yaml"
            )

        as_of = utcnow().strftime(_TS_FMT)
        metadata = self._warehouse.metadata(dataset_id)  # type: ignore[attr-defined]
        samples = self._warehouse.sample_columns(dataset_id)  # type: ignore[attr-defined]
        sample_by_name: dict[str, ColumnSample] = {s.name: s for s in samples}

        profile = profile_service.profile_dataset(metadata, samples, as_of=as_of)
        age = freshness_service.age_hours(metadata.partition_timestamp, as_of)
        dq_findings = dq.evaluate(pack, profile, sample_by_name, age_hours=age)
        ratio = dq.pass_ratio(dq_findings)
        freshness = freshness_service.score_freshness(metadata, pack.sla_hours, as_of=as_of)

        baseline = self._baseline_store.get_baseline(dataset_id, tenant=tenant)  # type: ignore[attr-defined]
        live = self._warehouse.live_schema(dataset_id)  # type: ignore[attr-defined]
        drift = drift_service.diff_schema(dataset_id, baseline, live) if baseline else ()

        pii = tuple(
            self._pii.classify(dataset_id, col, sample_by_name[col.name])
            for col in profile.columns
            if col.name in sample_by_name
        )

        owner = self._catalog.owner(dataset_id)  # type: ignore[attr-defined]
        downstream = self._catalog.downstream(dataset_id)  # type: ignore[attr-defined]
        tickets = remediation_service.build_tickets(dataset_id, owner, dq_findings, drift, pii)
        lineage = remediation_service.lineage_impact(dataset_id, downstream)

        prior = self._store.prior_status(dataset_id, tenant)
        scorecard = sc.certify(
            dataset_id,
            pass_ratio=ratio,
            dq_findings=dq_findings,
            freshness=freshness,
            drift=drift,
            pii=pii,
            tickets=tickets,
            lineage=lineage,
            as_of=as_of,
            prior_status=prior,
        )

        self._write_audit(scorecard, actor=actor)
        response = sc.to_response(scorecard, as_of=as_of, tenant=tenant)
        self._store.save(response, scorecard.status)
        return scorecard

    def response_for(self, dataset_id: str, *, tenant: str) -> CertificationResponse | None:
        """The stored certification H1 reads, authorised against the caller's tenant."""
        return self._store.get(dataset_id, tenant=tenant)

    def _write_audit(self, scorecard: DatasetScorecard, *, actor: str) -> None:
        from pii_kit import redact

        self._audit.record(  # type: ignore[attr-defined]
            AuditEvent(
                action="certify",
                actor=actor,
                decision=scorecard.decision,
                severity=scorecard.severity,
                redacted_summary=redact(
                    f"{scorecard.summary} :: {scorecard.narrative}", PII_PATTERNS
                ),
                citations=scorecard.citations[:8],
                timestamp=utcnow(),
            )
        )
