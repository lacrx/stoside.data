---
id: 2026-11-22-vote-baseline-watch
tier: 2
status: accepted
quiet: yes
paths:
  - vote_history/scripts/baseline-watch
  - vote_history/deploy/vote-baseline-check.service
  - vote_history/deploy/vote-baseline-check.timer
  - vote_history/deploy/install-timer.sh
  - vote_history/deploy/requirements.txt
---

# A regression check nothing runs is a comment

## Problem

`vote_history/scripts/check_baseline.py` asserts that `parse_votes.py` still reproduces the
committed `vote_history/votes.csv` row for row. It works: run by hand on 2026-11-22 it
parsed the 90 source PDFs in 2m32s and reported `baseline 1267 rows, parsed 1267 rows` /
`OK: the parse reproduces the committed baseline exactly`.

**Nothing ran it.** Checked on 2026-11-22: no entry in `crontab -l`, no unit in
`systemctl --user list-timers`, and `.github/workflows/` does not exist in this repository.
A repository-wide grep for `check_baseline` returns only its own docstring and one comment
in `parse_votes.py`. It has existed as a capability and never as a check.

GitHub Actions cannot close the gap either. `vote_history/pdfs/` is gitignored, so the 90
source PDFs exist on workhorse and nowhere a runner can reach. The check is local by
construction, which is exactly why it needed a local scheduler rather than a workflow.

Two failures it is watching for, and only one is a code change:

- somebody edits `parse_votes.py` and the committed CSV no longer reproduces
- nobody edits anything and a dependency or interpreter upgrade moves PDF text extraction
  underneath an unchanged parser

The second is the reason this runs on a clock rather than from a git hook, and it is the one
nobody would think to check by hand.

Writing this found a third thing, which is the same class of problem one level down.
`parse_votes.py:36` imports `pdfplumber`, its only third-party dependency, and it was
installed only in miniconda. miniconda is first on an interactive PATH and is not on a
systemd user unit's, so the first scheduled run raised a real alert reading
`ModuleNotFoundError: No module named 'pdfplumber'`. The delivery chain worked on its first
genuine failure; the repository simply had no reproducible environment for the check to run
in.

## Invariants

- **S1** WHILE the timer is installed, `check_baseline.py` SHALL run weekly on workhorse
  without anybody typing it.
- **S2** WHEN the check does not reproduce the baseline (exit 1), an alert SHALL be raised
  naming the drift and how to re-record it deliberately.
- **S3** WHEN the check cannot reach a verdict (exit 2), a *different* alert SHALL be
  raised, because a check that is silently not running is the state this replaces and must
  not look like a pass.
- **S4** WHEN the check reproduces the baseline, any existing alert SHALL be cleared, so the
  file's presence always means the current state.
- **S5** The check SHALL NOT write `votes.csv`, so a failing run cannot destroy the baseline
  it is checking.
- **S6** `baseline-watch` SHALL resolve `job-alert` by absolute path and SHALL refuse to run
  at all if it cannot find it, because a weekly check that delivers nowhere is the problem
  being fixed.
- **S7** The parser's third-party dependency SHALL be pinned in a committed requirements
  file and run from the repository's own `.venv`, not from whichever interpreter happens to
  be first on PATH.

## Blast radius

Read-only with respect to the data. `check_baseline.py` parses into a temp directory and
compares; nothing in `vote_history/` is written by any of this. The worst outcome of a bug
here is a false alert, and the alert states that the baseline was not touched.

Cost: a full core for 2m55s and 517 MB peak, once a week, at `Nice=10` and
`IOSchedulingClass=idle`, scheduled Saturday 07:20 to stay clear of the `civic-pipeline`
cron (18:00 Tue–Fri and 01:00 daily) in the sibling repository. `TimeoutStartSec` was 300
until that measurement, which it cleared by 25 seconds; a niced single-threaded run on a
busy machine would have exceeded it and been reported as a failed check rather than a slow
one, so it is 600.

`.venv/` is gitignored and so is not reproducible from a clone alone;
`vote_history/deploy/requirements.txt` plus two lines in the installer are what make it so,
and a machine without it fails loudly under S3 rather than quietly skipping.

Weekly is a deliberate ceiling. What this watches changes rarely, and running it nightly
would spend fifteen minutes of CPU a week to learn the same thing.

## Verification

| Invariant | How |
|---|---|
| S1 | `install-timer.sh` copies both units into `~/.config/systemd/user/`, reloads and enables the timer; `--check` prints `list-timers` and the service status. Installed 2026-11-22, next run `Sat 2026-11-28 07:26 PST`. Started once through systemd rather than by hand, which is the path with no profile and no interactive PATH: `Result=success`, `ExecMainStatus=0`, `Consumed 2min 55.296s CPU time, 516.8M memory peak`. |
| S2 | Exit 1 branches to the drift alert. The real tree reproduces the baseline, so exit 1 was exercised by pointing the check at a mutated copy of `votes.csv`: one changed cell produced `CHANGED`, `FAIL: 0 count changes, ...` and a raised `vote-baseline-alert.md` carrying the re-record command. |
| S3 | Exercised for real, unintentionally: the first run under `/usr/bin/python3` exited 2 with `ModuleNotFoundError: No module named 'pdfplumber'` and raised the exit-2 alert. Its advice then named only missing PDFs, so the text now covers both causes. |
| S4 | After the venv was built, the clean run exited 0 and `job-alert list` reported no alerts. |
| S5 | Unchanged property of `check_baseline.py`: it parses into `tempfile.TemporaryDirectory()` and only `--update` writes the baseline. `baseline-watch` never passes `--update`. |
| S6 | `find_job_alert` tries `~/.local/bin/job-alert` then `~/vault/claude-brain/tools/job-alert` then PATH; with all three absent the script prints `job-alert not found; nothing would be delivered. Not running.` and exits 2. `install-timer.sh` refuses to install in that state. |
| S7 | `.venv/bin/python3 -c "import pdfplumber"` reports 0.11.11 on Python 3.12.3. `vote_history/deploy/requirements.txt` is `pip freeze` from that venv. `baseline-watch` prefers `$REPO/.venv/bin/python3` over the system interpreter. |

Delivery itself is specified in `yimby.watchdog`'s `docs/specs/2026-11-22-alert-delivery.md`:
`job-alert` writes `~/.claude/state/vote-baseline-alert.md`, which `claude-state-hook`
injects at the start of the next Claude Code session on this machine. It was exercised under
`bash:3.2` in Docker, which is neo's shell.

## Rejected

- **A GitHub Actions workflow.** `vote_history/pdfs/` is gitignored, so a runner has no
  PDFs to parse. Committing 90 PDFs to make CI possible trades a real repository size cost
  for a check that already has a machine to run on.
- **A pre-commit or pre-push hook on `parse_votes.py`.** It would catch the parser edit and
  not the dependency drift, which is the half nobody would check by hand. It also puts two
  and a half minutes in front of a commit, which is how a hook gets bypassed.
- **A nightly timer.** Fifteen minutes of CPU a week for the same answer. The thing being
  watched changes on the order of months.
- **Running it only when `parse_votes.py` has changed since the last green run.** Cheap and
  it forfeits exactly the failure that motivated the clock: an unchanged parser whose output
  moved because something underneath it did.
- **Installing `pdfplumber` into miniconda and pointing the unit there.** It is what already
  existed and it is why the first run failed. A scheduled job should not depend on an
  interactive environment it cannot see.
- **Posting to the household Geoff page.** Same reasoning as the sibling spec: notices there
  are shown to both people, and a vote-parser regression is not household news.
