#!/usr/bin/env python3
"""
Merge and validate the agent's adjudications.

The agent writes adjudications.json. This script checks that file against the
audit output and refuses anything outside the model's remit, then emits
findings.adjudicated.json for apply.py.

The point of this script is that the model's output is untrusted input. It may
add reasoning; it may not add authority. Specifically it can never:

  - raise a disposition toward a write (nothing reaches AUTO by adjudication)
  - propose a value that no source reported
  - adjudicate a finding the rules did not flag as needing judgment
  - invent a finding that the audit did not produce

  python scripts/adjudicate.py --check     validate only, write nothing
  python scripts/adjudicate.py             validate and merge
  python scripts/adjudicate.py --template  emit a skeleton to fill in
"""

import argparse
import json
import sys

import config
from store import get_store

# Severity ladder. Adjudication moves down it, never up.
LADDER = {"AUTO": 3, "REVIEW": 2, "SKIP": 1, "DISMISSED": 0}
MIN_RATIONALE = 25


def source_values(leads, domain, field):
    """Every value any source reported for this domain/field. Nothing else is writable."""
    col = config.FIELD_MAP[field]
    return {str(r.get(col, "")).strip()
            for r in leads if str(r.get("domain", "")).strip() == domain
            and str(r.get(col, "")).strip()}


def validate(findings, adj, leads):
    by_key = {(f["account_id"], f["field"]): f for f in findings}
    errors, applied = [], []

    for a in adj:
        key = (a.get("account_id"), a.get("field"))
        f = by_key.get(key)

        if f is None:
            errors.append(f"{key}: no such finding — the audit did not produce it")
            continue

        if not f["needs_judgment"]:
            errors.append(f"{key}: rules settled this; not open for adjudication "
                          f"({f['rule_fired']})")
            continue

        rationale = str(a.get("rationale", "")).strip()
        if len(rationale) < MIN_RATIONALE:
            errors.append(f"{key}: rationale missing or too short "
                          f"({len(rationale)} chars, need {MIN_RATIONALE})")
            continue

        new_disp = a.get("disposition", f["disposition"])
        if new_disp not in LADDER:
            errors.append(f"{key}: unknown disposition {new_disp!r}")
            continue

        if LADDER[new_disp] > LADDER[f["disposition"]]:
            # One exception: resolving an identity block raises scrutiny, not
            # write authority. SKIP -> REVIEW only, and never to AUTO.
            identity_case = (f["rule_fired"] == "IDENTITY_UNRESOLVED"
                             and a.get("identity_resolved") is True
                             and new_disp == "REVIEW")
            if not identity_case:
                errors.append(f"{key}: cannot raise {f['disposition']} -> {new_disp}; "
                              f"adjudication only lowers severity")
                continue

        if new_disp == "AUTO":
            errors.append(f"{key}: AUTO is not reachable by adjudication")
            continue

        new_val = a.get("proposed_value", f["proposed_value"])
        if new_val and new_val != f["proposed_value"]:
            allowed = source_values(leads, f["domain"], f["field"])
            if new_val not in allowed:
                errors.append(f"{key}: proposed {new_val!r} was reported by no source "
                              f"(sources said {sorted(allowed) or 'nothing'})")
                continue

        applied.append((f, {
            "disposition": new_disp,
            "proposed_value": new_val,
            "rationale": rationale,
            "priority": a.get("priority"),
            "adjudicated": True,
        }))

    unadjudicated = [k for k, f in by_key.items()
                     if f["needs_judgment"] and k not in {(a.get("account_id"), a.get("field")) for a in adj}]
    return applied, errors, unadjudicated


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--template", action="store_true")
    ap.add_argument("--findings", default="findings.json")
    ap.add_argument("--adjudications", default="adjudications.json")
    args = ap.parse_args()

    run = json.load(open(args.findings))
    findings = run["findings"]

    if args.template:
        skeleton = [{"account_id": f["account_id"], "field": f["field"],
                     "_rule": f["rule_fired"], "_crm": f["old_value"],
                     "_source": f"{f['proposed_value']} (via {f['source']})",
                     "disposition": f["disposition"], "rationale": "", "priority": 0}
                    for f in findings if f["needs_judgment"]]
        json.dump(skeleton, open(args.adjudications, "w"), indent=2)
        print(f"wrote {len(skeleton)} open findings to {args.adjudications}")
        return 0

    try:
        adj = json.load(open(args.adjudications))
    except FileNotFoundError:
        print(f"{args.adjudications} not found — run with --template first")
        return 1

    leads = get_store().read("lead_data")
    applied, errors, missing = validate(findings, adj, leads)

    print(f"open findings: {sum(1 for f in findings if f['needs_judgment'])}  "
          f"submitted: {len(adj)}  accepted: {len(applied)}  rejected: {len(errors)}")

    for f, upd in applied:
        chg = "" if upd["disposition"] == f["disposition"] else f"  {f['disposition']} -> {upd['disposition']}"
        print(f"  OK       {f['account_id']} {f['field']:14}{chg}")

    for e in errors:
        print(f"  REJECTED {e}")

    for k in missing:
        print(f"  OPEN     {k[0]} {k[1]} — not adjudicated, stays as the rules left it")

    if errors:
        print("\nrejected adjudications are discarded; the rules' disposition stands")

    if args.check:
        return 1 if errors else 0

    for f, upd in applied:
        f.update(upd)

    run["adjudicated"] = True
    run["adjudications_accepted"] = len(applied)
    run["adjudications_rejected"] = len(errors)
    json.dump(run, open("findings.adjudicated.json", "w"), indent=2)
    print("\nwrote findings.adjudicated.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
