# Adoption FAQ

For an engineering lead forking this repo as their institution's data-certification base. The
step-by-step is [`../ADOPTING.md`](../ADOPTING.md); this answers the "will it hurt later?"
questions. Cross-references: [`CONTRIBUTING.md`](../../CONTRIBUTING.md),
[`practices-audit.md`](../practices-audit.md).

### How do I rebrand it for my organisation?

`scripts/rename_fork.py` rewrites five identifiers in one simultaneous pass: the python package
(`data_quality_governance`), the console-script name (which in this repo IS the package name,
see `[project.scripts]`), the `DATAQUALITY` env prefix, the Terraform `name_prefix` stem
(`h4-svc`), and the distribution and git id (`data-quality-governance`). Preview with
`--dry-run`, apply with `--yes`, add `--include-docs` to sweep Markdown too. Then recreate the venv
(the distribution name changed), `make install`, and `make gate`.

The pass is simultaneous rather than sequential on purpose: because the CLI name and the package
name are the same token upstream, a sequential search and replace would rename the command twice.
The script leaves the catalog id `H4` and every human decision alone.

### If several institutions fork this, how does each take upstream fixes?

Track upstream via git tags. The repo declares a core-vs-adopter-owned boundary
([`../ADOPTING.md`](../ADOPTING.md) section 2): upstream owns `domain/kernel.py`,
`domain/errors.py`, `ports/`, `tests/contract/`, the eval harness mechanics and the hexagon wiring
in `config.py`; you own the rule packs, the threshold values, `config/settings.yaml` values, the
seeded fixtures, `adapters/onprem/*`, the UI theming and the eval golden set. Rebase your
adopter-owned changes onto each release rather than merging `main` continuously, so conflicts stay
in files you were told to expect.

### Is there a separate kernel module I keep untouched?

Yes, and the direction is enforced. `domain/kernel.py` holds the vertical-neutral machinery
(`Severity`, `Decision`, `Citation`, `AuditEvent`, `utcnow`) and `domain/models.py` imports it,
never the reverse. A fork building a different governance vertical rewrites `models.py` and the
engines and leaves `kernel.py` alone. Practices-audit check A7 records this as a PASS.

### How do I change the checks without touching the engine?

Edit `config/rulepacks/*.yaml`. A pack is data: a `dataset_id`, an `owner`, an `sla_hours` and a
list of rules, each naming an id, a `rule_type` from the five families (`completeness`,
`uniqueness`, `validity`, `referential_integrity`, `timeliness`), a column, a severity, an owner, a
description and a `params` mapping. `domain/rulepack_loader.py` refuses an unknown rule type or
severity AT LOAD rather than skipping the check at scoring time, so a pack the engine cannot fully
understand fails loudly. Only reach for a sixth rule family after you have genuinely run out of
five.

### Can I retune the thresholds without touching code?

Not yet as configuration, and that is called out honestly. The certification bands
(`CERT_MIN_PASS_RATIO = 0.98`, `CONDITIONAL_MIN_PASS_RATIO = 0.90`), the borderline margin and the
`h4-data-quality` eval bundle are module constants in `domain/thresholds.py`; the PII thresholds are
dataclass FIELDS on `PiiClassifier` (`pii_threshold`, `review_threshold`, `strong_pattern_ratio`,
`adjudicator_nudge`), so they can at least be overridden at construction; the drift and freshness
severity ladders are module-level tables in their engines. There is no `policy:` block in
`config/settings.yaml` threading these values in, which is the open B4 item in
[`practices-audit.md`](../practices-audit.md). If your CDO office must own these numbers as
configuration rather than as a code change, plan that small addition as part of adoption, and pin
your values with a test either way.

### How do I add a new outbound dependency (a new port)?

There is a fixed touch list and the contract test enforces it, because four of the five homes can
be satisfied while the fifth is missing and the result is a port with zero enforcement and a green
build. The five: the Protocol in `ports/<port>.py`, the `PORT_PROTOCOLS` entry and `__all__` in
`ports/__init__.py`, an entry in `config.DEFAULT_BINDINGS` plus a `Container` accessor, the same
three bindings under `adapters.<port>` in `config/settings.yaml`, and a `PortCase` in
`tests/contract/canonical.py`. Then three adapters: `local` WORKS offline, `gcp` imports its SDK
lazily, `onprem` RAISES a subclass carrying a status and a reason.
`tests/contract/test_port_parity.py` asserts set equality across all five.
[`CONTRIBUTING.md`](../../CONTRIBUTING.md) has the full ten-row table including the surfaces, the
agent card and the docs.

### How do I add a new deterministic engine?

Same shape, with two additions that are not negotiable: the consequential decision stays pure
stdlib and replayable (a model may narrate it, never produce it), and every consequential result
escalates through `ReviewRouterPort` rather than terminating in a boolean. Put the engine in
`domain/<name>_service.py` with no I/O, sequence it from `domain/certification_service.py`, and
unit-test it against the real local adapters.

### What happens if I want to add a model?

Read [`../model-card.md`](../model-card.md) first. There is no generation port today, and the card
lists what must be true before there is one: the port registered in all five places, a pinned model
id, budget and rate limits with a kill switch, an eval that scores the LIVE model rather than the
deterministic pipeline, and prompt-injection screening through the Hrz1 guardrail. The boundary
does not move: a model may narrate, summarise or draft remediation prose, and may never produce a
rule verdict, a drift figure, a PII classification or a certification decision.

### Will the demo rot after I diverge?

It is guarded, and the guard runs inside the gate. A demo step exists in exactly two places,
`demo.STEPS` and `walkthrough.CHECKS`, and `tests/unit/test_demo_surface.py` holds the two sets
equal and then drives the whole arc against the real local adapters, applying the walkthrough's own
expectations at each step. So a claim the demo makes that nobody verifies cannot exist, and a step
that stops being true fails `make gate` rather than a meeting. `make demo-selftest` runs the same
arc headless in its own required CI check. Keep both halves when you add a step, and put the
numbers a check reads in the step's `facts` dict rather than only in the rendered rows: a check
that parses prose breaks on a wording change.

That same test is also why every `scripts/*.py` must appear in `scripts/README.md` wrapped in
backticks; add the row in the same commit as the script.

### Does the offline gate run for my fork out of the box?

Yes. `make gate` is `ruff check` plus `ruff format --check` plus `mypy src` plus
`pytest -m 'not integration'` plus the offline eval, and it needs no network, no cloud SDK, no
project and no credentials. The workflows reference no org secrets. `make audit` (pip-audit over
both lockfiles) is separate precisely because it is the one step that needs a vulnerability feed.
Note that the eval measures the REFERENCE rule packs and golden cases until you rebuild them for
your own datasets: that is an explicit adoption step, not a silent pass.

### What is honestly unfinished in this base?

The managed profile is not production-cleared: `managed_readiness.py` names the managed warehouse,
catalog and baseline-store operations that are still construction-only, and the API preflight
refuses to start on a managed profile while any of them is selected. Beyond that, the open control
rows are listed in [features-faq.md](features-faq.md) and, in control language, in
[`COMPLIANCE.md`](../../COMPLIANCE.md). Fork with your eyes open on those rather than discovering
them at a second-line review.
