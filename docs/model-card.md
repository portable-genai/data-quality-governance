# Model card: Data Quality and Governance Agent (H4)

**This system has no model in its path.** No generation, narration, drafting or LLM port is bound
in any profile today, so there is no model-attributable output to characterise. This card records
that boundary, and the conditions a model would have to meet before it could be added.

## The evidence that there is no model

`ports/` declares seven modules and eight named ports: `audit`, `identity`, `review_router`,
`warehouse`, `catalog`, `baseline_store`, `tracer` and `evaluation` (the last two both live in
`ports/observability.py`). None of them is a generation port. `config.DEFAULT_BINDINGS` and
`config/settings.yaml` bind exactly those eight in each of the three families, and
`tests/contract/test_port_parity.py` asserts set equality across all five homes of the port set,
so an unregistered generation port could not run unnoticed. There is no generation adapter under
`adapters/local/`, `adapters/gcp/` or `adapters/onprem/`.

One constant can mislead a reader on a grep: `_GATED_MODEL = "gemini-3.5-flash"` in
`adapters/gcp/evaluation.py`. That is the model identifier the `model-quality-gate` promotion verdict is RECORDED
AGAINST, so a future model swap invalidates an old verdict rather than inheriting it. Nothing in
this repo calls that model, or any model.

## Every consequential output is a deterministic stdlib engine

The scorecard, and every figure on it, is computed by pure-stdlib code in `domain/` that replays
byte-for-byte from the same inputs:

| Output | Produced by |
|---|---|
| Column statistics, null and cardinality ratios, inferred types | `domain/profile_service.py` |
| Per-rule pass or fail verdicts and their sampled evidence | `domain/dq_rule_engine.py` |
| Freshness age and its severity against the pack's SLA | `domain/freshness_service.py` |
| Schema-drift findings and their severity ladder | `domain/drift_service.py` |
| Per-column PII category, score and signal breakdown | `domain/pii_classifier.py` |
| Remediation tickets and downstream lineage impact | `domain/remediation_service.py` |
| The certification verdict, pass ratio and `requires_human_review` | `domain/scorecard_service.py` |
| Orchestration, the audit write and the tenant-scoped store | `domain/certification_service.py` |

**`domain/pii_classifier.py` is not a machine-learning classifier.** The word classifier is
load-bearing here, so read the module: it is rule and pattern based. It sums three explainable
signal families into a score an auditor recomputes by hand: a column-name synonym table
(`_NAME_RULES`, a fixed tuple of token lists with fixed weights), the fraction of sampled values
matching the shared `pii-kit` regular expressions and validators, and cardinality and inferred-type
shape signals. The thresholds are dataclass fields on `PiiClassifier`. There is no model, no
training data, no inference call and no learned parameter anywhere in it. `domain/pii.py` is a
separate and smaller thing: it only selects and ORDERS the `pii-kit` rows this deployment redacts
with, national-ID rows first and the universal email and phone rows last.

The `narrative` field on a `DatasetScorecard` is also deterministic. `scorecard_service.narrate`
assembles one paragraph out of counts the engines already produced, so it is grounded by
construction. It is the seam a drafting model would later occupy, which is precisely why it is
written to state nothing the engine did not compute.

## The boundary a model would have to respect

If a generation port is added later, it may **narrate, summarise or draft remediation prose, and
nothing else**. Specifically it may never:

- produce a rule verdict, a pass ratio or a piece of sampled evidence;
- produce a freshness age, a drift finding or any severity;
- produce a PII category, score or signal;
- produce a certification status, or decide `requires_human_review`.

And the surrounding controls do not move:

- **Redaction happens before the model call, not after.** PII is masked before the audit write and
  before any outbound payload today; a model call is another boundary and takes the same treatment.
- **Every output stays cited.** A drafted paragraph that states a figure must be grounded against
  the engine output and DISCARDED on failure, never repaired.
- **Escalation still routes to `human-review-console` under rule R8.** Setting `requires_human_review` and calling
  `ReviewRouterPort.route` remains one act, in the same request that produced the result.

## Controls that must exist BEFORE a model is introduced

- **A generation port registered in the five places `CONTRIBUTING.md` names**: the Protocol in
  `ports/`, the `PORT_PROTOCOLS` entry in `ports/__init__.py`, `config.DEFAULT_BINDINGS` plus a
  `Container` accessor, the `adapters:` block in `config/settings.yaml`, and a `PortCase` in
  `tests/contract/canonical.py`; then an adapter in all three families, the `onprem` one raising.
- **A pinned model id, recorded in this card** together with its prompt version, alongside the
  `_GATED_MODEL` constant the `model-quality-gate` verdict is keyed to.
- **Budget and rate limits and a kill switch**: a per-tenant token budget, a request rate limit,
  and a switch that forces deterministic-only operation with the model disabled (P-10, P-11).
- **An eval that scores the LIVE model.** Today `eval/run_eval.py --mode smoke` scores the
  deterministic pipeline, including `narrative_groundedness` against a narrative that is grounded
  by construction. That metric only becomes meaningful once a real model writes the text, so a
  managed-profile run through the `model-quality-gate` must score the model's own groundedness before
  promotion.
- **Prompt-injection screening through the `agent-guardrail-gateway`**, failing closed to deterministic-only
  when the screen is unavailable. Rule R1 in `COMPLIANCE.md` stays Partial until that port exists.

## Status

The system is model-free today, so this card records a boundary rather than a model. It is safe to
run offline on the deterministic engines alone; nothing here is a claim about a managed model path,
because there is not one.
