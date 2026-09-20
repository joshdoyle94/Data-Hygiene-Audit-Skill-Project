#!/usr/bin/env python3
"""
Audit CRM accounts against lead data.

Deterministic end to end. Emits findings.json. Nothing here calls a model and
nothing here writes to the system of record -- audit.py only ever reads.

Findings marked needs_judgment carry a provisional disposition so a standalone
run is still complete; the agent may change those and only those.
"""

import json
import sys
from datetime import date, datetime

import config
from store import get_store

TODAY = date(2026, 9, 20)     # pinned so demo output is reproducible


# ----------------------------------------------------------------- helpers
def norm(v):
    return str(v or "").strip()


def is_placeholder(value, field):
    v = norm(value).lower()
    if v in config.VALID_VALUES_OVERRIDING_PLACEHOLDER.get(field, set()):
        return False
    return v in config.PLACEHOLDERS


def parse_date(v):
    try:
        return datetime.strptime(norm(v), "%Y-%m-%d").date()
    except ValueError:
        return None


def days_since(v):
    d = parse_date(v)
    return None if d is None else (TODAY - d).days


def canon(value, field):
    """Fold vocabulary differences. Only where a synonym map exists."""
    v = norm(value)
    if field in config.NO_SYNONYM_FIELDS:
        return v
    return config.INDUSTRY_SYNONYMS.get(v.lower(), v)


def canon_name(name):
    v = norm(name).lower().replace(",", " ").replace(".", " ").replace("&", "and")
    parts = [p for p in v.split() if p not in config.NAME_NOISE]
    return " ".join(parts)


def to_num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------- reconciling
def waterfall(rows, field):
    """
    First source in precedence order with a non-blank value wins.
    Returns (value, source, source_url, observed_at, corroborated).
    """
    col = config.FIELD_MAP[field]
    fresh = []
    for r in rows:
        age = days_since(r.get("observed_at"))
        if age is None or age > config.MAX_OBSERVATION_AGE_DAYS:
            continue
        if is_placeholder(r.get(col), field):
            continue
        fresh.append(r)

    if not fresh:
        return None, None, None, None, False

    winner = None
    for src in config.SOURCE_PRECEDENCE:
        for r in fresh:
            if norm(r.get("source")) == src:
                winner = r
                break
        if winner:
            break
    if winner is None:
        winner = fresh[0]

    win_val = canon(winner.get(col), field)

    # Corroboration: does another source say the same thing? For a count,
    # "the same" means within tolerance -- vendors round and sample at
    # different times, so exact equality would never corroborate anything.
    def agrees(r):
        if norm(r.get("source")) == norm(winner.get("source")):
            return False
        other = canon(r.get(col), field)
        if field not in config.NUMERIC_FIELDS:
            return other == win_val
        a, b = to_num(other), to_num(win_val)
        return a is not None and b not in (None, 0) and abs(a - b) / b <= config.NUMERIC_AGREEMENT_TOLERANCE

    corroborated = any(agrees(r) for r in fresh)
    return (win_val, norm(winner.get("source")), norm(winner.get("source_url")),
            norm(winner.get("observed_at")), corroborated)


def classify(crm_value, src_value, field):
    if is_placeholder(crm_value, field):
        return "gap", None
    if field in config.NUMERIC_FIELDS:
        a, b = to_num(crm_value), to_num(src_value)
        if a is None or b is None:
            return "match", None
        if b == 0:
            return "match", None
        drift = abs(a - b) / b
        return ("stale", drift) if drift > config.NUMERIC_DRIFT_THRESHOLD else ("match", drift)
    return ("match", None) if canon(crm_value, field) == src_value else ("conflict", None)


# -------------------------------------------------------------- the gate
def gate(acct, field, defect, corroborated, identity_ok):
    """
    Ordered. First match wins. Returns (disposition, rule, needs_judgment).
    Only reached for a real discrepancy: caller has already discarded matches
    and the no-source cases.
    """
    if norm(acct.get("hygiene_override")).upper() == "TRUE":
        return "SKIP", "POLICY_LOCK", False

    if not identity_ok:
        return "SKIP", "IDENTITY_UNRESOLVED", True

    provenance = norm(acct.get("data_source"))
    verified_age = days_since(acct.get("last_verified"))
    human_claim = provenance in config.PROVENANCE_HUMAN_CLAIM
    # bulk_import voids the timestamp entirely
    if provenance in config.PROVENANCE_WITH_NO_CLAIM:
        verified_age = None

    if human_claim and verified_age is not None and verified_age <= config.FRESHNESS_WINDOW_DAYS:
        return "SKIP", "FRESH_HUMAN", False

    if defect == "conflict":
        return "REVIEW", "CONFLICT_NEEDS_HUMAN", True

    if human_claim:
        return "REVIEW", "DECAYED_HUMAN", False

    if corroborated:
        return "AUTO", "AUTO_ELIGIBLE", False

    return "REVIEW", "SINGLE_SOURCE", False


def _finding(run_id, acct, field, defect, src_value, disp, rule, judge,
             corrob, src, src_url, observed, drift):
    return {
        "run_id": run_id,
        "account_id": acct.get("account_id"),
        "domain": acct.get("domain"),
        "firm_name": acct.get("firm_name"),
        "field": field,
        "defect_class": defect,
        "old_value": norm(acct.get(field)),
        "proposed_value": src_value if disp != "SKIP" else "",
        "disposition": disp,
        "rule_fired": rule,
        "needs_judgment": judge,
        "corroborated": corrob,
        "source": src or "",
        "source_url": src_url or "",
        "observed_at": observed or "",
        "drift": round(drift, 3) if drift is not None else None,
        "provenance": norm(acct.get("data_source")),
        "last_verified": norm(acct.get("last_verified")),
        "rationale": "",
    }


# ------------------------------------------------------------------- main
def main():
    store = get_store()
    accounts = store.read("accounts")
    leads = store.read("lead_data")

    by_domain = {}
    for r in leads:
        by_domain.setdefault(norm(r.get("domain")), []).append(r)

    run_id = f"RUN-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    findings, matches = [], 0

    for acct in accounts:
        rows = by_domain.get(norm(acct.get("domain")), [])

        for field in config.FIELD_MAP:
            src_value, src, src_url, observed, corrob = waterfall(rows, field)
            crm_is_gap = is_placeholder(acct.get(field), field)

            # No source value. Only worth reporting if we wanted to fill a gap
            # and could not; a populated field with no source is not a finding.
            if src_value is None:
                if not crm_is_gap:
                    continue
                findings.append(_finding(run_id, acct, field, "gap", "", "SKIP",
                                         "NO_SOURCE", False, corrob, "", "", "", None))
                continue

            defect, drift = classify(acct.get(field), src_value, field)
            if defect == "match":
                matches += 1
                continue

            win = next((r for r in rows if norm(r.get("source")) == src), None)
            identity_ok = win is None or \
                canon_name(win.get("firm_name_reported")) == canon_name(acct.get("firm_name"))

            disp, rule, judge = gate(acct, field, defect, corrob, identity_ok)

            findings.append(_finding(run_id, acct, field, defect, src_value, disp,
                                     rule, judge, corrob, src, src_url, observed, drift))

    out = {"run_id": run_id, "generated": str(TODAY), "accounts": len(accounts),
           "fields_checked": len(accounts) * len(config.FIELD_MAP),
           "matches": matches, "findings": findings}
    with open("findings.json", "w") as f:
        json.dump(out, f, indent=2)

    from collections import Counter
    d = Counter(f["disposition"] for f in findings)
    c = Counter(f["defect_class"] for f in findings)
    r = Counter(f["rule_fired"] for f in findings)
    print(f"{run_id}  accounts={len(accounts)}  checks={out['fields_checked']}  matches={matches}")
    print(f"findings={len(findings)}  " + "  ".join(f"{k}={v}" for k, v in sorted(d.items())))
    print("  class: " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
    print("  rule:  " + "  ".join(f"{k}={v}" for k, v in sorted(r.items())))
    print(f"  needs_judgment={sum(1 for f in findings if f['needs_judgment'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
