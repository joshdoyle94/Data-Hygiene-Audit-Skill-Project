#!/usr/bin/env python3
"""
Seed generator for the RIA data-hygiene skill.

Produces three CSVs (one per Google Sheet tab) plus a manifest of every
planted defect, so audit precision/recall can be stated honestly.

  accounts.csv   - the CRM mirror (degraded copy of truth)
  lead_data.csv  - vendor export: multi-source, conflicting, partial
  audit_log.csv  - headers only; written by the pipeline at runtime
  seed_manifest.json - ground truth + what was planted where
"""

import csv, json, random
from datetime import date, timedelta

random.seed(1994)
TODAY = date(2026, 9, 20)

# ---------------------------------------------------------------- truth set
# (firm, domain, industry, advisors, custodian, service_model, tax, fee)
TRUTH = [
    ("Creative Planning", "creativeplanning.com", "Financial Services", 340, "Schwab", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Mercer Advisors", "merceradvisors.com", "Financial Services", 290, "Fidelity", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Carson Group", "carsongroup.com", "Financial Services", 180, "Schwab", "Ongoing Advisory", "Referral Partner", "AUM Percentage"),
    ("Savant Wealth Management", "savantwealth.com", "Financial Services", 95, "Schwab", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Buckingham Strategic Wealth", "buckinghamstrategicwealth.com", "Financial Services", 130, "Fidelity", "Ongoing Advisory", "Referral Partner", "AUM Percentage"),
    ("Wealth Enhancement Group", "wealthenhancement.com", "Financial Services", 210, "Schwab", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Brighton Jones", "brightonjones.com", "Financial Services", 88, "Schwab", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Plancorp", "plancorp.com", "Financial Services", 42, "Schwab", "Ongoing Advisory", "Referral Partner", "AUM Percentage"),
    ("Abacus Wealth Partners", "abacuswealth.com", "Financial Services", 36, "Schwab", "Ongoing Advisory", "Referral Partner", "AUM Percentage"),
    ("Beacon Pointe Advisors", "beaconpointe.com", "Financial Services", 120, "Fidelity", "Ongoing Advisory", "Referral Partner", "AUM Percentage"),
    ("The Colony Group", "thecolonygroup.com", "Financial Services", 145, "Fidelity", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Cerity Partners", "ceritypartners.com", "Financial Services", 160, "Schwab", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Wealthspire Advisors", "wealthspire.com", "Financial Services", 110, "Pershing", "Ongoing Advisory", "Referral Partner", "AUM Percentage"),
    ("Sequoia Financial Group", "sequoia-financial.com", "Financial Services", 75, "Schwab", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Mariner Wealth Advisors", "marinerwealthadvisors.com", "Financial Services", 250, "Schwab", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Kayne Anderson Rudnick", "kar.com", "Financial Services", 64, "Fidelity", "Ongoing Advisory", "None", "AUM Percentage"),
    ("Halbert Hargrove", "halberthargrove.com", "Financial Services", 22, "Schwab", "Ongoing Advisory", "Referral Partner", "AUM Percentage"),
    ("Baker Boyer", "bakerboyer.com", "Financial Services", 18, "Pershing", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Facet", "facet.com", "Financial Services", 130, "Fidelity", "Standalone Planning", "None", "Flat Fee"),
    ("Domain Money", "domainmoney.com", "Financial Services", 24, "Altruist", "Standalone Planning", "None", "Flat Fee"),
    ("Zoe Financial", "zoefin.com", "Financial Services", 40, "Altruist", "Hybrid", "Referral Partner", "AUM Percentage"),
    ("Altfest Personal Wealth Management", "altfest.com", "Financial Services", 28, "Schwab", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Gerber Kawasaki", "gerberkawasaki.com", "Financial Services", 32, "Schwab", "Ongoing Advisory", "Referral Partner", "AUM Percentage"),
    ("Rebalance", "rebalance360.com", "Financial Services", 20, "Schwab", "Ongoing Advisory", "None", "AUM Percentage"),
    ("Modera Wealth Management", "moderawealth.com", "Financial Services", 58, "Schwab", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Yeske Buie", "yebu.com", "Financial Services", 9, "Schwab", "Ongoing Advisory", "Referral Partner", "Flat Fee"),
    ("Arnerich Massena", "arnerichmassena.com", "Financial Services", 26, "Fidelity", "Ongoing Advisory", "None", "AUM Percentage"),
    ("Sullivan Bruyette Speros & Blayney", "sbsbfinancial.com", "Financial Services", 48, "Schwab", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Aspiriant", "aspiriant.com", "Financial Services", 105, "Fidelity", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Laird Norton Wealth Management", "lairdnortonwm.com", "Financial Services", 62, "Schwab", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Pure Financial Advisors", "purefinancialadvisors.com", "Financial Services", 44, "Schwab", "Hybrid", "In-House", "AUM Percentage"),
    ("Wetherby Asset Management", "wetherby.com", "Financial Services", 38, "Fidelity", "Ongoing Advisory", "Referral Partner", "AUM Percentage"),
    ("SEIA", "seia.com", "Financial Services", 70, "Fidelity", "Ongoing Advisory", "Referral Partner", "AUM Percentage"),
    ("Chevy Chase Trust", "chevychasetrust.com", "Financial Services", 34, "Pershing", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Bone Fide Wealth", "bonefidewealth.com", "Financial Services", 3, "Altruist", "Hybrid", "None", "Subscription"),
    ("TrueWealth Management", "truewealthmanagement.com", "Financial Services", 14, "Schwab", "Ongoing Advisory", "Referral Partner", "AUM Percentage"),
    ("Merriman Wealth Management", "merriman.com", "Financial Services", 30, "Schwab", "Ongoing Advisory", "Referral Partner", "AUM Percentage"),
    ("Hemington Wealth Management", "hemingtonwm.com", "Financial Services", 11, "Schwab", "Ongoing Advisory", "Referral Partner", "Flat Fee"),
    ("Parsec Financial", "parsecfinancial.com", "Financial Services", 40, "Schwab", "Ongoing Advisory", "In-House", "AUM Percentage"),
    ("Cardinal Point Wealth", "cardinalpointwealth.com", "Financial Services", 16, "Schwab", "Hybrid", "In-House", "AUM Percentage"),
]

FIELDS = ["industry", "num_advisors", "custodian", "service_model", "tax_services", "fee_model"]

# defect profile per account index
PROFILE = {}
for i in range(len(TRUTH)):
    PROFILE[i] = "clean"
for i in [2, 7, 11, 16, 20, 25, 31, 38]:
    PROFILE[i] = "gap"
for i in [1, 9, 14, 22, 29, 33]:
    PROFILE[i] = "stale"
for i in [4, 18, 26, 36]:
    PROFILE[i] = "conflict"
for i in [12, 30]:
    PROFILE[i] = "protected_hard"      # hygiene_override = TRUE
for i in [5, 21]:
    PROFILE[i] = "protected_fresh"     # rep_verified, recent  -> SKIP
for i in [8, 27]:
    PROFILE[i] = "protected_stale"     # rep_verified, decayed -> REVIEW ceiling
for i in [17, 23, 34, 37]:
    PROFILE[i] = "no_coverage"

# bulk-migration overlay: last_verified is structurally unreliable on these
MIGRATION_DATE = "2025-03-15"
BULK_IMPORT = [0, 3, 6, 13, 24, 32]

PLACEHOLDERS = ["", "N/A", "Unknown", "-", "TBD"]
GAP_FIELDS = {2: ["custodian"], 7: ["service_model", "tax_services"], 11: ["fee_model"],
              16: ["custodian", "fee_model"], 20: ["tax_services"], 25: ["custodian"],
              31: ["fee_model"], 38: ["tax_services"]}
CONFLICT_FIELDS = {4: ("custodian", "Schwab"), 18: ("service_model", "Ongoing Advisory"),
                   26: ("tax_services", "In-House"), 36: ("fee_model", "Flat Fee")}
PROTECTED_FIELDS = {12: ("service_model", "Hybrid"), 30: ("tax_services", "Referral Partner"),
                    5: ("custodian", "Pershing"), 21: ("fee_model", "Flat Fee"),
                    8: ("custodian", "Fidelity"), 27: ("service_model", "Hybrid")}
STALE_DRIFT = {1: 0.55, 9: 0.60, 14: 0.50, 22: 0.65, 29: 0.58, 33: 0.62}

IND_VARIANTS = ["Financial Services", "financial services", "Investment Management",
                "Wealth Management", "Investment Advisory", "Financial Planning"]
SOURCES = ["vendor_a", "vendor_b", "web_crawl"]

accounts, leads, manifest = [], [], []
vid = 0

for i, (name, domain, ind, adv, cust, svc, tax, fee) in enumerate(TRUTH):
    p = PROFILE[i]
    aid = f"ACC-{1000+i}"
    row = {"account_id": aid, "firm_name": name, "domain": domain, "industry": ind,
           "num_advisors": adv, "custodian": cust, "service_model": svc,
           "tax_services": tax, "fee_model": fee,
           "last_verified": (TODAY - timedelta(days=random.randint(20, 150))).isoformat(),
           "data_source": "crm_manual", "hygiene_override": "FALSE"}
    planted = []

    truthmap = dict(zip(FIELDS, [ind, adv, cust, svc, tax, fee]))

    if i in BULK_IMPORT:
        row["data_source"] = "bulk_import"
        row["last_verified"] = MIGRATION_DATE

    if p == "gap":
        for f in GAP_FIELDS[i]:
            row[f] = random.choice(PLACEHOLDERS)
            planted.append({"field": f, "class": "gap", "truth": truthmap[f],
                            "expected_disposition": "AUTO_OR_REVIEW", "strict": False})
    elif p == "stale":
        row["num_advisors"] = max(1, int(adv * STALE_DRIFT[i]))
        row["last_verified"] = (TODAY - timedelta(days=random.randint(400, 900))).isoformat()
        planted.append({"field": "num_advisors", "class": "stale", "truth": adv,
                        "crm": row["num_advisors"], "expected_disposition": "AUTO_OR_REVIEW", "strict": False})
    elif p == "conflict":
        f, wrong = CONFLICT_FIELDS[i]
        row[f] = wrong
        planted.append({"field": f, "class": "conflict", "truth": truthmap[f],
                        "crm": wrong, "expected_disposition": "REVIEW", "strict": True})
    elif p == "protected_hard":
        f, wrong = PROTECTED_FIELDS[i]
        row[f] = wrong
        row["hygiene_override"] = "TRUE"
        planted.append({"field": f, "class": "protected_hard", "truth": truthmap[f],
                        "crm": wrong, "expected_disposition": "SKIP", "strict": True,
                        "why": "hygiene_override=TRUE is an absolute exclusion"})
    elif p == "protected_fresh":
        f, wrong = PROTECTED_FIELDS[i]
        row[f] = wrong
        row["data_source"] = "rep_verified"
        row["last_verified"] = (TODAY - timedelta(days=random.randint(15, 120))).isoformat()
        planted.append({"field": f, "class": "protected_fresh", "truth": truthmap[f],
                        "crm": wrong, "expected_disposition": "SKIP", "strict": True,
                        "why": "rep_verified within 180d outranks vendor data"})
    elif p == "protected_stale":
        f, wrong = PROTECTED_FIELDS[i]
        row[f] = wrong
        row["data_source"] = "rep_verified"
        row["last_verified"] = (TODAY - timedelta(days=random.randint(300, 800))).isoformat()
        planted.append({"field": f, "class": "protected_stale", "truth": truthmap[f],
                        "crm": wrong, "expected_disposition": "REVIEW", "strict": True,
                        "why": "rep_verified but decayed past 180d — surface, never auto-write"})

    accounts.append(row)
    if planted:
        manifest.append({"account_id": aid, "domain": domain, "profile": p, "defects": planted})

    # ------------------------------------------------------------ lead rows
    if p == "no_coverage":
        manifest.append({"account_id": aid, "domain": domain, "profile": p,
                         "defects": [{"field": "*", "class": "no_source_coverage"}]})
        continue

    n_rows = random.choice([1, 2, 2, 3])
    for k in range(n_rows):
        vid += 1
        src = SOURCES[k % len(SOURCES)]
        obs_age = random.randint(5, 120) if k == 0 else random.randint(5, 500)
        r = {"vendor_record_id": f"V-{vid:04d}", "domain": domain,
             "firm_name_reported": name, "industry_reported": random.choice(IND_VARIANTS),
             "employee_count": adv, "custodian_reported": cust,
             "service_model_reported": svc, "tax_services_reported": tax,
             "fee_model_reported": fee, "source": src,
             "source_url": f"https://{domain}/about",
             "observed_at": (TODAY - timedelta(days=obs_age)).isoformat(),
             "vendor_confidence": round(random.uniform(0.55, 0.97), 2)}
        # realistic vendor noise: drop fields, jitter counts, disagree
        for f in ["custodian_reported", "tax_services_reported", "fee_model_reported",
                  "service_model_reported"]:
            if random.random() < 0.30:
                r[f] = ""
        if random.random() < 0.45:
            r["employee_count"] = max(1, adv + random.randint(-max(1, adv // 8), max(1, adv // 8)))
        if k > 0 and random.random() < 0.25:
            r["custodian_reported"] = random.choice(["Schwab", "Fidelity", "Pershing", "Altruist"])
        if random.random() < 0.12:
            r["firm_name_reported"] = name.replace(" LLC", "") + ", LLC"
        leads.append(r)

# name-mismatch case (rebrand) on one conflict account
leads.append({"vendor_record_id": f"V-{vid+1:04d}", "domain": "sbsbfinancial.com",
              "firm_name_reported": "SBSB Financial Advisors", "industry_reported": "Wealth Management",
              "employee_count": 48, "custodian_reported": "Schwab", "service_model_reported": "Ongoing Advisory",
              "tax_services_reported": "In-House", "fee_model_reported": "AUM Percentage",
              "source": "vendor_b", "source_url": "https://sbsbfinancial.com/about",
              "observed_at": (TODAY - timedelta(days=30)).isoformat(), "vendor_confidence": 0.91})

with open("data/accounts.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(accounts[0].keys())); w.writeheader(); w.writerows(accounts)

with open("data/lead_data.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(leads[0].keys())); w.writeheader(); w.writerows(leads)

with open("data/audit_log.csv", "w", newline="") as f:
    csv.writer(f).writerow(["run_id", "timestamp", "account_id", "domain", "field",
                            "old_value", "proposed_value", "disposition", "confidence",
                            "source", "source_url", "evidence", "rule_fired"])

with open("data/seed_manifest.json", "w") as f:
    json.dump({"generated_for": str(TODAY), "accounts": len(accounts),
               "scoring_note": ("gap and stale accept AUTO or REVIEW -- which one depends "
                                "on source coverage, not on correctness. conflict and the "
                                "three protected classes are strict: a wrong disposition "
                                "there is a safety failure, not a throughput difference."),
               "lead_rows": len(leads),
               "profile_counts": {p: sum(1 for v in PROFILE.values() if v == p)
                                  for p in set(PROFILE.values())},
               "planted": manifest}, f, indent=2)

print(f"accounts={len(accounts)} lead_rows={len(leads)} planted_accounts={len(manifest)}")
for p in sorted(set(PROFILE.values())):
    print(f"  {p:14} {sum(1 for v in PROFILE.values() if v == p)}")
