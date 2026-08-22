"""Managed CatalogPort: Dataplex ownership, tags and lineage (lazy SDK imports).

The ``google.cloud`` import is inside the methods, so this module imports with no cloud SDK and
the offline gate binds it; a call with nothing reachable refuses with ``ImportError``.
"""

from __future__ import annotations

from ...config import Settings


class CloudCatalogAdapter:
    """Dataplex-backed catalog. SDK imports are lazy (portability proof, P-02)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self) -> object:
        from google.cloud import dataplex_v1  # lazy: offline binding must import clean

        return dataplex_v1.CatalogServiceClient()

    def owner(self, dataset_id: str) -> str:
        self._client()
        raise NotImplementedError("wire the Dataplex entry lookup for ownership")

    def tags(self, dataset_id: str) -> tuple[str, ...]:
        self._client()
        raise NotImplementedError("wire the Dataplex aspect/tag lookup")

    def downstream(self, dataset_id: str) -> tuple[str, ...]:
        self._client()
        raise NotImplementedError("wire the Data Lineage API downstream query")
