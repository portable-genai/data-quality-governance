# Portability FAQ

For architecture, cloud and exit-planning reviewers who want to know how real the "no lock-in"
claim is and how an off-cloud or sovereign exit would actually work. Cross-references:
[`ARCHITECTURE.md`](../../ARCHITECTURE.md), [`onprem-migration.md`](../onprem-migration.md),
[`runbook.md`](../runbook.md).

## What is the no-lock-in claim, concretely?

`domain/` is pure standard library plus the stdlib-only commons: no web framework, no cloud SDK, no
HTTP client. Every boundary is a `@runtime_checkable` `Protocol` in `ports/`, and which adapter
implements it is a line in `config/settings.yaml` rather than a code edit.
`tests/unit/test_core_purity.py` holds the domain to that, and
`tests/contract/test_port_parity.py` proves every port binds in every profile with the cloud SDKs
unimportable.

## What are the ports and the profiles?

Eight ports across seven modules: `AuditSinkPort`, `IdentityPort` (re-exported from the commons),
`ReviewRouterPort`, `WarehousePort`, `CatalogPort`, `BaselineStorePort`, and
`ObservabilityTracerPort` plus `EvaluationGatePort` (both from `ports/observability.py`). There is
deliberately no generation or model port; see [`model-card.md`](../model-card.md).

`DATAQUALITY_PROFILE` selects the whole stack, in three states: UNSET is NO CHOICE (not a silent
`local`), SET-AND-EMPTY raises at import, and an unknown or mis-capitalised value raises at import.
Both raises kill the process before it can serve a request.

- **`local`** is a real, working, SDK-free offline stack: a seeded fictional warehouse with planted
  defects, a fixture catalog, an in-memory baseline store, a hash-chained anchored audit log, an
  inspectable review outbox, a no-op tracer, and an offline eval scorer that REFUSES to promote.
- **`gcp`** is the managed stack (Cloud Logging WORM, IAP identity, the `human-review-console` intake over S2S,
  BigQuery-style warehouse reads, a Dataplex-style catalog, OpenTelemetry, the `model-quality-gate` promotion
  gate), with every cloud import LAZY inside the method so the other two profiles import with no
  SDK installed.
- **`onprem`** is the exit family: fail-fast placeholders that satisfy the same Protocols and
  RAISE, naming the migration target. A placeholder that returned successfully would be a false
  portability claim, and a review router that silently returned would convert every consequential
  result into an unreviewed one.

## Is the portability claim tested, or just asserted?

Tested, and executable. `make portability` runs eight named checks with a pass or fail each: port
map completeness, adapter construction and Protocol conformance, the offline family ANSWERING, the
exit family REFUSING, in-place rewrite detection, anchored truncation detection together with its
control case, the JSON Lines export and foreign reload, and the no-cloud-SDK check. It exits
non-zero on any failure and it prints what it does NOT prove. The contract suite adds the
structural half: `tests/contract/test_port_parity.py` asserts set equality across all five homes of
the port set, and `tests/contract/test_behavioral_parity.py` proves the offline family answers, the
exit family raises and the managed family refuses rather than silently succeeding.

## Is the lazy-import claim proved, or just observed?

Proved. `tests/contract/_sdk_free_probe.py` BLOCKS the `google.cloud` import in a fresh interpreter
and imports the tree anyway, so the check does not depend on the SDK happening to be absent from
the machine.

## How would a sovereign or on-premises exit actually go?

The `onprem` family is the scaffold, and each raising placeholder marks one seam a client fills:
their own analytical store behind `WarehousePort`, their own catalog behind `CatalogPort`, their
own baseline store, their own IdP behind `IdentityPort`, their own audit sink, their own review
console. Because the domain never changes, the exit is an adapter exercise rather than a rewrite.
The written path is [`onprem-migration.md`](../onprem-migration.md).

## Can the data be exported in an open format?

Yes. The audit trail exports to and restores from JSON Lines, so the exit for the evidence is a
file copy; `make portability` exercises the export and a foreign reload as one of its named checks.
The scorecard itself is plain frozen dataclasses over `StrEnum` members whose value IS the wire
value, so the JSON has no vendor shape in it.

## How is residency handled?

The region is chosen ONCE and shared by the runtime and the deployment. `config/settings.yaml`
reads it from `GCP_REGION` (default `asia-southeast1`), `/healthz` reports it and the agent card
prints it, so a drifting deployment is visible. At deploy time `infra/terraform/variables.tf`
validates the effective region against `var.allowed_regions` at plan time, `org_policy.tf` applies
a `gcp.resourceLocations` allowlist restricted to that region's location group, `kms.tf` creates a
REGIONAL CMEK key ring rather than a global one, and `vpc_sc.tf` stands up a dry-run-first VPC-SC
perimeter. Note the toggles: `var.enable_org_policies`, `var.enable_vpc_sc` and
`var.vpc_sc_enforce`. A stack applied with them off is not a compliant one.

## What is honestly NOT portable, or not yet proved?

- The managed profile is not production-cleared. `managed_readiness.py` names the managed warehouse,
  catalog and baseline-store operations that are still construction-only placeholders, and the API
  preflight REFUSES to start on a managed profile while any of them is selected.
- Tamper evidence is scoped to what the local sink can prove. `portability_demo.py` says so
  explicitly rather than overclaiming; production non-rewritability is the locked Cloud Logging
  bucket's job, or `agent-observability`'s.
- The Terraform assertions in `infra/terraform/production_edge.tftest.hcl` are real but unexercised:
  no build step runs `terraform test`, because the offline gate may not need a terraform binary. See
  the P-03 row in [`COMPLIANCE.md`](../../COMPLIANCE.md).
