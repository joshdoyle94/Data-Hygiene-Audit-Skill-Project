---
name: ria-account-hygiene
description: Audit CRM account records for gaps, staleness, and conflicts against a lead-data source, then propose or apply corrections under a provenance-aware write gate. Use when asked to audit, clean, enrich, verify, or reconcile account or firmographic data, or when asked why a CRM field is wrong or out of date.
---

# RIA Account Hygiene

Audits a book of advisory-firm accounts against a lead-data source, classifies every
finding, and routes each one to **AUTO**, **REVIEW**, or **SKIP**. The system of record
is only written where the evidence and the provenance both permit it.

## Operating rule

This skill proposes. Rules gate. A human approves anything that isn't unambiguous.

Three constraints hold at all times, without exception:

1. **Never write a value that is not present in the source data.** Values are copied
   through verbatim. If a value needs to be composed, inferred, or estimated, abstain.
2. **Never restate a number.** Numeric values pass from source to proposal by reference,
   not by retyping. Do not round, convert, or summarize a count.
3. **Abstention is the default.** Missing source coverage, weak consensus, and ambiguity
   all resolve to SKIP or REVIEW. A record left alone is a correct outcome.

## Procedure

**1. Audit.** Run `scripts/audit.py`. It reads the `accounts` and `lead_data` tabs,
reconciles the lead rows per field, applies the rules in
`.claude/skills/ria-account-hygiene/references/field-rules.md`, and writes `findings.json`. Every finding carries a defect
class, a reconciled source value, a consensus strength, a provenance state, and a
proposed disposition.

Do not re-derive any of this. The script owns placeholder detection, reconciliation
math, drift computation, threshold comparison, and the provenance gate. Read its output.

**2. Adjudicate the flagged set.** The script marks findings `needs_judgment: true`
where a deterministic rule cannot settle the question. Only these require you. Load
`.claude/skills/ria-account-hygiene/references/field-rules.md` before adjudicating. Three cases arise:

- *Entity identity.* The lead row's firm name does not match the account's. Decide
  whether it is the same firm under a different legal name, DBA, or post-rebrand name.
  Domain match is strong evidence; name divergence alone is not disqualifying. If you
  cannot establish identity, set SKIP and say why.
- *Taxonomy reconciliation.* Source rows report industry or service model in a
  vocabulary the CRM picklist does not use. Map it to a picklist value only where the
  mapping is unambiguous. Where two picklist values are both defensible, that is a
  genuine conflict — REVIEW, not a guess.
- *Rationale.* Every REVIEW finding needs one sentence a human can act on: what
  disagrees, which sources say what, and what you would do. Name the sources.

Write your decisions to `adjudications.json` as a list of
`{account_id, field, disposition, rationale, priority}`. Start from
`python scripts/adjudicate.py --template`, which emits one entry per open finding.
Order the queue by how much a wrong value costs, not by confidence.

**3. Validate the judgment.** Run `scripts/adjudicate.py`. It checks every entry against
the audit and discards anything outside your remit: you may lower a disposition, never
raise one; AUTO is unreachable by adjudication; a proposed value must have been reported
by some source; and a finding the rules already settled is not open to you. Rejected
entries are dropped and the rules' disposition stands. Read the rejections — a rejection
means the reasoning was wrong, not that the validator was.

**4. Apply.** Run `scripts/apply.py`. It writes AUTO findings to the `accounts` tab,
stamps `last_verified` and `data_source`, and appends **every** finding — AUTO, REVIEW,
and SKIP alike — to the `audit_log` tab. Never write to the accounts tab by any other
path.

**5. Report.** Counts by disposition and by defect class, the REVIEW queue in priority
order, and every SKIP with the rule that caused it. If `seed_manifest.json` is present,
run `scripts/score.py` and report precision and recall against ground truth rather than
raw finding counts.

## What you do not decide

- Whether a write happens. `apply.py` writes AUTO only; the gate is in the rules.
- Whether your own judgment is accepted. `adjudicate.py` validates it independently.
- Whether a protected record can be touched. `hygiene_override = TRUE` is absolute.
- Whether a value is stale. Thresholds are in the rules file, not your judgment.
- What a field should contain when the source is silent. Silence means SKIP.

## Provenance

`data_source` and `last_verified` together outrank source data in one specific case: a
rep-verified record inside the freshness window. Outside that window the human claim has
decayed and the record becomes reviewable — never auto-writable. `bulk_import`
provenance carries no verification at all; treat its `last_verified` date as absent
regardless of how recent it looks.

Full precedence table, thresholds, and the per-field rules:
`.claude/skills/ria-account-hygiene/references/field-rules.md`.

## Paths

Run every command from the repository root. Scripts live in `scripts/`, data in
`data/`, and the rules reference in this skill's own `references/` directory.
