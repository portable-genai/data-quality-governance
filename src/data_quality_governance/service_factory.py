"""Build the certification orchestrator from a container and the on-disk rule packs.

One place wires the ports and the rule-pack set into a ``CertificationService``, so the API, the
CLI, the agent tools, the demo and the eval all construct the identical service. It loads the
YAML rule packs (config-as-data) once per call; a deployment that wants a warm cache holds the
returned service.
"""

from __future__ import annotations

from pathlib import Path

from .config import Container
from .domain.certification_service import CertificationService
from .rulepacks import load_rulepacks


def build_certification_service(
    container: Container, *, rulepack_dir: Path | None = None
) -> CertificationService:
    """Wire the warehouse, catalog, baseline store and audit ports plus the rule packs."""
    return CertificationService(
        warehouse=container.warehouse,
        catalog=container.catalog,
        baseline_store=container.baseline_store,
        audit=container.audit,
        tracer=container.tracer,
        rulepacks=load_rulepacks(rulepack_dir),
    )
