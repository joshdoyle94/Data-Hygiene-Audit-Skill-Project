#!/usr/bin/env python3
"""
Apply AUTO findings and log every finding.

This is the only code in the repo that writes to the system of record. It
applies findings whose disposition is already AUTO; it does not evaluate rules
and it cannot promote a finding. If a disposition is wrong, the bug is in
audit.py or in the rules, never here.

  python scripts/apply.py --dry-run    show what would happen, write nothing
  python scripts/apply.py              apply AUTO, append the full log
"""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime

import config
from store import get_store

TODAY = "2026-09-20"

LOG_COLUMNS = ["run_id", "timestamp", "account_id", "domain", "field",
               "old_value", "proposed_value", "disposition", "confidence",
               "source", "source_url", "evidence", "rule_fired"]


def to_log_row(f, ts):
    corr = "corroborated" if f.get("corroborated") else "single-source"
    ev = f"{f['defect_class']}; {corr}"
    if f.get("drift") is not None:
        ev += f"; drift {f['drift']:.0%}"
    if f.get("observed_at"):
        ev += f"; observed {f['observed_at']}"
    if f.get("rationale"):
        ev += f"; {f['rationale']}"
    return {
        "run_id": f["run_id"], "timestamp": ts, "account_id": f["account_id"],
        "domain": f["domain"], "field": f["field"], "old_value": f["old_value"],
        "proposed_value": f["proposed_value"], "disposition": f["disposition"],
        "confidence": corr, "source": f["source"], "source_url": f["source_url"],
        "evidence": ev, "rule_fired": f["rule_fired"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--findings", default=None)
    args = ap.parse_args()

    # Prefer the adjudicated file when it exists: it carries the agent's
    # rationale on the REVIEW queue. Falls back to the raw audit.
    path = args.findings or ("findings.adjudicated.json"
                             if os.path.exists("findings.adjudicated.json")
                             else "findings.json")
    run = json.load(open(path))

    # An adjudicated file belongs to exactly one audit. Applying decisions made
    # against a previous run silently writes judgments about records that may
    # have changed since.
    if path == "findings.adjudicated.json" and os.path.exists("findings.json"):
        current = json.load(open("findings.json"))["run_id"]
        if run["run_id"] != current:
            print(f"STALE: {path} is from {run['run_id']}, latest audit is {current}.")
            print("Re-adjudicate against the current run, or pass "
                  "--findings findings.json to apply the rules' dispositions as-is.")
            return 1
    findings = run["findings"]
    ts = datetime.now().isoformat(timespec="seconds")

    auto = [f for f in findings if f["disposition"] == "AUTO"]

    # Guard: nothing protected can reach a write, whatever findings.json says.
    store = get_store()
    accounts = {a["account_id"]: a for a in store.read("accounts")}
    blocked = [f for f in auto
               if str(accounts[f["account_id"]].get("hygiene_override", "")).upper() == "TRUE"]
    if blocked:
        print("REFUSING TO WRITE -- AUTO finding on a locked record:")
        for f in blocked:
            print(f"  {f['account_id']} {f['field']} ({f['rule_fired']})")
        return 1

    print(f"run {run['run_id']}  source={path}  findings={len(findings)}  auto={len(auto)}")
    for f in auto:
        arrow = f"{f['old_value']!r} -> {f['proposed_value']!r}"
        print(f"  {'WOULD WRITE' if args.dry_run else 'WRITE'} "
              f"{f['account_id']} {f['field']:14} {arrow:40} via {f['source']}")

    if args.dry_run:
        print(f"\ndry run -- no writes, no log rows ({len(findings)} would be logged)")
        return 0

    # Group per account so each record is touched once.
    per_account = {}
    for f in auto:
        u = per_account.setdefault(f["account_id"], {})
        u[f["field"]] = f["proposed_value"]
        u["last_verified"] = TODAY
        u["data_source"] = f"enriched_{f['source']}"

    for aid, updates in per_account.items():
        store.update_row("accounts", "account_id", aid, updates)

    # Every finding is logged, not just the writes. The SKIP rows are the
    # record of what the system declined to touch and why.
    store.append("audit_log", [to_log_row(f, ts) for f in findings])

    d = Counter(f["disposition"] for f in findings)
    print(f"\nwrote {len(auto)} values across {len(per_account)} accounts")
    print(f"logged {len(findings)} rows: " + "  ".join(f"{k}={v}" for k, v in sorted(d.items())))
    review = [f for f in findings if f["disposition"] == "REVIEW"]
    print(f"{len(review)} findings queued for human review")
    return 0


if __name__ == "__main__":
    sys.exit(main())