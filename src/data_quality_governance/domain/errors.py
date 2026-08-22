"""Domain error types (pure stdlib): fail-closed signals the engines raise at load or scoring."""

from __future__ import annotations


class RulePackError(ValueError):
    """A rule pack could not be loaded: an unknown rule type, or a malformed row.

    Raised AT LOAD, not at scoring. A pack the engine cannot fully understand is a gap in the
    control, and running the subset it recognises would silently certify a dataset against fewer
    checks than the owner configured.
    """


class CrossTenantError(Exception):
    """A caller asked for a scorecard that exists only under a DIFFERENT tenant.

    The API maps this to 403, never 404: answering 404 would leak whether the dataset exists at
    all to a tenant with no right to know it.
    """


class UnknownMetricError(KeyError):
    """A metric or threshold-bundle name the thresholds table does not register.

    Raising (rather than clearing a 0.0 bar) is the fix for the silent-pass trap: an
    unregistered metric must be an error, never a free PASS.
    """
