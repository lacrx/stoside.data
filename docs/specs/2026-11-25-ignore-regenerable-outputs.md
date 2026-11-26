---
id: 2026-11-25-ignore-regenerable-outputs
tier: 2
status: accepted
quiet: yes
paths:
  - .gitignore
---

# Ignore what is regenerated or holds state, so the deploy clone stays clean

## Problem

Seventeen lines of `.gitignore` additions sat uncommitted in the shared clone on workhorse
from 2026-11-21 18:32 (file mtime) until 2026-11-25. The session record for that day,
`claude-brain/sessions/2026-11-21-c08202eb.md`, notes the clone was "already dirty before
this session (.gitignore, CLAUDE.md, votes.csv line endings ...)", and every session since
left it alone.

That matters now because this repository deploys from the clone: `vote-baseline-check.timer`
runs `vote_history/scripts/baseline-watch` straight from `~/repos/stoside.data`. `ship land`
fast-forwards that clone after a merge only when it has no tracked changes, so a dirty
`.gitignore` meant every future merge would report the deploy as failed. The `votes.csv`
change beside it was CRLF line endings only (`git diff -w` is empty; the 2026-11-21 record
confirms an identical md5 once CRLF is normalised) and was reverted, not committed.

`.gitignore` is a boundary file: an over-broad pattern can hide a file that should be
committed, and an absent one lets terraform state, which can carry secrets, be committed by
`git add -A`.

## Invariants

- **S1** WHEN this change is applied, no file already tracked SHALL become ignored.
- **S2** Terraform state, plans and local provider caches (`.terraform/`, `*.tfstate`,
  `*.tfstate.backup`, `*.tfplan`) SHALL be ignored, so `git add -A` cannot commit them.
- **S3** Only outputs a script in this repository regenerates SHALL be added: `**/exports/`,
  `infra/*.zip`, `infra/lambda/layer/`, and six `fiscal_analysis/*.json` products.

## Blast radius

Ignore rules only; no code or data changes. The worst case is an ignored file somebody
meant to commit, which shows as missing from a later diff rather than lost from disk, since
ignoring never deletes a working-tree file. A missing ignore rule costs more: a committed
`*.tfstate` is in history for good.

## Verification

| Invariant | How |
|---|---|
| S1 | `git ls-files -ci --exclude-standard` with the new `.gitignore` printed nothing on 2026-11-25. |
| S2 | The four terraform patterns are in the diff; `git check-ignore -v infra/terraform.tfstate` names the new line. |
| S3 | `git status --ignored=matching` lists the nine `fiscal_analysis/exports/*.parquet` files as ignored. Every named JSON is produced by a script under `fiscal_analysis/scripts/` (`compute_fiscal_productivity_v2.py`, `build_hcd_permits.py`, `estimate_market_values.py`, `prop13_fiscal_impact.py`; parquet by `export_parquet.py`), found by grep on 2026-11-25. **Caveat:** most of those scripts are themselves untracked in the shared clone, so the outputs are regenerable on workhorse and not yet from a fresh clone. Committing the scripts is separate work for whoever owns them. |

## Rejected

- **Discarding the lines.** They are correct and cover terraform state; throwing them away
  only to get a clean tree would reopen the secret-commit risk.
- **Committing the CRLF `votes.csv`.** It is the committed baseline `check_baseline.py`
  compares against. Changing its line endings is churn with no content change, and it is
  reverted instead.
- **Making `ship land` tolerate a dirty clone.** It would then fast-forward over someone's
  uncommitted work, or leave production on an old commit while reporting success.
