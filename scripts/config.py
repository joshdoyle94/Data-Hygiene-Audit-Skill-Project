"""
Configuration for the RIA account hygiene skill.

Everything tunable lives here. No thresholds, precedence orders, or picklist
values are hardcoded in the logic — a RevOps owner should be able to change how
the system behaves without reading Python.
"""

# --- backend ---------------------------------------------------------------
# "csv"    -> read/write ./data/*.csv          (no credentials, used for dev)
# "sheets" -> read/write a Google Sheet        (requires gspread + service acct)
BACKEND = "sheets"

DATA_DIR = "data"
SHEET_NAME = "ria-hygiene"          # spreadsheet title, sheets backend only
SERVICE_ACCOUNT_FILE = "service_account.json"

TABS = {"accounts": "accounts", "lead_data": "lead_data", "audit_log": "audit_log"}

# --- source precedence (the waterfall) -------------------------------------
# First source in this list with a non-blank value for a field wins that field.
# This is a business decision about who we trust, made once. Reorder freely.
SOURCE_PRECEDENCE = ["vendor_a", "vendor_b", "web_crawl"]

# --- field mapping ---------------------------------------------------------
FIELD_MAP = {
    "industry":      "industry_reported",
    "num_advisors":  "employee_count",
    "custodian":     "custodian_reported",
    "service_model": "service_model_reported",
    "tax_services":  "tax_services_reported",
    "fee_model":     "fee_model_reported",
}

NUMERIC_FIELDS = {"num_advisors"}

# --- thresholds ------------------------------------------------------------
# Days a rep_verified claim outranks source data. Past this it is "decayed":
# still enough to block an automatic write, not enough to suppress the finding.
FRESHNESS_WINDOW_DAYS = 180

# Lead rows observed longer ago than this describe a different company.
MAX_OBSERVATION_AGE_DAYS = 548          # ~18 months

# Materiality, not statistics: how far a headcount must drift before it is
# worth a rep's attention. Tune to the book.
NUMERIC_DRIFT_THRESHOLD = 0.25

# Two sources "agree" on a count when they are this close. Vendors round and
# sample at different times; exact equality would corroborate nothing.
NUMERIC_AGREEMENT_TOLERANCE = 0.10

# --- placeholders ----------------------------------------------------------
# Treated as "no value". Case-insensitive, whitespace-stripped.
PLACEHOLDERS = {"", "n/a", "na", "unknown", "-", "--", "tbd", "null", "none"}

# ...except where a token is a legitimate value. `tax_services = None` means the
# firm offers no tax services. Overwriting that destroys real data.
VALID_VALUES_OVERRIDING_PLACEHOLDER = {"tax_services": {"none"}}

# --- provenance ------------------------------------------------------------
# bulk_import carries no verification: a migration stamps every record with the
# load date, so last_verified reports when the rows moved, not when anyone
# checked them. Treat the date as absent.
PROVENANCE_WITH_NO_CLAIM = {"bulk_import", ""}
PROVENANCE_HUMAN_CLAIM = {"rep_verified"}

# --- taxonomy --------------------------------------------------------------
# Vocabulary differences, not disagreements. Mapping these is reconciliation,
# and the result is MATCH, not a fix.
INDUSTRY_SYNONYMS = {
    "financial services": "Financial Services",
    "investment management": "Financial Services",
    "wealth management": "Financial Services",
    "investment advisory": "Financial Services",
    "financial planning": "Financial Services",
}

# service_model deliberately gets NO synonym map. Ongoing Advisory, Standalone
# Planning and Hybrid describe different businesses; a mismatch there is a real
# conflict to route, not a vocabulary problem to reconcile.
NO_SYNONYM_FIELDS = {"service_model", "custodian", "fee_model", "tax_services"}

# Suffixes stripped before comparing firm names for entity identity.
NAME_NOISE = ["llc", "inc", "inc.", "l.l.c.", "ltd", "lp", "llp", "the",
              "advisors", "advisers"]
