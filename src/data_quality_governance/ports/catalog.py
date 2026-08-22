"""CatalogPort: a Dataplex-style boundary supplying ownership, tags and lineage edges.

The remediation and lineage-impact logic needs to know who owns a dataset and which downstream
datasets read from it; that ownership and those edges live in a data catalog, not in this
service. The ``local`` family is a fixture catalog, ``gcp`` reads Dataplex with lazy imports,
``onprem`` is a fail-fast placeholder.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CatalogPort(Protocol):
    def owner(self, dataset_id: str) -> str:
        """The accountable owner (a role or team address) for a dataset."""
        ...

    def tags(self, dataset_id: str) -> tuple[str, ...]:
        """Governance tags on a dataset (e.g. ``tenant:...``, ``domain:...``)."""
        ...

    def downstream(self, dataset_id: str) -> tuple[str, ...]:
        """The datasets that read from this one (the lineage-impact set)."""
        ...
