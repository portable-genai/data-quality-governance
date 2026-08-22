"""BaselineStorePort: the tenant-scoped store of the last approved schema per dataset.

Drift detection diffs the live schema against the baseline this port returns. The baseline is
tenant-scoped: a lookup names its tenant, and a store must never return one tenant's baseline to
another. The ``local`` family is an in-memory JSON-backed fixture store, ``gcp`` a managed store
with lazy imports, ``onprem`` a fail-fast placeholder.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import SchemaColumn


@runtime_checkable
class BaselineStorePort(Protocol):
    def get_baseline(self, dataset_id: str, *, tenant: str) -> tuple[SchemaColumn, ...] | None:
        """The stored baseline schema for a dataset in a tenant, or ``None`` if unset."""
        ...

    def put_baseline(
        self, dataset_id: str, schema: tuple[SchemaColumn, ...], *, tenant: str
    ) -> None:
        """Record ``schema`` as the approved baseline for a dataset in a tenant."""
        ...
