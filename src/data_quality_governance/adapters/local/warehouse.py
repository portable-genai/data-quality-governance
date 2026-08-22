"""Local WarehousePort: a seeded, obviously fictional warehouse with planted defects.

Three datasets, engineered so the deterministic engines have something real to find and the demo
has a certified / uncertified / conditional arc:

* ``customer_master``    - clean and fresh: unique ids, valid emails, no nulls. CERTIFIED.
* ``transactions_daily`` - a STALE partition, a duplicate id, null amounts and an out-of-set
  currency. UNCERTIFIED (a high-severity, fail-closed outcome).
* ``marketing_events``   - a renamed column (schema drift) and a sensitive-category ``health``
  column, otherwise clean. CONDITIONAL, and routed to human review for the sensitive PII.

Partition timestamps are computed RELATIVE to the current time with fixed offsets, so freshness
is deterministic regardless of when the gate runs (the age is the offset, always), while the
column statistics are fixed and replay byte-for-byte. Every value is synthetic: RFC 5737 / RFC
3849 literals, ``.example`` domains and plainly invented names and identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from ...config import Settings
from ...domain.kernel import utcnow
from ...domain.models import ColumnSample, SchemaColumn, TableMetadata

_TS_FMT = "%Y-%m-%dT%H:%M:%S"


@dataclass(frozen=True, slots=True)
class _Dataset:
    row_count: int
    partition_age_hours: int
    columns: dict[str, tuple[str, ...]]
    schema: tuple[tuple[str, str], ...]


_EMAILS = tuple(f"user{n}@bank.example" for n in range(1001, 1013))
_NAMES = (
    "Ada Lovelace",
    "Grace Hopper",
    "Alan Turing",
    "Edsger Dijkstra",
    "Barbara Liskov",
    "Ken Thompson",
    "Dennis Ritchie",
    "Margaret Hamilton",
    "Donald Knuth",
    "Radia Perlman",
    "Leslie Lamport",
    "Frances Allen",
)

_DATASETS: dict[str, _Dataset] = {
    "customer_master": _Dataset(
        row_count=12,
        partition_age_hours=2,
        columns={
            "customer_id": tuple(str(n) for n in range(1001, 1013)),
            "email": _EMAILS,
            "full_name": _NAMES,
            "dob": tuple(f"1980-{(i % 12) + 1:02d}-14" for i in range(12)),
            "postcode": tuple(("018956", "049483", "238823")[i % 3] for i in range(12)),
            "balance": tuple(f"{1000 + n * 7}.50" for n in range(12)),
        },
        schema=(
            ("customer_id", "INTEGER"),
            ("email", "STRING"),
            ("full_name", "STRING"),
            ("dob", "DATE"),
            ("postcode", "STRING"),
            ("balance", "NUMERIC"),
        ),
    ),
    "transactions_daily": _Dataset(
        row_count=12,
        partition_age_hours=50,  # past the 24h SLA -> stale
        columns={
            # a duplicate txn id (T0007 twice) -> uniqueness fails
            "txn_id": tuple(("T0007" if n in (7, 8) else f"T{n:04d}") for n in range(1, 13)),
            "account_id": tuple(f"A{(n % 5) + 1:03d}" for n in range(12)),
            # two null amounts -> completeness fails
            "amount": tuple(("" if n in (3, 9) else f"{n * 12}.00") for n in range(12)),
            # one out-of-set currency -> referential integrity fails
            "currency": tuple(
                ("XYZ" if n == 4 else ("SGD", "USD", "HKD")[n % 3]) for n in range(12)
            ),
            "txn_ts": tuple(f"2026-07-30T{(n % 24):02d}:00:00" for n in range(12)),
        },
        schema=(
            ("txn_id", "STRING"),
            ("account_id", "STRING"),
            ("amount", "NUMERIC"),
            ("currency", "STRING"),
            ("txn_ts", "TIMESTAMP"),
        ),
    ),
    "marketing_events": _Dataset(
        row_count=12,
        partition_age_hours=3,
        columns={
            "event_id": tuple(f"E{n:04d}" for n in range(1, 13)),
            "customer_id": tuple(str(1001 + (n % 6)) for n in range(12)),
            # a sensitive-category column by name -> requires review, blocks full certification.
            # Values avoid the "none" null sentinel so the completeness check is not tripped.
            "health_condition": tuple(("healthy", "diabetes", "asthma")[n % 3] for n in range(12)),
            # one null campaign -> a MEDIUM completeness miss
            "campaign": tuple(("" if n == 5 else f"camp_{n % 4}") for n in range(12)),
            "event_ts": tuple(f"2026-08-01T{(n % 24):02d}:00:00" for n in range(12)),
        },
        # live schema RENAMED 'channel' (baseline) -> 'source' (both STRING) -> MEDIUM drift
        schema=(
            ("event_id", "STRING"),
            ("customer_id", "INTEGER"),
            ("health_condition", "STRING"),
            ("campaign", "STRING"),
            ("event_ts", "TIMESTAMP"),
            ("source", "STRING"),
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class LocalWarehouseAdapter:
    """The SDK-free fixture warehouse used by the gate, the demo and the eval."""

    settings: Settings = field(default=None)  # type: ignore[assignment]

    def __init__(self, settings: Settings) -> None:
        object.__setattr__(self, "settings", settings)

    def datasets(self) -> tuple[str, ...]:
        return tuple(_DATASETS)

    def _get(self, dataset_id: str) -> _Dataset:
        try:
            return _DATASETS[dataset_id]
        except KeyError as exc:
            raise KeyError(f"unknown dataset {dataset_id!r}") from exc

    def metadata(self, dataset_id: str) -> TableMetadata:
        ds = self._get(dataset_id)
        partition = (utcnow() - timedelta(hours=ds.partition_age_hours)).strftime(_TS_FMT)
        load = (utcnow() - timedelta(hours=ds.partition_age_hours - 1)).strftime(_TS_FMT)
        return TableMetadata(
            dataset_id=dataset_id,
            row_count=ds.row_count,
            load_timestamp=load,
            partition_timestamp=partition,
            schema=self.live_schema(dataset_id),
        )

    def sample_columns(self, dataset_id: str) -> tuple[ColumnSample, ...]:
        ds = self._get(dataset_id)
        return tuple(ColumnSample(name=name, values=values) for name, values in ds.columns.items())

    def live_schema(self, dataset_id: str) -> tuple[SchemaColumn, ...]:
        ds = self._get(dataset_id)
        return tuple(SchemaColumn(name=n, data_type=t) for n, t in ds.schema)
