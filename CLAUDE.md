# stoside.data

Data workspace for Oceanside, CA municipal fiscal intelligence. Incrementally built as we uncover pieces of the city's municipal structure.

Part of the stoside ecosystem: this repo holds source data, extraction scripts, and structured outputs. The main stoside repo (when it exists) will consume these as inputs for the platform.

## Related Projects
- `yimby.watchdog`: meeting monitoring, structured extraction, PRA tracking
- `agent-knowledge-docs`: engineering patterns KB
- `policy-knowledge-docs`: policy analysis KB

## Knowledge Bases
For engineering tasks, fetch from agent-knowledge-docs:
`gh api repos/lacrx/agent-knowledge-docs/contents/{path}?ref=main -H "Accept: application/vnd.github.raw+json"`

For policy-adjacent work, fetch from policy-knowledge-docs:
`gh api repos/lacrx/policy-knowledge-docs/contents/{path}?ref=main -H "Accept: application/vnd.github.raw+json"`

Discovery: fetch `QUICK-REF.md` first, find matching row, fetch that path. Fallback to `TOPIC-INDEX.md`.

## Repo Structure

Each topic gets its own directory at the repo root:

```
{topic}/
  context.md        # what this dataset is, where it came from, what's been done
  scripts/           # extraction and transform scripts
  pdfs/              # source PDFs (gitignored — download via scripts)
  text/              # extracted text from PDFs
  *.json, *.csv      # structured extracts and datasets
  visuals/           # charts and analysis outputs
```

### Current Topics
- `budget_history/` — ACFRs, adopted budgets, quarterly reports, Strong Towns decoder
- `capital_improvements/` — CIP projects, funding, pavement backlog model
- `land_use/` — Oceanside General Plan (all elements), EIR, housing element
- `vote_history/` — city council voting records, per-meeting and per-member views

## What Gets Tracked vs Ignored

**Tracked:** scripts, context docs, extracted text, structured data (JSON/CSV), small visuals, inventories, analysis outputs.

**Gitignored:** source PDFs (reproducible via download scripts), generated databases (sqlite/duckdb), rendered page images, Python cache, large binary formats.

Principle: track anything that represents work done (extractions, analysis, scripts). Ignore anything that can be re-downloaded or regenerated.

## Conventions

### Adding a New Topic
1. Create `{topic}/` directory at repo root
2. Write `{topic}/context.md` explaining what data this covers, sources, and status
3. Put download/extraction scripts in `{topic}/scripts/`
4. Source PDFs go in `{topic}/pdfs/` (auto-gitignored)
5. Extracted/structured outputs at `{topic}/` root or organized subdirs

### Checks that run on their own

`vote_history/scripts/check_baseline.py` asserts that `parse_votes.py` still reproduces the
committed `vote_history/votes.csv`. Until 2026-11-22 nothing ran it, and GitHub Actions
cannot: `vote_history/pdfs/` is gitignored, so the 90 source PDFs exist on workhorse only.

It now runs weekly from a user systemd timer, installed by
`vote_history/deploy/install-timer.sh` (`--check` to see its state, `--uninstall` to remove
it). A failure raises `~/.claude/state/vote-baseline-alert.md` through `job-alert`, which
`claude-state-hook` injects at the start of the next Claude Code session; a clean run
deletes the file, so its presence is always the current state. Drift (exit 1) and
"could not run" (exit 2) are deliberately different alerts, because a check that is silently
not running must not read like a pass. Spec:
`docs/specs/2026-11-22-vote-baseline-watch.md`.

**`parse_votes.py` needs `pdfplumber`, and that is the repo's only third-party dependency.**
It lives in `.venv/` (gitignored), built from `vote_history/deploy/requirements.txt`. Do not
point a scheduled job at miniconda's interpreter: miniconda is first on an interactive PATH
and absent from a systemd user unit's, which is how the first scheduled run failed.

### Scripts
- Python 3.11+
- Type hints on function signatures
- Functions over classes
- pathlib for file paths
- PDF extraction via `claude -p` with structured JSON output schemas

### Data Formats
- JSON for structured extracts and inventories
- CSV for tabular data
- Markdown for context docs and meeting records
- Plain text for OCR/extracted text
- Parquet only when data volume warrants it (gitignored by default)
