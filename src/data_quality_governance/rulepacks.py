"""Read the YAML rule packs (config-as-data) into frozen ``RulePack`` objects.

Rule packs live in ``config/rulepacks/*.yaml`` so a data owner edits a policy file rather than
code. This reader does the file I/O and hands each parsed mapping to the pure, fail-closed
``domain.rulepack_loader.parse_pack``. It lives at the package root (not in ``domain/``, which is
pure and does no I/O), alongside ``config.py`` which also reads files.

The directory is resolved relative to the working directory (the repo root for ``make`` targets
and ``/app`` in the image), with the env override ``DATAQUALITY_RULEPACK_DIR``. A named directory
that does not exist raises: somebody pointed at a policy set, and silently running on an empty
one is how a dataset gets certified against no checks at all.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from hex_service_kit.netdefaults import read_env_setting

from .domain.models import RulePack
from .domain.rulepack_loader import parse_pack

_RULEPACK_DIR_ENV = "DATAQUALITY_RULEPACK_DIR"
DEFAULT_RULEPACK_DIR = Path("config") / "rulepacks"


def _resolve_dir(directory: Path | None) -> Path:
    if directory is not None:
        return directory
    setting = read_env_setting(_RULEPACK_DIR_ENV)
    if setting.is_configured_empty:
        raise ValueError(f"{_RULEPACK_DIR_ENV} is set but empty; unset it or name a directory.")
    if setting.has_value:
        named = Path(setting.value)
        if not named.exists():
            raise FileNotFoundError(f"rule-pack directory {named} does not exist")
        return named
    return DEFAULT_RULEPACK_DIR


def load_rulepacks(directory: Path | None = None) -> dict[str, RulePack]:
    """Load every ``*.yaml`` rule pack, keyed by dataset id. Fail-closed on a bad pack."""
    target = _resolve_dir(directory)
    packs: dict[str, RulePack] = {}
    if not target.exists():
        return packs
    for path in sorted(target.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        pack = parse_pack(data)
        packs[pack.dataset_id] = pack
    return packs
