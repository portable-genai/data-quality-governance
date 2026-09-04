# FAQ index

Answers to the questions different teams ask when evaluating, adopting, or reviewing this
repository as a common base for a data-quality and data-governance certification agent (H4). Each
file is written for a specific audience; skim the one that matches your role.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec and security review | server-side identity, the two distinct PII surfaces, secrets, supply chain, the anchored audit chain, what is in scope and what is not |
| [portability-faq.md](portability-faq.md) | Architecture, cloud and exit planning | the no-lock-in claim, the eight ports and three profiles, the on-premises exit, open-format export |
| [features-faq.md](features-faq.md) | Product, data governance and delivery | what the agent produces, what is deterministic (all of it today), and the boundary with sibling catalog systems |
| [adoption-faq.md](adoption-faq.md) | Engineering leads forking the repo | rebranding, taking upstream fixes, rule packs, extension points, what is honestly unfinished |
| [compliance-faq.md](compliance-faq.md) | Compliance, data governance and model risk | regulatory posture, maker-checker, residency enforcement, the audit trail, model-risk evidence for a model-free system |

These FAQs deliberately do **not** re-document capabilities owned by sibling systems in the GRC
GenAI catalog. Where a concern belongs to another repo (the guardrail gateway `agent-guardrail-gateway`, the governed
knowledge base `enterprise-knowledge-base`, the agent registry `agent-registry`, the AI-quality gate `model-quality-gate`, observability and the WORM
audit sink `agent-observability`, the human-review console `human-review-console`), the FAQ names the owner and explains the boundary
rather than duplicating it. See [features-faq.md](features-faq.md) for the full "what this repo
owns vs what it integrates" map, and be aware that several of those integrations are honestly not
wired yet: the same file says which.
