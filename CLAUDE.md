# Repo notes for Claude Code

The skill lives at `.claude/skills/ria-account-hygiene/`. Run every command from the
repository root and export `PYTHONPATH=scripts` first, since the scripts import
`config` and `store` as siblings.

Do not edit `data/accounts.csv` directly. `scripts/apply.py` is the only writer.