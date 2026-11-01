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
- **seeded**: a control PR with one injected defect that still builds and passes tests. `seed`
  holds the patch, the control it starts from, the kind of mutation, and the repo's test command.
  The mutations are modeled on real bugs in the source repos: a removed guard, an off-by-one bound,
  unescaped shell interpolation, an ignored parameter or flag. Seeded cases carry most of the
  recall measurement, since few historical bugs are plainly visible in their diff, and are scored
  separately from historical ones.

`split` is `dev` or `holdout`, assigned from a hash of the repo and PR head, so every bug from one
PR lands on the same side. A seeded case takes its control's split. Tune on `dev`; report `holdout`.

Cases are replayed and scored as units, one per PR head (`harness/units.py`). A PR that introduced
several bugs is reviewed once and scored against all of them. Each seeded case is a unit of its own.

`prior_bot` records whether the deployed bot caught the bug on the original PR, which gives a
baseline before any replay runs.

`mine/` holds the scripts that build historical cases and controls from git history and PR
metadata.

## Replay

`harness/replay.py` reviews a unit with the action's own scripts, locally: `assemble-prompt.sh` in
review mode, then `review.py find`, `merge`, and `post --dry-run`.

- The repo is cloned at the PR head with every ref except the PR branch and `origin/main` (the
  base) removed and unreachable objects pruned, so the fix is not in history. A seed is folded into
  the PR's last commit with its message, author, and dates kept, so the unseeded head is pruned too.
  Clones live in `~/.cache/review-bot-eval/work`, outside this repo, so the reviewer cannot reach
  the cases.
- `--passes`, `--min-votes`, and `--merge-model` set the pipeline as the action's inputs do.
- `claude -p` runs with an isolated `HOME` and `ANTHROPIC_API_KEY`, as in CI, so user settings,
  plugins, and memory do not leak in. The checkout's own `CLAUDE.md` still loads, as in CI.
- A fake `gh` answers `pr view`, `pr diff`, and `pr checks` from the case and the checkout, and
  refuses everything else. Checks always pass.
- The dry-run post places findings on the diff exactly as a real post would and writes them to
  `findings.jsonl` instead of posting them.
- The reviewer's `HOME`, `TMPDIR`, environment, and the fake tools sit in a private temp
  directory per run, holding only the PR's own fields, never the expected bugs.
- PR bodies are stored without git-stk's stack note, which is rewritten after merge and lists
  the later PRs that fixed the bugs.
- No GitHub token is passed, so a replay cannot write to GitHub.

Each run writes `findings.jsonl`, `summary.md`, `merged.json`, `meta.json` (status, cost, turns,
wall time per pass and overall), per-pass results and transcripts, and `gh.jsonl` under
`runs/<config>/<unit>/<rep>/`.

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

- Recall on historical and on seeded cases, by visibility and category.
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
- `harness/check_judge.py` checks the judge's triage calls against the labeled sample.
- `harness/sample_triage.py` writes a sample of the judge's triage calls to `labels/` for a person
  to label, to check the judge.
- `mine/run_all.py` rebuilds the cases from git history and PR metadata.
- `mine/check_seeds.py` checks that every seeded case still builds and passes its repo's tests; a
  seed the tests catch does not belong in the set.

## Fidelity check

`sandbox/smoke.py` runs the real action on the 10 smoke units in `sandbox/smoke.json` and compares
its reviews with the local replay of the same units. It covers what the replay fakes: posting the
review and inline comments through the GitHub API, updating the summary comment, and loading prior
findings on a re-review. Run it before each release and whenever the pinned Claude Code CLI version
changes:

1. Replay the smoke units locally at the release candidate:
   `replay.py $(sandbox/smoke.py cases) --reps 3 --config smoke-<version>`.
2. `sandbox/smoke.py push --ref <branch or sha>` opens one PR per unit in the public sandbox repo
   (`lararosekelley/review-bot-eval`), with the source repo's workflows replaced by one that runs
   the action at that ref. Only the repo owner's PRs and comments trigger it.
3. Once the reviews post, `sandbox/smoke.py compare eval/runs/smoke-<version>` flags any PR whose
   comment count falls outside the local reps' range or that lacks exactly one summary.
4. `sandbox/smoke.py rereview` asks each PR for a re-review; compare again, and read the re-review
   comments for prior findings closed or kept.
5. `sandbox/smoke.py close` closes the PRs and deletes their branches.

Each smoke PR spends the sandbox repo's own API key.
