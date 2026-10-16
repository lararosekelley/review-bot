# Changelog

What changed in each version, for the people using the action. Each section is drafted with
`git cliff` and then written up by hand; see [RELEASING.md](RELEASING.md). The release workflow
publishes the section matching the tag as the GitHub release notes, so headings must stay
`## X.Y.Z - YYYY-MM-DD`.

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
