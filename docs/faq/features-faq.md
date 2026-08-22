# Features FAQ

For product, data-governance and delivery teams: what this agent produces, what is deterministic
versus what a model does (today: nothing), and where its responsibilities **stop** and a sibling
catalog system takes over. Cross-references: [`README.md`](../../README.md),
[`DEMO.md`](../../DEMO.md), [`ARCHITECTURE.md`](../../ARCHITECTURE.md),
[`model-card.md`](../model-card.md).

### What does H4 actually produce?

A cited **dataset scorecard** with a **certification verdict**. Given a dataset id it profiles the
dataset, runs every check its rule pack configures, and folds the results into one
`DatasetScorecard` carrying: the per-rule DQ findings with the sampled evidence rows behind each,
a freshness result against the pack's declared SLA, the schema-drift findings against the stored
baseline, a per-column PII classification with its signal breakdown, deterministically assembled
remediation tickets, the downstream lineage the verdict touches, and a status of `certified`,
`conditionally_certified` or `uncertified`. Every figure carries a `Citation`, and the whole thing
is written to a hash-chained, externally anchored audit trail.

The narrow slice a downstream consumer reads is `CertificationResponse` (dataset id, status,
certified metrics, `as_of`, pass ratio, tenant, citations), served at
`GET /v1/certification/{dataset_id}`.

### What is deterministic, and what does the LLM do?

Everything consequential is deterministic, and the LLM does **nothing**, because there is no LLM.
There is no generation, narration or drafting port bound in any profile: see
[`model-card.md`](../model-card.md) for the evidence and for the boundary a later model would have
to respect. The engines are pure stdlib and replay byte-for-byte:

| Output | Engine |
|---|---|
| Column statistics, null and cardinality ratios, inferred type | `domain/profile_service.py` |
| Per-rule verdicts plus the sampled evidence | `domain/dq_rule_engine.py` |
| Freshness age and severity against the SLA | `domain/freshness_service.py` |
| Schema drift, on a fixed severity ladder | `domain/drift_service.py` |
| PII category, score and explainable signals | `domain/pii_classifier.py` |
| Remediation tickets and lineage impact | `domain/remediation_service.py` |
| The certification verdict and the review decision | `domain/scorecard_service.py` |

Even the scorecard's one-paragraph `narrative` is deterministic: `scorecard_service.narrate`
restates counts the engines produced, which is grounded by construction and is the seam a drafting
model would later occupy.

### How are the data-quality checks configured?

As DATA, never as code. `config/rulepacks/*.yaml` declares one pack per dataset with an owner, an
`sla_hours` and a list of rules; each rule names an id, a `rule_type` (`completeness`,
`uniqueness`, `validity`, `referential_integrity` or `timeliness`), a column, a severity, an owner
and its parameters. `domain/rulepack_loader.py` parses a pack fail-closed: an unknown rule type or
severity, or a rule with no id or column, raises `RulePackError` AT LOAD. A check whose column is
absent from the dataset is a FAILING finding, not a skipped one, because a control that could not
run has not passed.

### What is the difference between `domain/pii.py` and `domain/pii_classifier.py`?

They do different jobs and it matters:

- **`domain/pii.py` is the redactor's pattern set.** It selects and ORDERS rows from the shared
  `pii-kit` for the jurisdictions this deployment serves (`("SG", "HK", "JP", "AU")` by default),
  national-ID rows first and the universal email and phone rows last. It is what masks values
  before the audit write and before any outbound review payload.
- **`domain/pii_classifier.py` is the column classifier.** It decides whether a COLUMN is
  `pii_direct`, `pii_quasi`, `sensitive` or `non_pii`, from three explainable signal families:
  a column-name synonym table, the fraction of sampled values matching the same `pii-kit`
  recognizers, and cardinality and type shape signals. It is rule and pattern based, not a model.

One PII definition, two uses: the classifier and the redactor read the same recognizers.

### Is anything auto-approved?

No consequential outcome is. Two outcomes set `requires_human_review` and are ROUTED to the Hrz7
console in the same request that produced them (rule R8): **decertifying** a dataset that was
previously certified, and **any sensitive-category PII finding**. Routing is one act with setting
the flag, on the API, the CLI and the agent tool alike; the managed router REFUSES when no console
is configured rather than swallowing the escalation, and the on-premises one raises.

### Which capabilities does this repo own vs integrate from the catalog?

It **owns** the data-governance domain logic and its outputs. It **integrates**, or is scheduled to
integrate, several cross-cutting concerns owned by sibling systems. Do not rebuild these in a fork,
and note honestly which are wired today:

| Concern | Owned by | H4's position today |
|---|---|---|
| Human review and maker-checker console | **Hrz7** `human-review-console` | WIRED. `ReviewRouterPort` in all three families over the shared `review-kit` (rule R8) |
| AI-quality, eval and promotion gate | **Hrz4** `model-quality-gate` | WIRED as a client. `eval/run_eval.py --mode gate` delegates the verdict and refuses off the managed profile; the bundle is not yet registered with Hrz4 |
| Observability, tracing and the WORM audit sink | **Hrz5** `agent-observability` | PARTLY WIRED. The tracer exports OTLP to the Hrz5 collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; the audit half is the local anchored chain or a locked Cloud Logging bucket |
| Agent registry, versioning, entitlements | **Hrz3** `agent-registry` | SCAFFOLDED ONLY. The A2A card is served at `/.well-known/agent-card.json`; nothing registers it |
| Runtime guardrail: injection defence, output filtering | **Hrz1** `agent-guardrail-gateway` | NOT WIRED. There is no `GuardrailPort`. It becomes mandatory the moment untrusted text reaches a model |
| Governed knowledge base with citations | **Hrz2** `enterprise-knowledge-base` | NOT WIRED, and not needed: there is no retrieval step to ground |

The `COMPLIANCE.md` R1 to R8 rows say the same thing in control language, and each open one names
what must be added.

### Who consumes H4's output?

**H1**, the NL-to-SQL governed semantic analyst, reads the certification verdict as DATA over the
`CertificationResponse` wire and never imports this repo. That contract is pinned by
`tests/contract/test_certification_wire.py`, so changing the field set is a deliberate breaking
cross-system change rather than an accident.

### How do I see it working?

`make demo` runs the presenter-paced walkthrough: it starts its own loopback server, narrates each
of the eight steps on your terminal, and after each one asserts that the real service reached the
state the narration claimed. `make demo-selftest` is the same arc headless and unattended,
`make demo-static` writes the audit-first HTML panels for screenshots, and `make portability` runs
the executable portability claim. Everything is offline, SDK-free and stdlib-only over synthetic,
obviously fictional data. See [`DEMO.md`](../../DEMO.md).

### What is NOT built yet?

Read `COMPLIANCE.md` and [`practices-audit.md`](../practices-audit.md) rather than trusting a
summary, but the honest headline: no guardrail port (R1), no retrieval or grounding (P-05, R3),
no Hrz3 registration (R4), no registered Hrz4 metric bundle (P-08, R5), no timeouts, circuit
breaker or documented kill switch per outbound dependency (P-10), no cost or latency controls
because there is nothing to route or cache yet (P-11), no Rsk3 intake reference (R6), and no
object-level authorisation from data tags because there is no queryable store to authorise against
yet. The policy numbers are also still module constants rather than a `policy:` block in
`config/settings.yaml` (check B4).
