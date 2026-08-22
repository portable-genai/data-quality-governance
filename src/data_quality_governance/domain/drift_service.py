"""Deterministic schema-drift detection (pure stdlib).

Diffs a dataset's LIVE schema against a stored BASELINE and classifies each difference on a
fixed severity ladder:

* ``removed``  (HIGH): a baseline column is gone. Breaks every downstream reader of it.
* ``retyped``  (HIGH): a column kept its name but changed type. Silent corruption risk.
* ``renamed``  (MEDIUM): a removed and an added column share a type and look like the same
  column renamed. Recoverable, but breaks column-name-bound queries.
* ``added``    (LOW): a new column appeared. Additive, rarely breaking.

The rename heuristic is deliberate and conservative: a removed column and an added column are
treated as a rename only when they share a data type AND exactly one removed and one added
column carry that type, so an ambiguous many-to-many change stays classified as the safer
separate add/remove pair.
"""

from __future__ import annotations

from .kernel import Citation, Severity
from .models import DriftFinding, DriftKind, SchemaColumn

_SEVERITY = {
    DriftKind.REMOVED: Severity.HIGH,
    DriftKind.RETYPED: Severity.HIGH,
    DriftKind.RENAMED: Severity.MEDIUM,
    DriftKind.ADDED: Severity.LOW,
}


def _citation(dataset_id: str, kind: DriftKind, column: str, detail: str) -> Citation:
    return Citation(
        source_id=f"drift:{dataset_id}:{column}",
        title=f"Schema {kind.value} on {dataset_id}.{column}",
        snippet=detail[:120],
    )


def _finding(dataset_id: str, kind: DriftKind, column: str, frm: str, to: str) -> DriftFinding:
    detail = f"{kind.value}: {column} {frm or '(absent)'} -> {to or '(absent)'}"
    return DriftFinding(
        dataset_id=dataset_id,
        kind=kind,
        column=column,
        from_type=frm,
        to_type=to,
        severity=_SEVERITY[kind],
        citation=_citation(dataset_id, kind, column, detail),
    )


def diff_schema(
    dataset_id: str,
    baseline: tuple[SchemaColumn, ...],
    live: tuple[SchemaColumn, ...],
) -> tuple[DriftFinding, ...]:
    """Classify every difference between ``baseline`` and ``live`` into drift findings."""
    base = {c.name: c.data_type for c in baseline}
    now = {c.name: c.data_type for c in live}

    retyped = [n for n in base.keys() & now.keys() if base[n] != now[n]]
    removed = sorted(base.keys() - now.keys())
    added = sorted(now.keys() - base.keys())

    findings: list[DriftFinding] = []
    for name in sorted(retyped):
        findings.append(_finding(dataset_id, DriftKind.RETYPED, name, base[name], now[name]))

    # Conservative rename detection: a removed and an added column that uniquely share a type.
    renamed_out: set[str] = set()
    renamed_in: set[str] = set()
    for r in removed:
        candidates = [a for a in added if now[a] == base[r] and a not in renamed_in]
        siblings = [r2 for r2 in removed if base[r2] == base[r] and r2 not in renamed_out]
        if len(candidates) == 1 and len(siblings) == 1:
            a = candidates[0]
            findings.append(_finding(dataset_id, DriftKind.RENAMED, f"{r}->{a}", base[r], now[a]))
            renamed_out.add(r)
            renamed_in.add(a)

    for name in removed:
        if name not in renamed_out:
            findings.append(_finding(dataset_id, DriftKind.REMOVED, name, base[name], ""))
    for name in added:
        if name not in renamed_in:
            findings.append(_finding(dataset_id, DriftKind.ADDED, name, "", now[name]))
    return tuple(findings)
