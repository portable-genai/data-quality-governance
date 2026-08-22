"""Local CatalogPort: a fixture data catalog (ownership, tags, lineage edges).

Obviously fictional. Mirrors the shape a Dataplex read would return, so the remediation and
lineage-impact logic can run with no cloud catalog. Every owner is a role address at an
``.example`` domain and every downstream edge names another fixture dataset.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...config import Settings

_OWNERS: dict[str, str] = {
    "customer_master": "cdo-office@bank.example",
    "transactions_daily": "payments-data-owner@bank.example",
    "marketing_events": "marketing-data-owner@bank.example",
}

_DOWNSTREAM: dict[str, tuple[str, ...]] = {
    "customer_master": ("transactions_daily", "marketing_events", "analytics.customer_360"),
    "transactions_daily": ("analytics.revenue_daily",),
    "marketing_events": ("analytics.campaign_roi",),
}

_TAGS: dict[str, tuple[str, ...]] = {
    "customer_master": ("tenant:demo-bank", "domain:customer", "pii:high"),
    "transactions_daily": ("tenant:demo-bank", "domain:payments"),
    "marketing_events": ("tenant:demo-bank", "domain:marketing", "pii:sensitive"),
}


@dataclass(frozen=True, slots=True)
class LocalCatalogAdapter:
    """The SDK-free fixture catalog used by the gate, the demo and the eval."""

    settings: Settings

    def owner(self, dataset_id: str) -> str:
        return _OWNERS.get(dataset_id, "unknown-owner@bank.example")

    def tags(self, dataset_id: str) -> tuple[str, ...]:
        return _TAGS.get(dataset_id, ())

    def downstream(self, dataset_id: str) -> tuple[str, ...]:
        return _DOWNSTREAM.get(dataset_id, ())
