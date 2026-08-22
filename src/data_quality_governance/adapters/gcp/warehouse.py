"""Managed WarehousePort: BigQuery INFORMATION_SCHEMA + bounded sampling (lazy SDK imports).

Every ``google.cloud`` import lives INSIDE a method, so this module imports cleanly with no cloud
SDK installed and the offline gate can bind the whole managed family. With nothing reachable the
lazy import is the first thing each method does, so a call refuses with ``ImportError`` rather
than pretending to have profiled a table. The real query bodies are intentionally thin: a
deployment wires the project and dataset ids and the bounded ``TABLESAMPLE`` sampling.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ColumnSample, SchemaColumn, TableMetadata


class CloudWarehouseAdapter:
    """BigQuery-backed profiling source. SDK imports are lazy (portability proof, P-02)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self) -> object:
        from google.cloud import bigquery  # lazy: offline binding must import clean

        return bigquery.Client()

    def datasets(self) -> tuple[str, ...]:
        client = self._client()
        return tuple(str(d.dataset_id) for d in client.list_datasets())  # type: ignore[attr-defined]

    def metadata(self, dataset_id: str) -> TableMetadata:
        self._client()
        raise NotImplementedError(
            "wire the INFORMATION_SCHEMA metadata query for the deployed project"
        )

    def sample_columns(self, dataset_id: str) -> tuple[ColumnSample, ...]:
        self._client()
        raise NotImplementedError("wire bounded TABLESAMPLE sampling for the deployed project")

    def live_schema(self, dataset_id: str) -> tuple[SchemaColumn, ...]:
        self._client()
        raise NotImplementedError("wire the INFORMATION_SCHEMA.COLUMNS query")
