# RIA Account Hygiene, an Agent Skill for CRM data quality

An Agent Skill that audits CRM account records against a lead-data source, classifies
every discrepancy as a gap, a staleness problem, or a conflict, and routes each one to
AUTO, REVIEW, or SKIP through a provenance-aware write gate. The scenario is a fintech
SaaS vendor selling planning software to registered investment advisers.

## Why it matters

Three fields drive coverage and routing on an advisory-firm account: adviser headcount,
custodian, and service model. All three decay quietly, so accounts end up in the wrong
tier with the wrong owner. The usual fix, bulk enrichment from a vendor feed, is worse.
It overwrites values reps deliberately corrected and leaves no record of what changed.

What this unlocks is not cleaner data. It is enrichment you can point at a live CRM
without reviewing every row, because the system knows which records it is not allowed to
touch.

## How it works

```
accounts ──┐                                    ┌─► accounts   (AUTO only, 5 writes)
           ├─► audit.py ─► findings ─► agent ─► apply.py
lead_data ─┘   waterfall   28 items   7 judged  └─► audit_log  (all 28, incl. SKIPs)
               classify              ▲
               gate                  └─ adjudicate.py: may lower a disposition,
                                        never raise one
```

Google Sheets, read and gated write, behind a `Store` adapter, so the audit logic never
learns where records live and Salesforce is one more subclass. Verified by running
identically against CSV and Sheets: same 28 findings, same split.

Everything touching the system of record is deterministic: placeholder detection, source
waterfall, corroboration, drift thresholds, provenance, disposition. The model gets three
jobs the rules flag for it: entity identity across legal-name variants, taxonomy mapping,
and the rationale on each REVIEW item.

Provenance is the core idea. Same disagreement, four right answers:

| Account | Provenance | CRM | Source | Result |
|---|---|---|---|---|
| ACC-1004 | `crm_manual` | Schwab | Fidelity | REVIEW, nobody vouched for it |
| ACC-1005 | `rep_verified`, 84d | Pershing | Schwab | SKIP, fresh human wins |
| ACC-1008 | `rep_verified`, 377d | Fidelity | Schwab | REVIEW, the claim has decayed |
| ACC-1012 | `hygiene_override` | Hybrid | Ongoing Advisory | SKIP, locked |

## Results

40 accounts, 240 checks, 68 lead rows across three sources.

```
28 findings   5 AUTO   16 REVIEW   7 SKIP      precision 89%   recall 96%
protection leaks 0      unplanted findings auto-written 0
```

The last two are the ones that matter. A missed stale field costs an opportunity. An
overwritten rep-verified value costs the team's trust in the CRM permanently.

Three guardrails, all demonstrated. The rules blocked at audit time. The validator
rejected five separate attempts to escalate: promoting REVIEW to AUTO, proposing a value
no source reported, overriding a lock, a two-character rationale, and adjudicating an
account that does not exist. And when asked directly to override the lock on ACC-1012,
the agent refused, cited the rule, and offered the legitimate escalation path instead.

## AI, where it helped and where I did not trust it

AI wrote most of the implementation. Three outputs were wrong in ways that ran clean.
The reconciliation design started with invented statistical rigor, confidence-times-
recency weights that nobody had calibrated, which I replaced with a declared waterfall.
The first audit reported 49 conflicts against 4 planted, because `classify()` did not
handle a null source value. And `apply.py` applied an adjudication file from a previous
audit without checking the run id. Each was caught by ground truth, since the seed
manifest scores every planted defect against its expected disposition, not by inspection.

Where it was reliable: all seven adjudications held up on verification, and it noticed on
its own that ACC-1012's lock protects a record nobody ever rep-verified.

## What I would harden

`adjudicate.py` constrains what the model may decide, not whether its prose is true, so a
rationale linter is the missing piece. Locks need a reason, an owner, and an expiry.
Security belongs in a restricted integration profile and field-level security rather than
only in Python. Scale needs incremental audit, batching, and idempotency keys. Accuracy
needs a sampled human-labelled set replacing the fixture, with the AUTO threshold tuned
per field. The REVIEW queue needs an owner and an SLA, because sixteen findings nobody is
accountable for is a spreadsheet rather than a process.

The constraint this sidesteps: a service account on a sheet is a velocity choice. At
scale the gatekeeper is not the code, it is who can provision the integration user and
which profile it runs under. That determines the tool, not the other way around.