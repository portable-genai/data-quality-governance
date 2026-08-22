"""On-prem BaselineStorePort: fail-fast portability placeholder (sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import SchemaColumn

_MSG = (
    "on-prem baseline storage is a portability placeholder: bind the client's own store "
    "(see docs/onprem-migration.md)."
)


class OnPremBaselineStore:
    """Satisfies BaselineStorePort but refuses: bind the client's own baseline store."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_baseline(self, dataset_id: str, *, tenant: str) -> tuple[SchemaColumn, ...] | None:
        raise NotImplementedError(_MSG)

    def put_baseline(
        self, dataset_id: str, schema: tuple[SchemaColumn, ...], *, tenant: str
    ) -> None:
        raise NotImplementedError(_MSG)
