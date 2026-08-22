"""Deterministic freshness scoring (pure stdlib).

Scores a dataset's recency against its declared SLA using a caller-supplied ``as_of``, so a run
is replayable rather than depending on wall-clock time inside the engine. The age is the whole
number of hours between the dataset's partition timestamp and ``as_of``; a breach past the SLA
is HIGH severity, and a breach past twice the SLA is CRITICAL.
"""

from __future__ import annotations

from datetime import datetime

from .kernel import Citation, Severity
from .models import FreshnessResult, TableMetadata

_FORMATS = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d")


def _parse(timestamp: str) -> datetime:
    for fmt in _FORMATS:
        try:
            return datetime.strptime(timestamp.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"unparseable timestamp {timestamp!r}")


def age_hours(partition_timestamp: str, as_of: str) -> float:
    """Whole-hours age of a partition relative to ``as_of`` (never negative)."""
    delta = _parse(as_of) - _parse(partition_timestamp)
    return max(0.0, round(delta.total_seconds() / 3600.0, 3))


def score_freshness(metadata: TableMetadata, sla_hours: int, *, as_of: str) -> FreshnessResult:
    """Score a dataset's recency against ``sla_hours`` at ``as_of``, fail-closed on staleness."""
    age = age_hours(metadata.partition_timestamp, as_of)
    breached = age > sla_hours
    if age > 2 * sla_hours:
        severity = Severity.CRITICAL
    elif breached:
        severity = Severity.HIGH
    else:
        severity = Severity.LOW
    snippet = f"age {age}h against SLA {sla_hours}h (partition {metadata.partition_timestamp})"
    return FreshnessResult(
        dataset_id=metadata.dataset_id,
        sla_hours=sla_hours,
        age_hours=age,
        breached=breached,
        severity=severity,
        citation=Citation(
            source_id=f"freshness:{metadata.dataset_id}",
            title=f"Freshness of {metadata.dataset_id}",
            snippet=snippet,
        ),
    )
