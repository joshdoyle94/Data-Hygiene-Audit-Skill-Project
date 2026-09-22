# RIA Account Hygiene, an Agent Skill

This skill audits CRM account records against a lead-data source, classifies every
discrepancy as a gap, a staleness problem, or a conflict, and routes each one to AUTO,
REVIEW, or SKIP through a write gate that understands provenance.

The scenario is a fintech SaaS vendor selling planning software to registered investment
advisers. Accounts are advisory firms. The fields that decay are the ones that matter:
how many advisers a firm has, which custodian it clears through, and whether it does
ongoing advisory work or one-off planning.

Loom recording here: https://www.loom.com/share/0154486acd3c4affa3f4fd7d98fdf27f

## Why a skill and not a script

A script can find the discrepancies. It cannot decide whether "SBSB Financial Advisors"
and "Sullivan Bruyette Speros & Blayney" are the same firm, whether a vendor reporting
"Investment Management" against a CRM holding "Financial Services" is a real
disagreement or just different vocabulary, or how to explain a conflict to the rep who
owns the account.

So the work is split. Deterministic logic owns anything that touches the system of
record. The model owns the judgment calls the rules hand it, and nothing else.

| Decided by audit.py | Decided by the model |
|---|---|
| Placeholder detection | Entity identity across name variants |
| Waterfall selection and corroboration | Taxonomy mapping to picklist values |
| Drift percentage vs. materiality threshold | One sentence of rationale per REVIEW item |
| Provenance and freshness | Triage order of the REVIEW queue |
| Disposition assignment | |
| The write itself | |

Three constraints hold throughout: never write a value that is absent from the source,
never restate a number (values pass through verbatim), and abstain by default.

The model's output is treated as untrusted input. `scripts/adjudicate.py` validates every
adjudication independently. It may lower a disposition but never raise one, AUTO is
unreachable by adjudication, a proposed value has to have been reported by some source,
and a finding the rules already settled is not open to it. Rejected entries are discarded
and the rules' disposition stands.

## Architecture

```
accounts ──┐                                    ┌─► accounts   (AUTO only)
           ├─► audit.py ─► findings ─► agent ─► apply.py
lead_data ─┘   waterfall   28 items   7 judged  └─► audit_log  (all 28, incl. SKIPs)
               classify              ▲
               gate                  └─ adjudicate.py validates the judgment
```

`store.py` is an adapter, so the audit logic never learns where records live. Swapping
the sheet for Salesforce means writing one more `Store` subclass rather than editing
`audit.py`. CSV is the default backend so the demo runs with no credentials.

## Setup

```bash
git clone <repo> && cd ria-hygiene-skill
python3 scripts/generate_seed.py
```

Nothing to install for the CSV backend. For Google Sheets:

```bash
python3 -m pip install -r requirements.txt
```

1. In Google Cloud, create a project and enable the Google Sheets API.
2. Credentials, then Create service account, then Keys, then Add key, JSON. Save it to
   the repo root as `service_account.json`. It is gitignored.
3. Create a spreadsheet with three tabs named exactly `accounts`, `lead_data`, and
   `audit_log`, and import the matching CSV from `data/` into each one using File,
   Import, Replace current sheet.
4. Share the sheet with the service account's `client_email` as an Editor.
5. In `scripts/config.py`, set `BACKEND = "sheets"` and set `SHEET_KEY` to the id between
   `/d/` and `/edit` in the sheet URL.

Setting `SHEET_KEY` matters. `gspread.open()` looks a sheet up by title, which is a Drive
operation and needs the Drive API enabled as well. `open_by_key()` uses only the Sheets
API and survives a rename.

Resetting on the Sheets backend is manual. `generate_seed.py` rewrites `data/*.csv` only,
so you have to re-import `accounts.csv` and `audit_log.csv` to restore the sheet. Seeding
and teardown should route through the `Store` adapter like everything else. They do not
yet.

## Running it

```bash
export PYTHONPATH=scripts

python3 scripts/audit.py                    # read both tabs, write findings.json
python3 scripts/adjudicate.py --template    # skeleton of the open findings
#   the agent fills in adjudications.json
python3 scripts/adjudicate.py               # validate and merge its judgment
python3 scripts/apply.py --dry-run          # show the writes, change nothing
python3 scripts/apply.py                    # apply AUTO, log every disposition
python3 scripts/score.py                    # precision and recall against ground truth
```

Or open the repo in Claude Code and ask it to audit the account book. The skill sits at
`.claude/skills/ria-account-hygiene/`, which is where Claude Code discovers project
skills, and it triggers off the description without being named.

## Results on the seed data

40 accounts, 6 fields, 240 checks, 68 lead rows across three sources.

```
findings   28      AUTO 5    REVIEW 16    SKIP 7
precision  89%     recall 96%
protection leaks                     0
unplanted findings auto-written      0
```

The last two numbers are the ones that matter. Precision and recall describe how much the
audit found. The leak counts describe whether it wrote anything it should not have. A
hygiene system that misses a stale field costs you an opportunity. One that overwrites a
rep's verified value costs you the rep's trust in the CRM, permanently.

### Rules fired

| Rule | Count | Disposition |
|---|---|---|
| `AUTO_ELIGIBLE` | 5 | AUTO, gap or drift, corroborated, no human claim |
| `CONFLICT_NEEDS_HUMAN` | 7 | REVIEW, CRM and source both plausible |
| `SINGLE_SOURCE` | 9 | REVIEW, only one source reports it |
| `POLICY_LOCK` | 3 | SKIP, `hygiene_override = TRUE` |
| `FRESH_HUMAN` | 2 | SKIP, rep verified within 180 days |
| `NO_SOURCE` | 2 | SKIP, a gap the source cannot fill |

### The four-way case

Four accounts have the same shape of disagreement and four different right answers.
Provenance and recency are the only things separating them.

| Account | `data_source` | Verified | CRM | Source | Result |
|---|---|---|---|---|---|
| ACC-1004 | `crm_manual` | | Schwab | Fidelity | REVIEW, nobody vouched for it |
| ACC-1005 | `rep_verified` | 84d | Pershing | Schwab | SKIP, fresh human wins |
| ACC-1008 | `rep_verified` | 377d | Fidelity | Schwab | REVIEW, the claim has decayed |
| ACC-1012 | `hygiene_override` | | Hybrid | Ongoing Advisory | SKIP, locked |

## Design decisions worth naming

**Source precedence, not statistics.** The order is `vendor_a`, then `vendor_b`, then
`web_crawl`, and the first non-blank value wins. An earlier draft scored sources with
confidence-times-recency weights and took medians across vendor rows. That was invented
rigor. With three rows a median is just the middle value, and nobody had calibrated the
weights. A declared waterfall is what enrichment stacks actually do, and the ranking is a
business decision made once by whoever owns the book.

**AUTO requires corroboration.** A second source has to independently report the same
value. That can be stated in one sentence and defended without arithmetic.

**Conflicts never auto-resolve.** A populated CRM field is a claim someone made.
Overwriting it because a vendor disagrees is how automated hygiene destroys a book.

**`None` is a valid value for `tax_services`.** A naive placeholder list treats it as a
gap and overwrites firms that genuinely offer no tax services. It is called out
explicitly in `references/field-rules.md` because it is the shape of bug that ships
silently.

**`service_model` gets no synonym mapping.** Industry variants reconcile, because "Wealth
Management" and "Investment Advisory" are the same claim in different words. Ongoing
advisory and standalone planning are different businesses, so a mismatch there is routed
rather than reconciled.

**`bulk_import` voids its own timestamp.** A migration stamps every record with the load
date, so `last_verified` reports when rows moved rather than when anyone checked them.
Six seed accounts share the identical stamp `2025-03-15`. Identical timestamps across
unrelated records are the signature of a bulk write.

**Everything is logged, not just the writes.** All 28 findings hit `audit_log`, including
the 7 SKIPs with the rule that caused each one. The record of what the system declined to
touch is what makes it safe to point at a real CRM.

## Deliberately out of scope

Contacts and leads. Duplicate detection and merge. Bulk API batching. Field-history
staleness. Territory and owner logic. Any write path that bypasses the gate.
Re-verification scheduling. Notification and assignment of the REVIEW queue.

## Repo

```
.claude/skills/ria-account-hygiene/
    SKILL.md                  procedure and judgment
    references/field-rules.md thresholds, gate, taxonomy, loaded on demand
scripts/config.py             every tunable, no hidden constants
scripts/store.py              backend adapter (csv or sheets)
scripts/audit.py              waterfall, classification, gate, writes findings.json
scripts/adjudicate.py         validates the agent's judgment
scripts/apply.py              the only writer, AUTO only, logs everything
scripts/score.py              precision, recall, and leaks vs. the seed manifest
scripts/generate_seed.py      deterministic seed plus defect manifest
data/                         accounts, lead_data, audit_log, seed_manifest
```

## Data and confidentiality

The vendor is fictional. Account records are seeded by `scripts/generate_seed.py` against
publicly listed advisory-firm names and domains, with every defect planted
deterministically. Lead data is synthetic. Nothing here derives from any current or
former employer, and no proprietary or confidential material is used.
