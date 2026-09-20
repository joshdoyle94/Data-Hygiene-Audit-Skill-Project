# RIA Account Hygiene, write-up

An Agent Skill that audits CRM account records against a lead-data source, classifies
every discrepancy as a gap, a staleness problem, or a conflict, and routes each one to
AUTO, REVIEW, or SKIP through a provenance-aware write gate. The seed scenario is a
fintech SaaS vendor selling planning software to registered investment advisers.

## The problem

Account firmographics decay quietly. For a vendor selling into advisory firms, three
fields do most of the work: adviser headcount, custodian, and service model. All three
drift without anyone noticing. A firm that grew from 20 advisers to 34 still shows 20. A
firm that moved custodians still shows the old one. Nobody is wrong on purpose. The
record was right when someone typed it.

The cost is not abstract. Coverage and routing get assigned off those fields, so stale
values put accounts in the wrong tier with the wrong owner. The bigger problem is that
the team learns the data is unreliable and stops trusting any of it, which is how a CRM
turns into a place people log activity instead of a place they get answers.

The usual fix is to bulk-enrich everything from a vendor feed, and that trades one
failure for a worse one. It overwrites values a rep deliberately corrected, it
propagates vendor errors at scale, and it leaves no record of what changed.

What this unlocks is not cleaner data. It is enrichment you can point at a live CRM
without a human reviewing every row, because the system knows which records it is not
allowed to touch.

## Assumptions

Lead data is multi-source and contradictory. Three sources, one to three rows per firm,
roughly 30% field coverage gaps, and disagreement between them. Reconciliation is the
problem, not retrieval.

Some CRM values are deliberate. A rep who corrects a field is usually right, and the
system has to be able to tell that apart from staleness.

A human claim decays. Correct at verification time does not mean correct now.

The CRM is a shared surface. Throughput matters less than never writing something wrong.
A missed gap costs an opportunity. A bad overwrite costs the team's trust.

Sheets is the medium, not the architecture. `store.py` is an adapter, and the audit logic
never learns where records live.

## Design decisions

**A skill, not a script.** A script can find discrepancies. It cannot decide whether two
firm names refer to the same entity, whether a vendor taxonomy difference is a real
disagreement or just different vocabulary, or how to explain a conflict to the rep who
owns the account. Those are the only three things the model is given, and `audit.py`
marks exactly which findings need them with `needs_judgment: true`. Everything that
touches the system of record is deterministic.

**A skill, not a direct MCP call.** An MCP server would give the agent enrichment access.
It would not give it a procedure, a write gate, or an audit trail. The skill is the
hygiene SOP: judgment, rules, and tools version-controlled in one folder.

**Structured so the model can reason reliably.** Findings arrive as flat records with the
defect class, the source value, the provenance state, the rule that fired, and the
proposed disposition already assigned. The model reads them rather than re-deriving them.
It cannot promote a disposition, and `apply.py` re-checks the lock independently before
writing. The guard is duplicated on purpose, because a single point of failure on a write
path into a CRM is not acceptable.

**Source precedence over statistics.** A declared waterfall (`vendor_a`, `vendor_b`,
`web_crawl`), first non-blank value wins. An earlier draft weighted sources by confidence
times recency and took medians across vendor rows. Nobody had calibrated those weights,
and with three rows a median is just the middle value. The ranking is a business decision
made once by whoever owns the book.

**Provenance and recency, not one flag.** `hygiene_override = TRUE` is absolute.
`data_source = rep_verified` is time-decaying: it outranks source data for 180 days, then
becomes reviewable but never auto-writable. `bulk_import` voids its own timestamp,
because a migration stamps every record with the load date.

**Left out on purpose.** Contacts and leads, duplicate merge, bulk API batching,
field-history staleness, territory logic, re-verification scheduling, and REVIEW queue
assignment. Each one is real work. None of them changes whether the core gate is sound.

## Where AI helped, and where I did not trust it

AI wrote most of the implementation and the first draft of the reasoning. Three of its
outputs were wrong in ways that ran clean.

The first reconciliation design used median-of-vendor-rows, a confidence-times-recency
weighting, and a 0.15 margin threshold. It reads as rigorous and it is not. Nothing
calibrated those numbers, and a median of three values is the middle one. I replaced it
with a declared waterfall, which is what enrichment stacks actually do and what a RevOps
owner can reason about without arithmetic.

The first audit run reported 49 conflicts against 4 planted defects. `classify()` did not
handle a null source value, so every populated field with no matching lead row was called
a conflict. It ran without error and reported confidently.

Corroboration used exact string equality and was applied to a numeric field. Vendor
headcounts are jittered, so 338 never corroborated 340. The system was suppressing writes
it should have made, and nothing errored.

During the live Sheets run, `apply.py` preferred `findings.adjudicated.json` over
`findings.json` without checking that the run ids matched, so it applied adjudications
from a previous audit. The output was identical only because the seed data is
deterministic. On a book that had changed between runs it would have written decisions
about records that no longer looked that way. It is guarded now.

The pattern across all four is the same. Each was fluent, ran without error, and produced
output that looked right. What caught them was ground truth, not inspection. The seed
manifest records every planted defect and the disposition it should receive, so the audit
is scoreable rather than just descriptive.

Where the model was reliable: all seven adjudications held up on verification.
Corroboration flags were correct in both directions, `rep_verified` dates were quoted
exactly, and the SBSB legal-name variant resolved correctly against the domain. It also
noticed on its own that ACC-1012's lock protects a record nobody ever rep-verified, which
is a design observation I had not made.

## What I would harden for production

**Validate the rationale, not just the authority.** `adjudicate.py` constrains what the
model may decide. It does not check whether the sentence attached to a finding is true. A
linter asserting that claimed corroboration matches the flag, and that any date or source
named in the prose appears in the finding record, is the missing piece.

**Locks need provenance.** A `hygiene_override` with no reason and no owner is honored
forever. Locks should carry a reason, an owner, and an expiry.

**Reliability.** Batched reads and writes with retry and backoff, and idempotency keys
per run so a partial failure can resume without double-writing. Right now it is a row at
a time.

**Security.** A dedicated integration user on a restricted profile, field-level security
enforcing the write allowlist at the platform rather than in code, and secrets in a
manager rather than a local JSON key. The write gate should be defended by permissions,
not only by Python.

**Scale.** Forty accounts runs in memory. A real book is six figures, which needs an
incremental audit scoped to records not verified in N days, batched source calls, and a
run ledger so an interrupted sweep resumes.

**Accuracy.** The seed manifest is a fixture. Production needs a sampled, human-labelled
set, re-scored on every rules change, with per-field precision tracked over time. The
AUTO threshold should be tuned per field from that data rather than set globally by
judgment.

**Operations.** The REVIEW queue needs an owner, an SLA, and assignment by account owner.
Sixteen findings nobody is accountable for is a spreadsheet, not a process. Approving a
REVIEW item should also write `rep_verified`, so human decisions feed back into the
precedence model instead of being surfaced again on the next run.

**The enterprise constraint this sidesteps.** Building against a sheet with a service
account is a velocity choice. At scale the gatekeeper is not the code. It is who can
provision the integration user, which profile it runs under, and whether the automation
platform is approved for team-wide access. That constraint determines the tool, not the
other way around.