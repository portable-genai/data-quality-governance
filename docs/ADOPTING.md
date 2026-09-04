# Adopting this repo as your base

This repository (H4, the Data Quality and Governance Agent) is a **common base** that a bank or
other regulated institution forks to build its own **second-line data-certification service**: it
profiles a dataset, runs deterministic data-quality, freshness, schema-drift and PII-classification
checks over it, and folds the results into one cited scorecard with a certification verdict and
remediation tickets. It ships a reusable hexagonal core (a pure-stdlib domain, eight typed ports,
three swappable adapter families, a green offline gate) plus a fully worked data-governance
vertical that you can keep, retune, or replace with your own control framework.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical rebrand**
(one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the layout, the port table and the
> request pipeline), [`CONTRIBUTING.md`](../CONTRIBUTING.md) (the file-by-file touch list for a
> new adapter and for a new port), [`COMPLIANCE.md`](../COMPLIANCE.md) (every principle and rule
> mapped to a control), [`model-card.md`](model-card.md) (why there is no model in the path today
> and what a later one may do), and the [`faq/`](faq/) directory.

---

## 1. What you keep vs what you rewrite

The core is hexagonal, and the boundary between reusable machinery and your governance vertical is
a physical module split with an enforced dependency direction (practices-audit check A7).
`domain/kernel.py` holds the vertical-neutral machinery and imports nothing from this vertical;
`domain/models.py` imports `kernel`, never the reverse. A fork building a different vertical
rewrites `models.py` and leaves `kernel.py` untouched.

| Layer | Where | For a new control framework |
|---|---|---|
| **Kernel** (vertical-neutral) | all of `domain/kernel.py` (`Severity`, `Decision`, `Citation`, `AuditEvent`, `utcnow`), `domain/errors.py`, every Protocol in `ports/` plus the identity vocabulary in `ports/identity.py`, the `Settings` and `Container` wiring in `config.py`, and the redacted review conversion in `adapters/_review_payload.py` | keep untouched |
| **Policy** (your numbers) | the certification bands and the eval bundle in `domain/thresholds.py` (`CERT_MIN_PASS_RATIO`, `CONDITIONAL_MIN_PASS_RATIO`, `BORDERLINE_MARGIN`, `METRIC_BUNDLES`), the classifier thresholds that are dataclass fields on `PiiClassifier` in `domain/pii_classifier.py`, the jurisdiction tuple in `domain/pii.py`, the drift severity ladder in `domain/drift_service.py`, the freshness ladder in `domain/freshness_service.py`, and the rule packs in `config/rulepacks/*.yaml` | change deliberately (see section 4) |
| **Vertical** (the governance artifacts) | the artifact models in `domain/models.py` (`RulePack`, `DQFinding`, `FreshnessResult`, `DriftFinding`, `PiiClassification`, `RemediationTicket`, `DatasetScorecard`, `CertificationResponse` and the four taxonomies), the engines that produce them (`profile_service`, `dq_rule_engine`, `freshness_service`, `drift_service`, `pii_classifier`, `remediation_service`, `scorecard_service`, `certification_service`), the seeded warehouse and catalog fixtures, the eval golden set, and the UI panels | rewrite or reseed for your framework |

If your product is another *data-governance or assurance* service, most of the kernel, the three
profiles, the deterministic-verdict pattern, the anchored audit chain, the eval gate and the `human-review-console`
review routing transfer directly. You replace the artifact models and the engines, and you retune
the policy numbers.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly.

- **Upstream-owned** (take our changes): `domain/kernel.py`, `domain/errors.py`, `ports/`,
  `tests/contract/`, the eval harness mechanics in `eval/run_eval.py`, the CI workflows, the
  hexagon wiring in `config.py`, and the demo surface's plumbing in `scripts/`.
- **Adopter-owned** (yours; expect to edit): the two prime surfaces below, plus the *values* in
  `config/settings.yaml`, the seeded warehouse and catalog fixtures in `adapters/local/`,
  `adapters/onprem/*`, `tests/fixtures/sample_cases.py`, the golden eval dataset, the UI theming,
  and the jurisdiction rows in `COMPLIANCE.md`.

Two surfaces deserve naming, because they are where an adopter's own policy actually lives and
neither requires an engine edit:

- **The rule packs.** `config/rulepacks/*.yaml` are DATA, not code. The three bundled packs
  (`customer_master.yaml`, `transactions_daily.yaml`, `marketing_events.yaml`) are fictional
  reference packs. Each declares a `dataset_id`, an `owner`, an `sla_hours` and a list of rules,
  and each rule names an `id`, a `rule_type` (one of `completeness`, `uniqueness`, `validity`,
  `referential_integrity`, `timeliness`), a `column`, a `severity`, an `owner`, a `description`
  and a `params` mapping. `domain/rulepack_loader.py` parses them fail-closed: an unknown
  `rule_type` or `severity`, or a rule missing its `id` or `column`, raises `RulePackError` AT
  LOAD rather than silently running a subset of what the pack's owner configured. Write your own
  packs; do not add rule families to the engine until you have run out of the five.
- **The thresholds.** `domain/thresholds.py` carries the two certification bands
  (`CERT_MIN_PASS_RATIO = 0.98`, `CONDITIONAL_MIN_PASS_RATIO = 0.90`), the borderline margin
  (`BORDERLINE_MARGIN = 0.02`) and the `h4-data-quality` metric bundle the eval gate scores
  against. `threshold_for` RAISES on an unknown metric name rather than clearing a 0.0 bar, which
  is the fix for the silent-pass trap; keep that property when you edit the table.

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites five identifiers across the tree in one simultaneous pass: the
python package (`data_quality_governance`), the console-script name (which in this repo IS
the package name, see `[project.scripts]` in `pyproject.toml`), the `DATAQUALITY` env-var prefix,
the Terraform `name_prefix` stem (`h4-svc`) and the distribution / git id
(`data-quality-governance`). Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_dq --cli acme-dq \
    --env-prefix ACME --resource acme-dq --dry-run

# Apply, sweeping Markdown prose as well:
python scripts/rename_fork.py --package acme_dq --cli acme-dq \
    --env-prefix ACME --resource acme-dq --include-docs --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
make install
make gate
```

`--dist` defaults to the package name with underscores turned into hyphens (`acme-dq` above); pass
it explicitly if your git id follows a different convention. `--resource` is validated against the
same `^[a-z][a-z0-9-]{2,18}$` pattern the Terraform `name_prefix` variable enforces at plan time,
so a bad value fails here rather than three minutes into an apply. Without `--include-docs` the
sweep leaves `.md` files alone, which is useful for a first pass over code only.

Two things the script deliberately leaves behind, because neither is mechanical: the catalog id
`H4` (in `infra/terraform/render.tf.json` and every document title), and the human decisions
below.

## 4. The human decisions (the script cannot make these)

1. **Region and residency.** The build is pinned to `asia-southeast1` (MAS and Singapore). The
   region is chosen once and shared: `config/settings.yaml` reads it from `GCP_REGION`, and in
   tfvars you set BOTH `var.region` and `var.allowed_regions`, the residency allowlist the region
   is validated against at `terraform plan`. Change all of them together, and re-read
   [`runbook.md`](runbook.md) before you do.
2. **Identity and the IdP.** This repo owns no login flow. `local` resolves a seeded dev persona
   from `X-Dev-Persona` and refuses to construct unless `local` was chosen deliberately; `gcp`
   verifies the Cloud IAP-injected assertion against the configured `DATAQUALITY_IAP_AUDIENCE`
   (three-state: unset or emptied REFUSES, because an unverified audience accepts any
   Google-signed token); `onprem` is a client-IdP placeholder that RAISES. Wire your issuer on the
   deployed service and set the audience. The browser boundary is described in
   [`../ui/README.md`](../ui/README.md).
3. **The DQ thresholds and the drift bands.** These are the numbers your CDO office owns, and the
   shipped values are a reference rather than your policy:
   - certification: `CERT_MIN_PASS_RATIO = 0.98` and `CONDITIONAL_MIN_PASS_RATIO = 0.90` in
     `domain/thresholds.py`, applied on top of the fail-closed gates in
     `domain/scorecard_service.py` (any failing HIGH or CRITICAL check, a freshness breach at HIGH
     or above, or breaking drift forces UNCERTIFIED regardless of the ratio);
   - drift: the fixed ladder in `domain/drift_service.py`, `removed` and `retyped` HIGH, `renamed`
     MEDIUM, `added` LOW, plus the deliberately conservative rename heuristic that only pairs a
     removed and an added column when exactly one of each shares a data type;
   - freshness: the ladder in `domain/freshness_service.py`, a breach past the pack's `sla_hours`
     is HIGH and a breach past twice it is CRITICAL, scored against a caller-supplied `as_of` so a
     run replays;
   - PII: the `PiiClassifier` dataclass fields (`pii_threshold = 0.6`, `review_threshold = 0.3`,
     `strong_pattern_ratio = 0.6`, `adjudicator_nudge = 0.15`) and the `jurisdictions` tuple, which
     defaults to `("SG", "HK", "JP", "AU")` in both `domain/pii_classifier.py` and `domain/pii.py`.
     Set the jurisdictions you actually serve: they select which national-ID recognizers from the
     shared `pii-kit` both the classifier and the redactor use.

   These are module-level constants and dataclass fields today rather than a `policy:` block in
   `config/settings.yaml`; check B4 in [`practices-audit.md`](practices-audit.md) tracks that gap.
   Change them deliberately and add a test that pins your values.
4. **Reference data is fictional.** The seeded warehouse (`adapters/local/warehouse.py`) ships
   three invented datasets with planted defects, the catalog adapter ships invented lineage edges,
   and `tests/fixtures/sample_cases.py` and `eval/datasets/golden_cases.jsonl` are synthetic
   throughout: `.example` domains, RFC 5737 and RFC 3849 literals, plainly invented names. Replace
   them with your own synthetic data. **Do not run against real production tables without your own
   security, privacy and model-risk sign-off.**
5. **The eval golden set.** Rebuild `eval/datasets/golden_cases.jsonl` for your rule packs and your
   datasets. A fork inherits a green gate that measures the WRONG control set until you do. The
   gate structure and the strict `review_safety >= 0.99` and `narrative_groundedness >= 0.99` bars
   are generic; the golden cases and their `expected_*` labels are yours. Every metric scores
   against the dataset's own expected outcome, never against the pipeline's verdict, and the
   harness proves each metric can go RED before it trusts a report. Keep both properties.
6. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root uid 10001,
   `HEALTHCHECK` on `/healthz`) and `infra/terraform/` before you expose anything: the
   `gcp.resourceLocations` Org Policy allowlist and the service-account-key ban in `org_policy.tf`,
   the regional CMEK ring in `kms.tf`, the dry-run-first VPC-SC perimeter in `vpc_sc.tf`, the
   locked WORM log bucket in `logging_worm.tf`, and the internal-load-balancer-only ingress in
   `production_edge.tf`. Note that `var.enable_org_policies`, `var.enable_vpc_sc` and
   `var.vpc_sc_enforce` are toggles: a stack applied with them off is not a compliant one. The
   exit path is [`onprem-migration.md`](onprem-migration.md).

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it *touches* are
owned by sibling platform services, and you should integrate rather than rebuild them (see
[`faq/features-faq.md`](faq/features-faq.md) for the full boundary map). Be precise about which
are actually wired here today:

**Wired, through a bound port:**

- `human-review-console` human-review and maker-checker console: every escalation is ROUTED, not merely flagged,
  through `ReviewRouterPort` and the shared `review-kit` (rule R8). The offline family
  enqueues to an inspectable outbox, the managed family submits over S2S to `HUMAN_REVIEW_URL`
  and REFUSES when no console is configured, and the on-premises family raises. You wire your
  endpoint; you do not re-implement the console.
- `model-quality-gate`: `EvaluationGatePort` is bound in all three families.
  `eval/run_eval.py --mode gate` delegates the promotion verdict to `model-quality-gate` and refuses to run off
  the managed profile; the local adapter scores offline but refuses to promote.
- `agent-observability`: `ObservabilityTracerPort` is bound in all three families, and the managed
  tracer exports OTLP to the `agent-observability` collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and straight
  to Cloud Trace when it is not.

**Scaffolded but not yet registered:**

- `agent-registry`: the A2A card is built from the same tool table the runtime binds and
  served at `/.well-known/agent-card.json`, but nothing registers it with `agent-registry` and the agent's
  identity and entitlements are not taken from it. Rule R4 in `COMPLIANCE.md` names this openly.

**Honestly NOT integrated today:**

- `agent-guardrail-gateway`: there is no `GuardrailPort` in `ports/`. Redaction happens locally
  with the shared `pii-kit` before the audit write and before any outbound payload, which is not
  the same thing as injection defence and output filtering. Rule R1 stays Partial until a
  guardrail port exists, and it becomes mandatory the moment untrusted text reaches a model.
- `enterprise-knowledge-base` governed knowledge base: there is no retrieval port and nothing to ground, so P-05 and
  rule R3 are honestly open rather than claimed.
- `marketing-compliance-gate` marketing compliance: not applicable. This service produces no customer-facing output.
- `architecture-validator` architecture and requirements validator: an intake action, not a code control. Record
  your validation reference in `COMPLIANCE.md` when the project passes it.

**Downstream, not a dependency:** H4 hands its per-dataset certification verdict to **H1** (the
NL-to-SQL governed semantic analyst) as DATA over the narrow `CertificationResponse` wire, pinned
by `tests/contract/test_certification_wire.py`. H1 never imports H4. If you change that field set,
you have made a breaking cross-system change.

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make install` and `make gate` green.
- [ ] Set the region in `config/settings.yaml` and BOTH `var.region` and `var.allowed_regions` in tfvars.
- [ ] Wired your IdP on the deployed service and set `DATAQUALITY_IAP_AUDIENCE` (this repo owns no login flow).
- [ ] Replaced `config/rulepacks/*.yaml` with your own datasets, rules, owners and SLAs.
- [ ] Owned the certification bands, the drift and freshness ladders and the PII thresholds with your CDO office, and pinned them in a test.
- [ ] Set the `jurisdictions` tuple in `domain/pii.py` and `domain/pii_classifier.py` to the jurisdictions you actually serve.
- [ ] Replaced the seeded warehouse, the catalog lineage edges and every synthetic fixture.
- [ ] Rebuilt `eval/datasets/golden_cases.jsonl` and its `expected_*` labels for your control set.
- [ ] Reviewed the deploy posture (Dockerfile, Terraform toggles, bind address) and set a durable `DATAQUALITY_AUDIT_PATH` with a `DATAQUALITY_AUDIT_ANCHOR` on a different volume.
- [ ] Wired your `human-review-console` review endpoint and decided which other sibling services you integrate vs leave open.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
