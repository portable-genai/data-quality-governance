"""On-prem WarehousePort: fail-fast portability placeholder (the sovereign-exit proof, P-12).

The client runs its own analytical store (an on-prem warehouse, a sovereign-cloud dataset). This
binding refuses at call time rather than pretending to profile, so a migration surfaces the
integration point instead of shipping a silent no-op.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ColumnSample, SchemaColumn, TableMetadata


class OnPremWarehouseAdapter:
    """Satisfies WarehousePort but refuses: bind the client's own warehouse connector."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def datasets(self) -> tuple[str, ...]:
        raise NotImplementedError(_MSG)

    def metadata(self, dataset_id: str) -> TableMetadata:
        raise NotImplementedError(_MSG)

    def sample_columns(self, dataset_id: str) -> tuple[ColumnSample, ...]:
        raise NotImplementedError(_MSG)

    def live_schema(self, dataset_id: str) -> tuple[SchemaColumn, ...]:
        raise NotImplementedError(_MSG)


_MSG = (
    "on-prem warehouse access is a portability placeholder: bind the client's own store "
    "connector (see docs/onprem-migration.md)."
)
