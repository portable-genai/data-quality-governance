# Compliance FAQ

For compliance, data-governance and model-risk teams assessing this repo's regulatory posture.
Cross-references: [`COMPLIANCE.md`](../../COMPLIANCE.md) (the full P-01 to P-13 and R1 to R8 map
with an evidence file per row, plus the adopter-owned crosswalk), [`SPEC.md`](../../SPEC.md),
[`practices-audit.md`](../practices-audit.md), [`model-card.md`](../model-card.md).

### Is this system making certification decisions autonomously?

It computes them deterministically and escalates the consequential ones. Two outcomes set
`requires_human_review` and are ROUTED to the `human-review-console` in the same request
that produced them (dependency rule R8): DECERTIFYING a dataset that was previously certified, and
ANY sensitive-category PII finding. Setting the flag and calling `ReviewRouterPort.route` is one
act, on the API, the CLI and the agent tool alike, so an escalation never depends on a later job
that may not exist. The managed router REFUSES when no console is configured rather than swallowing
the escalation, and the on-premises one raises. A local router that silently did nothing would let
a producer ship R8 unwired and green, which is why the offline one enqueues to an inspectable
outbox instead.

### What is the model-risk story for a system with no model?

There is no model in the path: no generation, narration or LLM port is bound in any profile, and
there is no generation adapter in any family. [`model-card.md`](../model-card.md) records that as a
boundary rather than a model, names the deterministic engine behind every consequential output, and
lists the controls that must exist BEFORE a model is introduced (a generation port registered in
the five places `CONTRIBUTING.md` names, a pinned model id, budget and rate limits with a kill
switch, an eval that scores the live model, and prompt-injection screening through the `agent-guardrail-gateway`).

Be careful with one name: `domain/pii_classifier.py` is a CLASSIFIER but not a model. It is rule
and pattern based, returns every contributing signal with its weight, and has no learned parameter.

### Is there an evaluation gate?

Yes, in two layers. `eval/run_eval.py --mode smoke` runs offline in `make gate` on every change,
driving the REAL engines and the certification orchestrator against a golden set with SDK-free
adapters and scoring the `h4-data-quality` bundle: `finding_accuracy` 0.90, `drift_recall` 0.85,
`drift_precision` 0.85, `pii_f1` 0.85, `verdict_accuracy` 0.90, `narrative_groundedness` 0.99,
`review_safety` 0.99. Every metric scores against the DATASET'S OWN expected label, never against
the pipeline's own verdict, and the harness proves each metric can go RED before it trusts the
report. `--mode gate` delegates the promotion verdict to the sibling `model-quality-gate` authority and refuses
to run off the managed profile. What is still open: this repo's metric bundle is not yet registered
with `model-quality-gate`, so gate mode has no authority to ask (P-08 and R5).

### How is the work auditable and reproducible?

Every certification writes an already-redacted `AuditEvent` whose actor is the verified principal,
never the request body. Every figure on the scorecard carries a `Citation` back to the rule,
column, drift diff or PII signal that produced it, and every engine is pure stdlib scored against
an explicit `as_of`, so an auditor recomputes any verdict from the same inputs without the service.
The trail is hash-chained AND externally anchored: only the anchor detects a truncated tail,
because a truncated chain still verifies. `tests/unit/test_audit_anchor.py` proves both halves plus
the control case. Operating rules are in [`runbook.md`](../runbook.md).

### How is personal data handled?

Redaction happens before every boundary, not once. The shared `pii-kit` recognizers selected by
`domain/pii.py` mask values before the audit write, and `adapters/_review_payload.py` redacts
against EVERY jurisdiction's rows before a review leaves the process, because the `human-review-console` is a
shared sink and `human-review-console` redacts again on arrival (defence in depth). A tool result is masked before it
can become model context. `tests/unit/test_not_falsely_green.py` proves the safety metric can go
red rather than being green by construction. Separately, `domain/pii_classifier.py` labels which
columns are `pii_direct`, `pii_quasi` or `sensitive` and recommends an action per category
(tokenize or mask, generalise or bucket, or block pending DPO approval).

### Is data residency enforced, or only documented?

Enforced at deploy time, with an honest caveat. `infra/terraform/variables.tf` validates the
effective region against `var.allowed_regions` at plan time, so an unapproved region fails before
anything is created; `org_policy.tf` applies the `gcp.resourceLocations` allowlist restricted to
that region's location group and bans exportable service-account keys; `kms.tf` creates a REGIONAL
CMEK key ring with 90-day rotation and per-service-agent bindings; `vpc_sc.tf` stands up a
dry-run-first VPC-SC perimeter; `logging_worm.tf` puts the locked WORM audit bucket in the same
region; `production_edge.tf` restricts Cloud Run ingress to the internal load balancer. The caveats
are real and stated in the P-03 row: the org-policy and perimeter layers are gated on
`var.enable_org_policies`, `var.enable_vpc_sc` and `var.vpc_sc_enforce`, and no build step runs the
Terraform assertions in `production_edge.tftest.hcl`, so nothing in the offline gate would catch a
regression in that file.

### Which regulators does this map to?

`COMPLIANCE.md` aligns to MAS TRM, APRA CPS 234 and CPS 230, HKMA and PDPA-class regimes at the
level of the catalog's own principles and rules. The mapping from those to a specific regulation,
and the judgement that a control is SUFFICIENT for it, is explicitly **adopter-owned**: it depends
on the institution's risk appetite, its regulator, its licence conditions and its existing control
library. This repo does not make that claim on an adopter's behalf, and no row should be quoted as
regulatory assurance. An adopter is expected to add, in their own control library: the crosswalk to
their control ids, the risk acceptance for every row still Partial or TODO at go-live, a
second-line review of the deterministic policy in `domain/` (bank-owned logic, not a vendor default
to inherit unexamined), and the retention schedule and legal basis for the audit trail.

### What is still open at the control level?

Read the tables rather than a summary, but the honest list from `COMPLIANCE.md`: **TODO** on P-05
(no retrieval, so nothing to ground), P-10 (no timeouts, circuit breaker or documented kill switch
per outbound dependency, and no CPS 230 recovery objectives recorded in the runbook), P-11 (no cost
or latency controls, because there is no model call to route or cache) and R6 (no `architecture-validator` intake
reference). **Partial** on P-01 (no Interconnect attachment), P-03 and P-09 (the deploy-time layers
are shipped but unguarded by any test the build runs), P-08 and R5 (bundle not registered with
`model-quality-gate`), R1 (no guardrail port), R2 (the audit half is local, not yet in the shared `agent-observability` sink), R4
(the agent card is served but not registered with `agent-registry`) and tenant isolation (no object-level
authorisation, because there is no queryable store yet). The practices audit adds B4: the policy
numbers are module constants rather than a `policy:` block a bank can set without a code change.

### Can we run it against real data today?

Not without your own legal, security and model-risk sign-off. The seeded warehouse, the catalog
edges, the rule packs and the eval golden set are all obviously fictional, using `.example`
domains, RFC 5737 and RFC 3849 literals and invented parties. [`../ADOPTING.md`](../ADOPTING.md)
section 6 is the checklist that must precede any live use.
