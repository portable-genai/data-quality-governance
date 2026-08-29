# Security FAQ

For an AppSec reviewer sizing up this repo. It explains what the attack surface is, what is
deliberately out of scope (and why that is honest rather than a gap), and where the evidence
lives. Cross-references: [`COMPLIANCE.md`](../../COMPLIANCE.md),
[`practices-audit.md`](../practices-audit.md), [`ARCHITECTURE.md`](../../ARCHITECTURE.md).

## What does this system actually process?

Dataset METADATA and bounded column SAMPLES, never a full table. `WarehousePort` exposes three
operations: the table metadata (row count, load and partition timestamps, the live schema), the
live schema, and a bounded sample of column values as text. The engine never issues a query. Those
samples can and do contain personal data, which is why the redaction and classification controls
below are load-bearing rather than decorative.

## How is identity handled? Can a caller spoof the actor?

No. Identity is resolved server-side on every route, and the client-asserted actor is discarded.
The request schemas carry no `actor` field; the audit actor and the review maker are both the
verified `Principal`. Three families:

- `local` resolves a seeded dev persona from `X-Dev-Persona`, and the adapter REFUSES to construct
  unless the `local` profile was chosen deliberately;
- `gcp` verifies the Cloud IAP-injected assertion, and it EARNS the word verified:
  `id_token.verify_token` is called with the configured `DATAQUALITY_IAP_AUDIENCE` (three-state:
  unset or emptied refuses, because an unverified audience accepts any Google-signed token from
  any project) and with IAP's own key set rather than google-auth's OAuth2 default, and the issuer
  is checked here because `verify_token` does not check it;
- `onprem` raises, carrying a status and a reason rather than a bare `NotImplementedError`.

`tests/unit/test_iap_identity.py` runs in every `make gate`; `tests/unit/test_iap_crypto_matrix.py`
runs the real verifier over locally minted assertions in a CI job that fails if it skips.

## Why is the exposure guard derived from the identity binding rather than a profile string?

Because the alternative was a real defect. `add_loopback_exposure_guard` is bound at MODULE scope
in `api/app.py` (the Dockerfile `CMD` and `make run-api` serve the app OBJECT, so a bind that lives
only in `main()` never runs in a shipped process), and its posture comes from what the bound
identity adapter DECLARES about end-user authentication: `VERIFIED`, `CLIENT_ASSERTED` or
`UNIMPLEMENTED`, defaulting to client-asserted when silent. `DATAQUALITY_S2S_TOKEN` may never enter
that decision: it authenticates a calling SERVICE and no end user, and while it did, SETTING it
switched the guard off for the end-user routes it was protecting.
`tests/unit/test_serving_path_exposure.py` and `tests/unit/test_end_user_auth_posture.py` are the
standing gates.

## There are two PII modules. Which does what?

Both matter and they are not interchangeable.

- **`domain/pii.py` redacts.** It selects and ORDERS the shared `pii-kit` recognizers for the
  jurisdictions this deployment serves, national-ID rows first so a universal catch-all cannot
  subsume one. It masks before the audit write and before any outbound payload.
- **`domain/pii_classifier.py` classifies columns.** It labels a column `pii_direct`, `pii_quasi`,
  `sensitive` or `non_pii` from a name-synonym table, the fraction of sampled values matching the
  same `pii-kit` recognizers, and cardinality and type shape signals. It is rule and pattern
  based, with no model and no learned parameter, and every contributing signal is returned with the
  classification so an auditor can recompute the score.

Redaction runs before both boundaries that leave the process: `adapters/_review_payload.py` redacts
against EVERY jurisdiction's rows before the review goes to Hrz7, because the console is a shared
sink, and `agent/tools.py` masks a tool result before it can become model context.
`tests/unit/test_not_falsely_green.py` proves the safety metric can actually go red.

## Is the audit trail tamper-evident?

Yes, within stated limits, and it is anchored rather than merely chained. The local sink is an
append-only hash-chained WORM log from the commons, AND every append writes the chain head to an
external anchor file (`DATAQUALITY_AUDIT_ANCHOR`) that should live on a different volume under
different credentials. The chain alone catches an edit, a deletion or a reorder; only the anchor
catches a TRUNCATED TAIL, because a truncated chain still verifies perfectly on its own.
`tests/unit/test_audit_anchor.py` proves the detection, proves the control case goes UNDETECTED
without an anchor, and proves an append after a truncation refuses rather than silently
re-anchoring. In the managed profile the sink is a locked Cloud Logging bucket
(`infra/terraform/logging_worm.tf`), which provides non-rewritability itself.

## What about outbound service-to-service calls?

Two. The Hrz7 review submission goes over the shared `review-kit`, which refuses a plaintext
non-loopback URL and a missing bearer at construction; the credentials are `HUMAN_REVIEW_S2S_TOKEN` and
`HUMAN_REVIEW_S2S_SIGNING_KEY`, deliberately DISTINCT variables from this service's own inbound
`DATAQUALITY_S2S_TOKEN`. The Hrz4 promotion call in `adapters/gcp/evaluation.py` uses the shared
`agent-eval-kit` client and refuses to run off the managed profile.

## Are there secrets in the repo?

No literal secret material. `config/settings.yaml` and `.env.example` carry variable NAMES and
non-secret defaults only, resolved as `${VAR}` or `${VAR:-default}` in three states;
`.env.secrets.example` carries placeholders; `.gitignore` excludes the real files. Check C10 in the
practices audit.

## What is the supply-chain posture?

Committed `requirements-dev.lock` and `requirements-gcp.lock`, installed with `--no-deps` by
`make install`, by CI and by the Dockerfile, with the catalog commons pinned to 40-character COMMIT
shas rather than tags (a tag can be moved, so a tag pin lets what installs change with no diff); a
digest-pinned non-root base image; SHA-pinned GitHub Actions; dependabot per ecosystem; and
`pip-audit` over both lockfiles as a HARD CI failure. `tests/unit/test_repo_artifacts.py` asserts
each of these from inside the repo, offline.

## Why is there no guardrail or injection defence?

Because there is no model to defend, and claiming the control before it exists would be worse than
owing it. There is no `GuardrailPort` in `ports/` and no generation adapter in any family (see
[`model-card.md`](../model-card.md)). Rule R1 in `COMPLIANCE.md` is Partial for exactly this reason
and names what must be added: bind a `GuardrailPort` to the Hrz1 gateway for injection defence and
output filtering as soon as untrusted text reaches a model.

## What is explicitly out of scope for this repo?

The guardrail and prompt-injection engine (**Hrz1**), the governed knowledge base (**Hrz2**), the
agent registry (**Hrz3**), the AI-quality and promotion gate (**Hrz4**), the enterprise WORM audit
and trace sink (**Hrz5**), and the human-review console (**Hrz7**). This repo integrates the ones
it has wired through thin adapters rather than re-implementing them; see
[features-faq.md](features-faq.md) for which are wired today and which are not. Also out of scope
by design: a login flow (the platform in front authenticates), and object-level authorisation from
data tags, which has no queryable store to apply to yet (check C2).
