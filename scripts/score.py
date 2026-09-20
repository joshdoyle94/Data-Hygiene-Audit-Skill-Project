#!/usr/bin/env python3
"""
Score the audit against ground truth.

The seed manifest records every planted defect and the disposition it should
receive. Without this the audit can only report how many things it found, which
says nothing about whether it found the right things.
"""

import json
import sys
from collections import Counter


def main():
    manifest = json.load(open("data/seed_manifest.json"))
    run = json.load(open("findings.json"))

    truth = {}
    for a in manifest["planted"]:
        for d in a["defects"]:
            if d["field"] == "*":
                continue
            truth[(a["account_id"], d["field"])] = d

    found = {(f["account_id"], f["field"]): f for f in run["findings"]}

    tp = sorted(set(truth) & set(found))
    fn = sorted(set(truth) - set(found))
    fp = sorted(set(found) - set(truth))

    prec = len(tp) / len(found) if found else 0
    rec = len(tp) / len(truth) if truth else 0

    print(f"planted={len(truth)}  found={len(found)}")
    print(f"  detected      {len(tp)}")
    print(f"  missed        {len(fn)}")
    print(f"  unplanted     {len(fp)}")
    print(f"  precision     {prec:.0%}   recall {rec:.0%}")

    ok = bad = 0
    leaks = []
    print("\ndisposition vs. expected (planted defects only)")
    for k in tp:
        exp = truth[k].get("expected_disposition")
        got = found[k]["disposition"]
        strict = truth[k].get("strict", False)
        good = (got in ("AUTO", "REVIEW")) if exp == "AUTO_OR_REVIEW" else (got == exp)
        if good:
            ok += 1
        else:
            bad += 1
            tag = "SAFETY" if strict else "routing"
            print(f"  {tag:8} {k[0]} {k[1]:14} expected {exp:14} got {got:6} "
                  f"({found[k]['rule_fired']})")
        if strict and got == "AUTO":
            leaks.append(k)
    print(f"  correct {ok}   incorrect {bad}")

    print("\n--- safety ---")
    print(f"  protection leaks (protected/conflict record auto-written): {len(leaks)}")
    for k in leaks:
        print(f"    LEAK {k[0]} {k[1]}")

    if fn:
        print("\nmissed")
        for k in fn:
            print(f"  {k[0]} {k[1]:14} {truth[k]['class']}")

    if fp:
        print("\nunplanted findings (source disagreement on records that were correct)")
        for k in fp:
            f = found[k]
            print(f"  {k[0]} {k[1]:14} {f['defect_class']:9} -> {f['disposition']:6} "
                  f"({f['rule_fired']})  crm={f['old_value']!r} src={f['proposed_value']!r}")
        auto_fp = [k for k in fp if found[k]["disposition"] == "AUTO"]
        print(f"\n  of which AUTO (would have been written): {len(auto_fp)}")
        if auto_fp:
            print("  ^ dangerous: unplanted and auto-applied")

    print("\nrules fired: " + "  ".join(
        f"{k}={v}" for k, v in sorted(Counter(
            f["rule_fired"] for f in run["findings"]).items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
