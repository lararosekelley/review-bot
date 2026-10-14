# Review eval harness

Measures how well the review prompt finds real defects, and how much noise it posts, so that
changes to the prompt, model, effort, harness, or review pipeline are compared on numbers.

## Cases

One JSON file per case in `cases/`. Cases from private repos go in `cases-private/`, which is
not committed.

- **historical**: a merged PR that introduced a bug a later PR fixed. `expected` names where the
  bug is (path, line at the PR head, window, alternative locations) and what it is.
  `visibility` is how plainly the bug shows in the PR's diff.
- **control**: a merged PR whose changed lines no later fix touches. `expected` is empty; every
  posted comment counts toward noise.
- **seeded** (not built yet): a control PR with one injected defect that still builds and passes
  tests. Seeded cases are meant to carry most of the recall measurement, since few historical bugs
  are plainly visible in their diff.

`split` is `dev` or `holdout`, assigned from a hash of the repo and PR head, so every bug from one
PR lands on the same side. Tune on `dev`; report `holdout`.

Cases are replayed and scored as units, one per PR head (`harness/units.py`). A PR that introduced
several bugs is reviewed once and scored against all of them.

`prior_bot` records whether the deployed bot caught the bug on the original PR, which gives a
baseline before any replay runs.

`mine/` holds the scripts that build historical cases and controls from git history and PR
metadata.

## Replay

`harness/replay.py` reviews a case the way the action does, locally:

- The repo is cloned at the PR head with every ref except the PR branch and `origin/main` (the
  base) removed and unreachable objects pruned, so the fix is not in history.
- The prompt and tool allowlist come from running `scripts/assemble-prompt.sh` itself.
- `claude -p` runs with an isolated `HOME` and `ANTHROPIC_API_KEY`, as in CI, so user settings,
  plugins, and memory do not leak in. The checkout's own `CLAUDE.md` still loads, as in CI.
- A fake `gh` answers `pr view`, `pr diff`, and `pr checks` from the case and the checkout, and
  refuses everything else. Checks always pass.
- A fake `github_inline_comment` MCP server with the action's schema records comments instead of
  posting them. It rejects lines outside the diff and buffers calls without `confirmed: true`,
  matching the action.
- No GitHub token is passed, so a replay cannot write to GitHub.

Each run writes `findings.jsonl`, `summary.md`, `meta.json` (status, cost, turns, tokens, wall
time), `transcript.jsonl`, and `gh.jsonl` under `runs/<config>/<case>/<rep>/`.

Repo notes come from the PR head (`--notes head`) or are left out (`--notes none`). Notes written
later are never used, because they may describe the bugs being measured.

## Scoring

1. Match: a fixed judge model, separate from the models under test, decides for every posted
   finding and every expected bug in the unit whether they describe the same defect (yes, partial,
   no). Location does not gate this, since a finding can name a bug from a call site. Pairs are
   assigned one to one, preferring yes over partial and the labeled location over elsewhere.
2. Location: whether a matched finding sits in the expected file within the window, or at a
   listed alternative, is reported as location accuracy.
3. Triage: unmatched findings are judged, with read access to the checkout, as valid but
   unlabeled, nit, or wrong.

Judge answers are cached per configuration, so scoring again costs nothing.

Existing bot comments on the original PRs, which carry outcomes (fixed, ignored, harmful), are
used to calibrate the judge.

## Metrics

- Recall on historical and seeded cases, by visibility and category.
- Noise: nits plus wrong findings per PR, and the share of controls with no findings.
- Location accuracy and format compliance (rejected or unconfirmed comments).
- Cost, tokens, turns, and wall time per review.

Each configuration runs 3 times per case. Configurations are compared with a paired bootstrap
over cases.

## Configurations

Model, effort, notes on or off, harness (Claude Code or opencode), and pipeline changes such as a
separate verification pass. A verification pass is judged on noise removed against recall lost.

## Tools

- `harness/replay.py` replays units for one configuration (`--split`, `--model`, `--effort`,
  `--reps`); finished runs are skipped, so an interrupted sweep resumes.
- `harness/score.py` scores a configuration and writes `scores.json`.
- `harness/compare.py` compares two configurations with a paired bootstrap over units.
- `harness/ensemble.py` estimates multi-pass reviews (union, or a 2-pass vote) from a
  configuration's independent reps.
- `harness/sample_triage.py` writes a sample of the judge's triage calls to `labels/` for a person
  to label, to check the judge.
- `mine/run_all.py` rebuilds the cases from git history and PR metadata.

## Fidelity check

A private sandbox repo runs the real action on about 10 smoke cases whenever the pinned
claude-code-action version changes, and compares its comments with the local replay of the same
cases. This covers what the replay fakes: sticky comments, comment buffering and classification,
and the action's own prompt wrapping.
