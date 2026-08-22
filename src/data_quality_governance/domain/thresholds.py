"""Certification thresholds and the eval metric bundle (pure stdlib).

Cribs the shape of Hrz4's ``thresholds.py``: named metric bundles, a ``threshold_for`` that
RAISES on an unknown metric name (Hrz4's recorded silent-pass fix), and an ``is_borderline``
margin that flags a marginal pass for review. Two roles live here:

* the CERTIFICATION bands (:data:`CERT_MIN_PASS_RATIO`, :data:`CONDITIONAL_MIN_PASS_RATIO`) the
  scorecard folds its per-check results against, and
* the EVAL bundle (:data:`METRIC_BUNDLES`) ``eval/run_eval.py`` gates against, mirroring the
  sibling-bundle pattern Hrz4's map exists to serve.

The bars are deliberately strict for a second-line control: a dataset is not CERTIFIED while a
HIGH/CRITICAL check fails, its data is stale, or a sensitive-category PII column is unreviewed.
"""

from __future__ import annotations

from collections.abc import Iterable

from .errors import UnknownMetricError

#: A dataset is CERTIFIED only when at least this fraction of its DQ checks pass (and no
#: high-severity check fails, and it is fresh, and no sensitive PII is unreviewed: the scorecard
#: service applies those gates on top of the ratio).
CERT_MIN_PASS_RATIO: float = 0.98

#: Below the certified bar but at or above this, and with no failing HIGH/CRITICAL check, a
#: dataset is CONDITIONALLY certified: usable with the failing checks tracked as tickets.
CONDITIONAL_MIN_PASS_RATIO: float = 0.90

#: How close to a threshold a passing metric may sit before the gate flags it for review.
BORDERLINE_MARGIN: float = 0.02

#: Named per-metric eval bundles (the sibling-bundle pattern). ``h4-data-quality`` is this
#: repo's own gate; a metric name ending in ``safety`` carries the strictest bar. Every metric
#: scores against the DATASET'S OWN expected outcome, never the pipeline's verdict.
METRIC_BUNDLES: dict[str, dict[str, float]] = {
    "h4-data-quality": {
        "finding_accuracy": 0.90,
        "drift_recall": 0.85,
        "drift_precision": 0.85,
        "pii_f1": 0.85,
        "verdict_accuracy": 0.90,
        "narrative_groundedness": 0.99,
        "review_safety": 0.99,
    },
}

#: The default bundle name, so a caller that names nothing still gets this repo's gate.
DEFAULT_BUNDLE = "h4-data-quality"

#: Flat metric -> bar view, first-wins across bundles, for the bundle-less ``threshold_for``.
EVAL_THRESHOLDS: dict[str, float] = {}
for _bundle in METRIC_BUNDLES.values():
    for _metric, _bar in _bundle.items():
        EVAL_THRESHOLDS.setdefault(_metric, _bar)


def threshold_for(metric: str) -> float:
    """Return the bar for ``metric``, fail-closed on an unknown name.

    Raising (rather than a 0.0 fallback) is the fix for the silent-pass trap: an unregistered
    metric would otherwise clear a 0.0 bar with any score.
    """
    try:
        return EVAL_THRESHOLDS[metric]
    except KeyError as exc:
        raise UnknownMetricError(f"unrecognised metric: {metric!r}") from exc


def bundle_thresholds(bundle: str = DEFAULT_BUNDLE) -> dict[str, float]:
    """Return a copy of a named bundle's ``{metric: threshold}`` map, or raise."""
    try:
        return dict(METRIC_BUNDLES[bundle])
    except KeyError as exc:
        known = ", ".join(sorted(METRIC_BUNDLES))
        raise UnknownMetricError(f"unknown metric bundle {bundle!r} (known: {known})") from exc


def validate_metrics(metrics: Iterable[str]) -> tuple[str, ...]:
    """Return ``metrics`` as a tuple, raising ``UnknownMetricError`` on any unknown name."""
    resolved = tuple(metrics)
    unknown = sorted({m for m in resolved if m not in EVAL_THRESHOLDS})
    if unknown:
        raise UnknownMetricError(f"unrecognised metric(s): {', '.join(unknown)}")
    return resolved


def is_borderline(score: float, threshold: float, margin: float = BORDERLINE_MARGIN) -> bool:
    """Whether a passing score sits within ``margin`` above its threshold (a marginal pass).

    A perfect score (1.0) is never borderline: it is the strongest possible pass, which matters
    for near-1.0 bars where the band would otherwise be wider than the headroom.
    """
    if score >= 1.0:
        return False
    return threshold <= score < threshold + margin
