"""WarehousePort: the boundary to the analytical store being profiled.

The engine reasons over metadata, bounded column samples and the live schema; it never issues a
query. The ``local`` family is a seeded fictional warehouse with planted defects (nulls,
duplicates, a stale partition, drifted schema, PII columns); the ``gcp`` family reads BigQuery
``INFORMATION_SCHEMA`` plus bounded sampling with lazy SDK imports; the ``onprem`` family is a
fail-fast placeholder for the client's own store.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import ColumnSample, SchemaColumn, TableMetadata


@runtime_checkable
class WarehousePort(Protocol):
    def datasets(self) -> tuple[str, ...]:
        """The dataset ids this warehouse exposes for profiling."""
        ...

    def metadata(self, dataset_id: str) -> TableMetadata:
        """Row count, load and partition timestamps, and the live schema for a dataset."""
        ...

    def sample_columns(self, dataset_id: str) -> tuple[ColumnSample, ...]:
        """A bounded, deterministic sample of each column's values, as text."""
        ...

    def live_schema(self, dataset_id: str) -> tuple[SchemaColumn, ...]:
        """The dataset's current schema (name and type per column)."""
        ...
