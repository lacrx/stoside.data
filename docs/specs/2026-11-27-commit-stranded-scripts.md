---
id: 2026-11-27-commit-stranded-scripts
tier: 2
status: accepted
quiet: no
paths:
  - .gitignore
  - fiscal_analysis/scripts/
  - capital_improvements/extract_fy0608_vision.py
  - infra/outputs.tf
  - infra/.terraform.lock.hcl
  - infra/lambda/requirements.txt
---

# Commit the scripts and extracted text stranded in the shared clone

## Problem

On 2026-11-27 the shared clone `~/repos/stoside.data` carried 31 untracked paths, the
newest modified 2026-08-04. `docs/specs/2026-11-25-ignore-regenerable-outputs.md` already
named the gap in its S3 caveat: the scripts that regenerate the ignored
`fiscal_analysis/*.json` products are untracked, so those outputs can be rebuilt on
workhorse and not from a fresh clone. The rest was a mix of extracted text that sits beside
tracked text of the same shape (`budget_history/text/` has 378 tracked files), about 1.6 GB of
downloaded General Plan PDFs, five rendered HTML maps (69 MB) and a saved terraform plan.

Thomas asked the same day to clear long-dirty clones by keeping real work and discarding
the rest.

## Invariants

- **S1** The nine `fiscal_analysis/scripts/*.py`, `capital_improvements/extract_fy0608_vision.py`,
  `infra/outputs.tf`, `infra/.terraform.lock.hcl` and `infra/lambda/requirements.txt` SHALL be
  committed unchanged from the shared clone.
- **S2** The extracted text under `capital_improvements/text/`, `vote_history/text/` and
  `land_use/general_plan/text/` (about 22 MB, `.txt` plus `.meta.json`) SHALL be committed, matching
  `budget_history/text/`.
- **S3** The General Plan PDFs, `fiscal_analysis/visuals/` and `infra/tfplan` SHALL be ignored,
  and no file already tracked SHALL become ignored.
- **S4** No committed file SHALL contain a credential.
- **S5** WHEN this merges, the shared clone SHALL show no untracked or modified files.

## Blast radius

Additions plus three ignore rules. `vote-baseline-check.timer` runs `baseline-watch` from the
clone, and nothing it reads changes. The worst case is an ignored file somebody meant to keep,
which stays on disk, since ignoring never deletes. A committed `tfplan` would cost more: a plan
can carry resource values, and history is permanent, so it is ignored, not committed.

## Verification

| Invariant | How |
|---|---|
| S1 | Copied with `cp -p` from the shared clone; `python3 -m py_compile` passes on all ten scripts. |
| S2 | `git status` in the worktree lists the three `text/` folders; `du -sh` totals about 22 MB. |
| S3 | `git ls-files -ci --exclude-standard` prints nothing; `git ls-files -o --exclude-standard` in the shared clone, with this `.gitignore`, lists only the paths committed here. |
| S4 | `gitleaks detect --no-git` over every added file: no leaks found. |
| S5 | After merge and fast-forward: `git -C ~/repos/stoside.data status --porcelain` is empty. |

## Rejected

- **Deleting the PDFs to get a clean tree.** They took a crawl to fetch and the extracted text
  cites them. Ignoring keeps them on disk at no cost.
- **Committing the PDFs or the rendered maps.** 1.6 GB and 69 MB of regenerable bytes in
  history, in a repository whose `.gitignore` already says source PDFs are not tracked.
- **Running ruff fixes on the scripts.** The repository has no lint config or CI, and the
  tracked scripts fail the same checks. Reformatting someone's work in the commit that saves it
  hides what was saved.
