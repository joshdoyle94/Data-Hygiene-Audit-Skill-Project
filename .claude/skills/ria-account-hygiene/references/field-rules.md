# Field rules

Loaded on demand. Everything here is enforced by `scripts/audit.py`; this file is the
human-readable statement of the same logic, and the reference for adjudicating findings
marked `needs_judgment`.

## Fields in scope

| CRM field | Source column | Type | Notes |
|---|---|---|---|
| `industry` | `industry_reported` | picklist | vendor vocabularies differ; needs mapping |
| `num_advisors` | `employee_count` | numeric | drift-based, not equality-based |
| `custodian` | `custodian_reported` | picklist | sparse coverage — blank on ~30% of rows |
| `service_model` | `service_model_reported` | picklist | the highest-value field; also the most contested |
| `tax_services` | `tax_services_reported` | picklist | — |
| `fee_model` | `fee_model_reported` | picklist | — |

Out of scope: `firm_name`, `domain`, `account_id`. Identity fields are never
auto-corrected; a mismatch on them is an entity-resolution finding, not a hygiene fix.

## Placeholders

These are gaps, not values: empty string, whitespace only, `N/A`, `n/a`, `NA`,
`Unknown`, `unknown`, `-`, `--`, `TBD`, `None` **only in a field where `None` is not a
valid picklist value**. Note `tax_services` legitimately takes `None` — a hardcoded
placeholder list that does not account for this will destroy real data.

## Source precedence (waterfall)

A domain has 1–3 lead rows from `vendor_a`, `vendor_b`, or `web_crawl`. They disagree,
and they have gaps. Resolve by declared precedence, not by vote.

**Order: `vendor_a` > `vendor_b` > `web_crawl`.**

Per field, walk that order and take the first non-blank value. It wins; record which
source it came from. The ranking is a business decision made once — *which source do we
trust on custodian?* — not a calculation made per record. It lives in config so the
person who owns the book can change it without touching code.

Ignore any row whose `observed_at` is more than **18 months** old. It is describing a
different company.

Each winning value carries one flag:

- **corroborated** — at least one other source reports the same value
- **single-source** — no other source has a value for this field, or they disagree

That is the entire reconciliation step. No averaging, no weighted scoring.

Numeric fields use the same waterfall — first source with a count wins. The only extra
rule is **materiality**: flag `num_advisors` only where the winning count differs from
the CRM by more than **25%**. That is a judgment about what deserves a rep's attention,
tunable by whoever owns the book. It is not a statistical threshold and should not be
defended as one.

## Defect classes

- **gap** — CRM value is a placeholder, source has a value.
- **stale** — both populated and `num_advisors` differs from the winning source's count
  by **more than 25%**. Percentage rather than absolute, so one threshold works across a
  book spanning 3 to 340 advisors.
- **conflict** — both populated, both are valid picklist values, and they differ.
- **match** — no finding. Not logged as a defect, counted in the run summary.

## Provenance precedence

`last_verified` is only meaningful alongside `data_source`.

| `data_source` | Meaning | Effect |
|---|---|---|
| `rep_verified` | A human checked this record | Outranks source **within 180 days** |
| `crm_manual` | Entered, never verified | No precedence |
| `bulk_import` | Loaded in a migration | **No precedence, and `last_verified` is void** |

`bulk_import` is the trap. A migration stamps every record with the load date, so a
record can report a recent `last_verified` while nobody has ever checked it. Treat the
date as absent. In this dataset, six accounts share the identical stamp `2025-03-15` —
identical timestamps across unrelated records are the signature of a bulk write, not of
verification.

Freshness window: **180 days**. Beyond it a rep-verified claim is decayed — still
protective enough to block an automatic write, not strong enough to suppress the finding.

## Disposition gate

Evaluated in order. First match wins. The rule that fired is recorded in the log.

| # | Condition | Disposition | Rule |
|---|---|---|---|
| 1 | `hygiene_override = TRUE` | SKIP | `POLICY_LOCK` |
| 2 | No source value for the field | SKIP | `NO_SOURCE` |
| 3 | CRM matches the winning value | — | `MATCH` |
| 4 | `rep_verified` and verified within 180 days | SKIP | `FRESH_HUMAN` |
| 5 | Entity identity unresolved | SKIP | `IDENTITY_UNRESOLVED` |
| 6 | Class `conflict` | REVIEW | `CONFLICT_NEEDS_HUMAN` |
| 7 | `rep_verified` and decayed past 180 days | REVIEW | `DECAYED_HUMAN` |
| 8 | Class `gap` or `stale`, **corroborated** | AUTO | `AUTO_ELIGIBLE` |
| 9 | Class `gap` or `stale`, **single-source** | REVIEW | `SINGLE_SOURCE` |

**AUTO is reachable only through rule 8.** A gap or a drifted count, a second source
agreeing, no human claim on the record, identity established. Everything else is a human decision or no
decision at all.

A conflict never auto-resolves. The CRM value is a claim someone made; overwriting it
because a vendor disagrees is how automated hygiene corrupts a book.

## Deterministic versus model

| Decided by `audit.py` | Decided by the model |
|---|---|
| Placeholder detection | Entity identity across name variants |
| Waterfall selection and corroboration | Taxonomy mapping to picklist values |
| Drift percentage vs. materiality threshold | REVIEW rationale, one sentence per finding |
| Provenance and freshness evaluation | Triage ordering of the REVIEW queue |
| Disposition assignment | — |
| The write itself | — |

The model never selects a value that is not already in `lead_data`, never restates a
number, and never overrides a disposition the gate assigned.

## Taxonomy mapping

`industry` source values map to the CRM picklist `Financial Services`:
`financial services`, `Investment Management`, `Wealth Management`,
`Investment Advisory`, `Financial Planning`. These are vocabulary differences, not
conflicts — mapping them is the model's job, and the result is `MATCH`, not a fix.

An industry value outside that set is a genuine finding, not a mapping problem.

`service_model` does **not** map loosely. `Ongoing Advisory`, `Standalone Planning`, and
`Hybrid` describe different businesses. A source reporting `Hybrid` against a CRM
holding `Ongoing Advisory` is a real conflict — route it, do not reconcile it.

## Logging

Every finding, all three dispositions, one row in `audit_log`:

```
run_id | timestamp | account_id | domain | field | old_value | proposed_value |
disposition | confidence | source | source_url | evidence | rule_fired
```

The SKIP rows matter most. A log of what the system declined to change, and why, is what
makes it safe to point at a real CRM.
