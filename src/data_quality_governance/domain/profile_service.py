"""Deterministic column profiling (pure stdlib).

Turns the warehouse's bounded ``ColumnSample`` rows plus ``TableMetadata`` into a
``DatasetProfile``: per column, the null ratio, cardinality ratio, an inferred type and length
statistics. Every number is computed here, replayably: the same fixture samples produce a
byte-identical profile, which is the property the eval's replay test pins. A model produces none
of these figures.

A value is NULL when it is the empty string or one of the conventional null sentinels a
warehouse export uses (``NULL`` / ``None`` / ``NaN`` / ``N/A``), compared case-insensitively.
Type inference is a fixed ladder: every non-null value integer -> ``integer``; every one a
number -> ``numeric``; every one an ISO-8601-ish date -> ``date``; otherwise ``text``.
"""

from __future__ import annotations

import re

from .models import ColumnProfile, ColumnSample, DatasetProfile, TableMetadata

#: Sentinels an export writes for a null cell, matched case-insensitively after stripping.
_NULL_TOKENS: frozenset[str] = frozenset({"", "null", "none", "nan", "n/a", "na"})

_INT_RE = re.compile(r"[+-]?\d+$")
_NUM_RE = re.compile(r"[+-]?\d+(\.\d+)?$")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$")


def is_null(value: str) -> bool:
    """Whether ``value`` counts as null (empty or a conventional null sentinel)."""
    return value.strip().lower() in _NULL_TOKENS


def _infer_type(non_null: list[str]) -> str:
    if not non_null:
        return "unknown"
    if all(_INT_RE.match(v) for v in non_null):
        return "integer"
    if all(_NUM_RE.match(v) for v in non_null):
        return "numeric"
    if all(_DATE_RE.match(v) for v in non_null):
        return "date"
    return "text"


def profile_column(sample: ColumnSample) -> ColumnProfile:
    """Compute one column's deterministic statistics from its sampled values."""
    values = list(sample.values)
    non_null = [v.strip() for v in values if not is_null(v)]
    lengths = [len(v) for v in non_null]
    return ColumnProfile(
        name=sample.name,
        inferred_type=_infer_type(non_null),
        sample_size=len(values),
        non_null_count=len(non_null),
        null_count=len(values) - len(non_null),
        distinct_count=len(set(non_null)),
        min_length=min(lengths, default=0),
        max_length=max(lengths, default=0),
    )


def profile_dataset(
    metadata: TableMetadata, samples: tuple[ColumnSample, ...], *, as_of: str
) -> DatasetProfile:
    """Profile every sampled column into a ``DatasetProfile`` at a caller-supplied ``as_of``."""
    return DatasetProfile(
        dataset_id=metadata.dataset_id,
        metadata=metadata,
        columns=tuple(profile_column(s) for s in samples),
        as_of=as_of,
    )
