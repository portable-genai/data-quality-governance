"""On-prem CatalogPort: fail-fast portability placeholder (the sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings

_MSG = (
    "on-prem catalog access is a portability placeholder: bind the client's own catalog/lineage "
    "connector (see docs/onprem-migration.md)."
)


class OnPremCatalogAdapter:
    """Satisfies CatalogPort but refuses: bind the client's own catalog connector."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def owner(self, dataset_id: str) -> str:
        raise NotImplementedError(_MSG)

    def tags(self, dataset_id: str) -> tuple[str, ...]:
        raise NotImplementedError(_MSG)

    def downstream(self, dataset_id: str) -> tuple[str, ...]:
        raise NotImplementedError(_MSG)
