"""
Storage adapter.

The audit logic never knows where records live. Swapping the sheet for
Salesforce means writing one more Store subclass, not editing audit.py.
"""

import csv
import os
import config


class Store:
    def read(self, tab):        raise NotImplementedError
    def update_row(self, tab, key_field, key, updates):  raise NotImplementedError
    def append(self, tab, rows):  raise NotImplementedError


class CsvStore(Store):
    """Local CSVs. No credentials. Used for development and for the demo run."""

    def _path(self, tab):
        return os.path.join(config.DATA_DIR, f"{config.TABS[tab]}.csv")

    def read(self, tab):
        with open(self._path(tab), newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def update_row(self, tab, key_field, key, updates):
        rows = self.read(tab)
        hit = False
        for r in rows:
            if r[key_field] == key:
                r.update(updates)
                hit = True
        if not hit:
            raise KeyError(f"{key_field}={key} not found in {tab}")
        with open(self._path(tab), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    def append(self, tab, rows):
        if not rows:
            return
        path = self._path(tab)
        with open(path, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))
        with open(path, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=header).writerows(
                [{k: r.get(k, "") for k in header} for r in rows]
            )


class SheetsStore(Store):
    """Google Sheets. Requires gspread + a service account with edit access."""

    def __init__(self):
        try:
            import gspread
        except ImportError:
            raise SystemExit(
                "BACKEND is 'sheets' but gspread is not installed.\n"
                "  pip install -r requirements.txt\n"
                "or set BACKEND = 'csv' in scripts/config.py to run without credentials."
            )
        self.gc = gspread.service_account(filename=config.SERVICE_ACCOUNT_FILE)
        # Opening by key needs only the Sheets API. Opening by title is a Drive
        # lookup, so it also requires the Drive API and survives a rename badly.
        key = getattr(config, "SHEET_KEY", "")
        self.sh = self.gc.open_by_key(key) if key else self.gc.open(config.SHEET_NAME)
        self._cache = {}

    def _ws(self, tab):
        if tab not in self._cache:
            self._cache[tab] = self.sh.worksheet(config.TABS[tab])
        return self._cache[tab]

    def read(self, tab):
        return self._ws(tab).get_all_records()

    def update_row(self, tab, key_field, key, updates):
        ws = self._ws(tab)
        header = ws.row_values(1)
        col = header.index(key_field) + 1
        try:
            cell = ws.find(str(key), in_column=col)
        except Exception:
            raise KeyError(f"{key_field}={key} not found in {tab}")
        payload = [
            {"range": f"{chr(64 + header.index(f) + 1)}{cell.row}", "values": [[v]]}
            for f, v in updates.items() if f in header
        ]
        if payload:
            ws.batch_update(payload)

    def append(self, tab, rows):
        if not rows:
            return
        ws = self._ws(tab)
        header = ws.row_values(1)
        ws.append_rows([[str(r.get(k, "")) for k in header] for r in rows],
                       value_input_option="RAW")


def get_store():
    return SheetsStore() if config.BACKEND == "sheets" else CsvStore()