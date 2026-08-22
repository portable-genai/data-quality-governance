"""Explainable PII classification of structured columns (pure stdlib + pii-kit).

Three signal families summed into a score an auditor can recompute, mirroring the design of the
on-prem DLP column classifier (which deliberately consumes no commons; this one does, so the
patterns come from ``pii-kit`` rather than being copied):

1. name signals    - the column name against a synonym dictionary;
2. pattern signals - the fraction of sampled values matching the SAME ``pii-kit`` recognizers
   the redactor and the leak-check use (one PII definition across the whole service);
3. shape signals   - cardinality and inferred type, separating direct identifiers (near-unique)
   from quasi-identifiers (low-cardinality demographics) and plain measures.

Ambiguous scores fall into an adjudication band and set ``needs_review``; an optional
adjudicator verdict nudges by a BOUNDED amount. The engine, never a model, assigns the category.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pii_kit import UNIVERSAL_PATTERNS, Pattern, national_patterns_for

from .kernel import Citation
from .models import (
    DIRECT_ENTITIES,
    ColumnCategory,
    ColumnProfile,
    ColumnSample,
    PiiClassification,
    PiiSignal,
)

# synonym tokens -> (entity hint, category hint, weight). Direct identifiers weigh most.
_NAME_RULES: tuple[tuple[tuple[str, ...], str, ColumnCategory, float], ...] = (
    (("email", "e_mail", "mail"), "EMAIL_ADDRESS", ColumnCategory.PII_DIRECT, 0.45),
    (("nric", "fin", "uin"), "SG_NRIC_FIN", ColumnCategory.PII_DIRECT, 0.45),
    (("hkid",), "HK_HKID", ColumnCategory.PII_DIRECT, 0.45),
    (("mynumber", "kojin"), "JP_MY_NUMBER", ColumnCategory.PII_DIRECT, 0.45),
    (("tfn", "tax_file"), "AU_TFN", ColumnCategory.PII_DIRECT, 0.45),
    (("passport",), "PASSPORT", ColumnCategory.PII_DIRECT, 0.45),
    (("phone", "mobile", "msisdn", "telephone"), "PHONE_NUMBER", ColumnCategory.PII_DIRECT, 0.4),
    (
        ("name", "surname", "given_name", "full_name"),
        "PERSON_NAME",
        ColumnCategory.PII_DIRECT,
        0.35,
    ),
    (("address", "street", "addr"), "ADDRESS", ColumnCategory.PII_DIRECT, 0.35),
    (
        ("dob", "date_of_birth", "birth_date", "birthday"),
        "DATE_OF_BIRTH",
        ColumnCategory.PII_QUASI,
        0.4,
    ),
    (
        ("customer_id", "user_id", "member_id", "cust_id"),
        "GENERIC_ID",
        ColumnCategory.PII_QUASI,
        0.25,
    ),
    (("postcode", "postal_code", "zip"), "", ColumnCategory.PII_QUASI, 0.3),
    (("gender", "sex"), "", ColumnCategory.PII_QUASI, 0.3),
    (("nationality", "citizenship"), "", ColumnCategory.PII_QUASI, 0.3),
    (("salary", "income", "wage"), "", ColumnCategory.SENSITIVE, 0.4),
    (("health", "diagnosis", "medical", "disease"), "", ColumnCategory.SENSITIVE, 0.45),
    (("religion", "religious"), "", ColumnCategory.SENSITIVE, 0.45),
    (("ethnicity", "race"), "", ColumnCategory.SENSITIVE, 0.45),
    (("biometric", "fingerprint"), "", ColumnCategory.SENSITIVE, 0.45),
)

_ACTIONS = {
    ColumnCategory.PII_DIRECT: "tokenize or mask before any cloud egress",
    ColumnCategory.PII_QUASI: "generalise or bucket (k-anonymity) before analytics egress",
    ColumnCategory.SENSITIVE: "block by default; requires explicit DPO approval",
    ColumnCategory.NON_PII: "allow",
}


def _normalise(name: str) -> list[str]:
    spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", name)
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", spaced)
    cleaned = "".join(c if c.isalnum() else "_" for c in spaced.lower())
    return [t for t in cleaned.split("_") if t]


def _pattern_rows(jurisdictions: tuple[str, ...]) -> tuple[Pattern, ...]:
    return (*national_patterns_for(jurisdictions), *UNIVERSAL_PATTERNS)


def _match_ratio(regex: re.Pattern[str], validator: object, values: list[str]) -> float:
    hits = 0
    for v in values:
        if regex.search(v) is None:
            continue
        if validator is None or (callable(validator) and validator(v)):
            hits += 1
    return hits / len(values) if values else 0.0


@dataclass(frozen=True, slots=True)
class PiiClassifier:
    """Pure scoring. Thresholds are fields so a deployment can tune and a test can pin them."""

    jurisdictions: tuple[str, ...] = ("SG", "HK", "JP", "AU")
    pii_threshold: float = 0.6
    review_threshold: float = 0.3
    strong_pattern_ratio: float = 0.6
    adjudicator_nudge: float = 0.15

    def classify(
        self,
        dataset_id: str,
        profile: ColumnProfile,
        sample: ColumnSample,
        adjudication: tuple[bool, float] | None = None,
    ) -> PiiClassification:
        signals: list[PiiSignal] = []
        entity = ""
        category_hint: ColumnCategory | None = None

        # 1. name signals
        tokens = _normalise(profile.name)
        for synonyms, ent, cat, weight in _NAME_RULES:
            if any(s in tokens for s in synonyms):
                matched = next(s for s in synonyms if s in tokens)
                signals.append(
                    PiiSignal(f"name:{matched}", weight, f"column name matches synonym '{matched}'")
                )
                entity, category_hint = ent, cat
                break

        # 2. value-pattern signals (the shared pii-kit recognizers)
        values = [v.strip() for v in sample.values if v.strip()]
        best_ratio, best_type = 0.0, ""
        for info_type, regex, validator in _pattern_rows(self.jurisdictions):
            ratio = _match_ratio(regex, validator, values)
            if ratio > best_ratio:
                best_ratio, best_type = ratio, info_type
        if best_ratio > 0:
            weight = (
                0.45 * best_ratio if best_ratio >= self.strong_pattern_ratio else 0.2 * best_ratio
            )
            signals.append(
                PiiSignal(
                    f"pattern:{best_type}",
                    round(weight, 4),
                    f"{best_ratio:.0%} of {len(values)} sampled values match {best_type}",
                )
            )
            if best_ratio >= self.strong_pattern_ratio:
                entity = entity or best_type
                if category_hint is None:
                    category_hint = (
                        ColumnCategory.PII_DIRECT
                        if best_type in DIRECT_ENTITIES
                        else ColumnCategory.PII_QUASI
                    )

        # 3. shape signals: cardinality and type
        card = profile.cardinality_ratio
        if profile.non_null_count >= 10:
            if card >= 0.95 and entity and profile.inferred_type == "text":
                signals.append(PiiSignal("cardinality:unique", 0.15, f"near-unique (ratio {card})"))
            elif card <= 0.05 and category_hint is ColumnCategory.PII_QUASI:
                signals.append(
                    PiiSignal("cardinality:low", 0.1, f"low-cardinality demographic (ratio {card})")
                )
            elif card <= 0.02 and category_hint is None and entity == "":
                signals.append(
                    PiiSignal(
                        "cardinality:code", -0.15, f"code-like low cardinality (ratio {card})"
                    )
                )
        if profile.inferred_type in ("numeric", "integer") and category_hint is None and not entity:
            signals.append(PiiSignal("type:numeric", -0.1, "plain numeric measure"))

        score = max(0.0, min(1.0, sum(s.weight for s in signals)))

        # adjudication band
        needs_review = False
        if self.review_threshold <= score < self.pii_threshold:
            if adjudication is not None:
                is_pii, conf = adjudication
                nudge = self.adjudicator_nudge * (1 if is_pii else -1) * max(0.0, min(1.0, conf))
                signals.append(
                    PiiSignal("adjudicator", round(nudge, 4), f"adjudicator conf {conf:.2f}")
                )
                score = max(0.0, min(1.0, score + nudge))
            if self.review_threshold <= score < self.pii_threshold:
                needs_review = True

        soft_category = category_hint in (ColumnCategory.PII_QUASI, ColumnCategory.SENSITIVE)
        if score >= self.pii_threshold:
            category = category_hint or ColumnCategory.PII_DIRECT
        elif category_hint is not None and (
            needs_review or (soft_category and score >= self.review_threshold)
        ):
            category = category_hint
        else:
            category = ColumnCategory.NON_PII

        return PiiClassification(
            dataset_id=dataset_id,
            column=profile.name,
            category=category,
            score=round(score, 4),
            signals=tuple(signals),
            entity_type=entity,
            needs_review=needs_review,
            recommended_action=_ACTIONS[category],
            citation=Citation(
                source_id=f"pii:{dataset_id}:{profile.name}",
                title=f"PII classification of {dataset_id}.{profile.name}",
                snippet=f"category={category.value} score={round(score, 4)}",
            ),
        )
