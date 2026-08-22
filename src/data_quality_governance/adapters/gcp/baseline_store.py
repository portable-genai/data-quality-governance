"""Managed BaselineStorePort: a durable, tenant-scoped baseline store (lazy SDK imports).

The ``google.cloud`` import is inside the methods, so this module imports with no cloud SDK and
the offline gate binds it; a call with nothing reachable refuses with ``ImportError``. A
deployment backs this with Firestore or a CMEK-encrypted GCS object per tenant.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import SchemaColumn


class CloudBaselineStore:
    """Firestore/GCS-backed baseline store. SDK imports are lazy (portability proof, P-02)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self) -> object:
        from google.cloud import firestore  # lazy: offline binding must import clean

        return firestore.Client()

    def get_baseline(self, dataset_id: str, *, tenant: str) -> tuple[SchemaColumn, ...] | None:
        self._client()
        raise NotImplementedError("wire the tenant-scoped baseline document read")

    def put_baseline(
        self, dataset_id: str, schema: tuple[SchemaColumn, ...], *, tenant: str
    ) -> None:
        self._client()
        raise NotImplementedError("wire the tenant-scoped baseline document write")
