"""Parse a rule-pack mapping into a frozen ``RulePack`` (pure stdlib, fail-closed).

The engine treats rule packs as DATA: the pack is authored in ``config/rulepacks/*.yaml`` and
parsed here. Parsing is fail-closed, so a control cannot silently run a subset of what its owner
configured:

* an unknown ``rule_type`` raises ``RulePackError`` AT LOAD (never a skipped check at scoring);
* an unknown ``severity`` raises;
* a rule missing its ``id`` or ``column`` raises.

This module takes an already-parsed mapping (a ``dict``) rather than a file path, so it imports
no YAML and does no I/O: the file reading lives in the package-level ``rulepacks`` reader.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

from .errors import RulePackError
from .kernel import Severity
from .models import Rule, RulePack, RuleType


def _enum[E: Enum](raw: Any, enum: type[E], field: str, rule_id: str) -> E:
    try:
        return enum(str(raw))
    except ValueError as exc:
        allowed = ", ".join(str(m.value) for m in enum)
        raise RulePackError(f"rule {rule_id!r}: {field} {raw!r} is not one of {allowed}") from exc


def parse_rule(data: Mapping[str, Any]) -> Rule:
    """Parse one rule mapping, fail-closed on an unknown type/severity or a missing field."""
    rule_id = str(data.get("id") or "").strip()
    if not rule_id:
        raise RulePackError(f"a rule is missing its 'id': {dict(data)!r}")
    column = str(data.get("column") or "").strip()
    if not column:
        raise RulePackError(f"rule {rule_id!r} is missing its 'column'")
    params = data.get("params") or {}
    if not isinstance(params, Mapping):
        raise RulePackError(f"rule {rule_id!r}: 'params' must be a mapping")
    return Rule(
        id=rule_id,
        rule_type=_enum(data.get("rule_type"), RuleType, "rule_type", rule_id),
        column=column,
        severity=_enum(data.get("severity", "medium"), Severity, "severity", rule_id),
        owner=str(data.get("owner") or ""),
        description=str(data.get("description") or ""),
        params=tuple((str(k), str(v)) for k, v in params.items()),
    )


def parse_pack(data: Mapping[str, Any]) -> RulePack:
    """Parse a full rule-pack mapping into a frozen ``RulePack``, fail-closed."""
    dataset_id = str(data.get("dataset_id") or "").strip()
    if not dataset_id:
        raise RulePackError("a rule pack is missing its 'dataset_id'")
    rules = data.get("rules") or []
    if not isinstance(rules, list):
        raise RulePackError(f"rule pack {dataset_id!r}: 'rules' must be a list")
    try:
        sla_hours = int(data.get("sla_hours", 24))
    except (TypeError, ValueError) as exc:
        raise RulePackError(f"rule pack {dataset_id!r}: 'sla_hours' must be an integer") from exc
    return RulePack(
        dataset_id=dataset_id,
        owner=str(data.get("owner") or ""),
        sla_hours=sla_hours,
        rules=tuple(parse_rule(r) for r in rules),
    )
