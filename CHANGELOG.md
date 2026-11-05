# Changelog

What changed in each version, for the people using the action. Each section is drafted with
`git cliff` and then written up by hand; see [RELEASING.md](RELEASING.md). The release workflow
publishes the section matching the tag as the GitHub release notes, so headings must stay
`## X.Y.Z - YYYY-MM-DD`.

## 2.1.0 - 2026-11-05

### Changed

- The repo notes file and the agent-facing docs (`CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`) are
  read as they stand on the PR's base branch, so a PR cannot rewrite the rules it is reviewed by.
  The action fetches the base commit for this; if it cannot, both are read from the checkout as
  before. A notes file the PR adds takes effect once it is merged.
- The rules for findings, the kill filter, the confidence score, and the verify pass's rules moved
  to `prompts/rubric/`, so other tools can review by the same rules. The assembled review prompt is
  unchanged apart from the note above.

## 2.0.0 - 2026-11-03

### Added

- Reviews can run on models from OpenAI, Google, OpenRouter, xAI, Mistral, and DeepSeek. Set
  `harness: opencode`, name the model as `provider/model` (for example `openai/gpt-6.1-sol`), and
  pass that provider's key. Each provider has its own key input, so you can keep several and switch
  `model` between them. The model gets the same read-only tools as with Claude, and a repo's own
  opencode config is ignored. `opencode-version` pins the version.

### Changed

- Replies to comments run the same way as reviews: the model reads the thread and returns its reply,
  and the action posts it in the thread. A reply no longer reuses one sticky comment or adds fix
  links, and it reacts to the comment while it runs, like a re-review.
- `anthropic-api-key` is optional, since another provider's key can take its place.
- `merge-model` defaults to `model` when `harness` is `opencode`.

### Removed

- The `sticky-comment` and `include-fix-links` inputs. Remove them from your workflow if you set
  them; nothing else needs to change. Move from `@v1` to `@v2` to upgrade.

## 1.5.0 - 2026-11-02

### Changed

- Reviews post fewer comments, mostly fewer nits, and find as many real bugs. On the eval set,
  comments per PR fell by about a quarter, and the share of PRs with nothing worth changing that got
  no comments rose from about 1 in 5 to about 2 in 5.
- A new `verify` input, on by default, checks each finding against the code before posting and
  drops the ones it can rule out. It adds one call to each review that has findings, so a review
  costs about a third more. Set `verify: false` to skip it. The summary says how many findings it
  dropped, and the job log lists them.
- Architecture, complexity, and missing-coverage findings must name what goes wrong because of them,
  so the reviewer leaves out structural preferences and requests for tests on code that works.

### Fixed

- The reusable workflow now runs the action from its own release. Pinning an exact release, such as
  `@v1.5.0`, now pins both; before, the action always came from `@v1`.

## 1.4.0 - 2026-11-01

### Fixed

- With `passes` above 1, the step that groups duplicate findings across passes takes a few seconds
  instead of up to two and a half minutes, and keeps the same findings. If it takes longer than 60
  seconds, findings are grouped by location instead.

## 1.3.0 - 2026-10-25

### Changed

- The summary's cost line is now the PR's estimated cost and tokens so far, and expands to list each
  review's, oldest first. PRs reviewed before 1.3.0 start the total at their next review.
- A re-review's "Re-reviewed" comment includes the new confidence score and its change since the
  last review. The summary shows that change whenever there was an earlier review, not only when
  earlier findings were still open.
- The bot's comments carry the review-bot logo: before the name in the summary heading, and at the
  start of its inline findings, review, "Fixed" replies, and re-review comment.
- The default `footer` is now "Automated code review provided by review-bot. Findings are advisory
  and should be vetted.", linking to this repository.

## 1.2.2 - 2026-10-16

### Added

- The summary comment ends with the review's estimated cost and its tokens in (with how many were
  read from cache) and out, totaled across passes and the merge. `show-usage: false` leaves it out.
  The job's step summary always has the same numbers, per pass.

## 1.2.1 - 2026-10-16

### Fixed

- A re-review requested with `@bot review` no longer looks like it did nothing. It reacts to the
  request while it runs (a thumbs up when done, a confused face if it fails), replies "Fixed" on each
  fixed finding's thread, and comments with a link to the updated summary when it has no new
  findings to post. It also resolves those threads when its token is allowed to; the default job
  token is not.
- A finding that was resolved, or answered "Fixed" by the bot, is no longer carried into later
  re-reviews. Replying on the thread after "Fixed" brings it back.
- File paths and categories in the summary come from the model, so they are shown as plain code
  text and cannot add formatting or links. The summary stays under GitHub's size limit on a review
  with many findings.

## 1.2.0 - 2026-10-16

### Added

- `passes` runs several independent reviews of a PR in parallel and posts only the findings that at
  least `min-votes` of them raised. It trims nitpicks at the cost of one review per pass. The
  default stays one pass. `merge-model` sets the model that groups duplicate findings.
- `claude-code-version` pins the Claude Code CLI the review runs.
- A re-review (`@bot review`) checks each earlier finding against the current code, reports it as
  fixed, still open, or not verifiable, and updates the summary comment with the change in
  confidence instead of posting a new one.

### Changed

- The model returns its findings as data and the action posts them: one review holding every inline
  comment, plus one summary comment per PR that later reviews update. Links in the summary point at
  the inline comments. A finding that cannot be placed on a changed line is listed in the summary
  rather than lost.
- Reviews run the Claude Code CLI directly; replies to comments still go through
  claude-code-action. Review comments no longer carry "Fix this" links, and there is no progress
  checklist while a review runs.
- The first review after upgrading posts a new summary comment. A summary left by an earlier version
  stays where it is.
- Text the bot posts has the API key and token values redacted.

### Fixed

- A comment on a PR from another repository no longer checks out that repository's code next to the
  API key; the review reads your base branch instead. On a PR from the same repository, a
  comment-triggered review now reads the PR's code rather than the default branch.

## 1.1.1 - 2026-10-14

### Changed

- The action is named Low-Noise Code Review, so it can be listed on the GitHub Marketplace. Callers
  do not need to change anything: `lararosekelley/review-bot@v1` and the reusable workflow at `@v1`
  keep working.

## 1.1.0 - 2026-10-01

### Changed

- The default model is `claude-sonnet-5-5` at `high` effort, in place of `claude-opus-5`. Set
  `model: claude-opus-5-5` for the most thorough reviews, or `effort: xhigh` to trade cost for
  depth. If you pinned `model` or `effort` only to get the defaults, you can remove them.

## 1.0.0 - 2026-09-07

### Added

- A GitHub Action that reviews pull requests with Claude and posts inline findings plus one summary
  with a confidence score, tuned to post only what is worth a change.
- A reusable workflow that gates reviews to the repository owner by default and re-reviews when a
  comment mentions `@bot`.
- Repo notes, from a file or inline, that teach the reviewer a codebase's specifics and coverage
  rules.
