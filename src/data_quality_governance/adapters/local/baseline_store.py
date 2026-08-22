"""Local BaselineStorePort: a tenant-scoped, in-memory baseline schema store.

Seeded so drift detection has a real baseline to diff against: ``marketing_events`` carries a
baseline with a ``channel`` column the live schema renamed to ``source`` (a MEDIUM drift), while
the other datasets' baselines match their live schema (no spurious drift). The store is
tenant-scoped: a baseline is keyed on ``(tenant, dataset_id)`` and one tenant's baseline is never
returned to another, which is what lets the cross-tenant isolation test have something to prove.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import SchemaColumn

_DEMO_TENANT = "demo-bank"

_SEED: dict[tuple[str, str], tuple[SchemaColumn, ...]] = {
    (_DEMO_TENANT, "customer_master"): (
        SchemaColumn("customer_id", "INTEGER"),
        SchemaColumn("email", "STRING"),
        SchemaColumn("full_name", "STRING"),
        SchemaColumn("dob", "DATE"),
        SchemaColumn("postcode", "STRING"),
        SchemaColumn("balance", "NUMERIC"),
    ),
    (_DEMO_TENANT, "transactions_daily"): (
        SchemaColumn("txn_id", "STRING"),
        SchemaColumn("account_id", "STRING"),
        SchemaColumn("amount", "NUMERIC"),
        SchemaColumn("currency", "STRING"),
        SchemaColumn("txn_ts", "TIMESTAMP"),
    ),
    (_DEMO_TENANT, "marketing_events"): (
        SchemaColumn("event_id", "STRING"),
        SchemaColumn("customer_id", "INTEGER"),
        SchemaColumn("health_condition", "STRING"),
        SchemaColumn("campaign", "STRING"),
        SchemaColumn("event_ts", "TIMESTAMP"),
        SchemaColumn("channel", "STRING"),  # live renamed this to 'source'
    ),
}


class LocalBaselineStore:
    """A per-process, tenant-scoped baseline store seeded with the fixture baselines."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._store: dict[tuple[str, str], tuple[SchemaColumn, ...]] = dict(_SEED)

    def get_baseline(self, dataset_id: str, *, tenant: str) -> tuple[SchemaColumn, ...] | None:
        return self._store.get((tenant, dataset_id))

    def put_baseline(
        self, dataset_id: str, schema: tuple[SchemaColumn, ...], *, tenant: str
    ) -> None:
        self._store[(tenant, dataset_id)] = tuple(schema)
