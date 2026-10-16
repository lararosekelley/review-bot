<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg"
     width="48" height="48" alt="review-bot logo" />

# review-bot

> A simple, open-source AI code review helper

---

A GitHub Action that reviews your pull requests with Claude. Bring an Anthropic API key, pick a
model, and you get a bot that posts inline findings and one summary with a confidence score.

It is tuned for **signal over volume**. It does not restate your linter's results or other CI findings, and it does not
post a hypothesis it could not trace in the code. If the PR is clean, it says so in two lines.

The base prompt works with **no repo-specific configuration**. It orients itself in your repo
first, reading your agent docs and your CI workflows so it never reports what CI already catches.

Add a `REPO_NOTES.md` when you want to teach it your specifics and your coverage rules.

## Install

Add `ANTHROPIC_API_KEY` as a repository secret, then create
`.github/workflows/code-review.yml`:

```yaml
name: "Code Review Bot"

on:
  pull_request:
    types: [opened, ready_for_review]
  pull_request_review_comment:
    types: [created]
  issue_comment:
    types: [created]

permissions:
  contents: read
  pull-requests: write
  issues: write
  id-token: write
  actions: read

concurrency:
  group: code-review-${{ github.event.pull_request.number || github.event.issue.number }}-${{ github.event_name }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  review:
    uses: lararosekelley/review-bot/.github/workflows/review.yml@v1
    secrets:
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

The `permissions` block is required.

That's it! Opening a PR triggers a review; commenting `@bot review` on a PR runs
another one; replying `@bot` to one of its inline comments starts a conversation on that thread.

### Permissions

By default, only the **repo owner** can spend the API key. On a shared or org repo, widen it:

```yaml
with:
  allowed-associations: "OWNER,MEMBER,COLLABORATOR"
```

## Configure

| Input                  | Default                     | What it does                                                                                                                    |
| ---------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `model`                | `claude-sonnet-5-5`         | Any current model id. `claude-opus-5-5` is more thorough and costs more per PR.                                                 |
| `effort`               | `high`                      | `low`, `medium`, `high`, `xhigh`, or `""` to leave it unset. `xhigh` is the most thorough and the most expensive.               |
| `passes`               | `1`                         | Independent review passes, run in parallel. With more than one, only findings raised by at least `min-votes` passes are posted. |
| `min-votes`            | auto                        | Passes that must raise a finding. Defaults to 1 for a single pass, 2 otherwise.                                                 |
| `merge-model`          | `claude-haiku-4-5-20251001` | Model that groups duplicate findings across passes.                                                                             |
| `bot-name`             | `Code Review Bot`           | The name it signs the summary with.                                                                                             |
| `repo-notes-file`      | –                           | Path to your repo-specific notes, e.g. `.github/review-bot/REPO_NOTES.md`.                                                      |
| `repo-notes`           | –                           | The same thing inline, for a few lines you do not want in a file.                                                               |
| `trigger-phrase`       | `@bot`                      | A comment with this phrase plus `review` runs a re-review; other mentions get a reply.                                          |
| `allowed-associations` | `OWNER`                     | Comma-separated author associations allowed to trigger it. No spaces.                                                           |
| `timeout-minutes`      | `20`                        | Job timeout.                                                                                                                    |
| `footer`               | advisory notice             | Line appended to the summary. Set to `""` to omit.                                                                              |
| `extra-allowed-tools`  | –                           | Extra tools appended to the allowlist.                                                                                          |

Need custom triggers - branch filters, a different event set, extra steps in the job? Skip the
reusable workflow and call the action directly. See [`examples/action.yml`](examples/action.yml).

## Repo notes

The base prompt carries the philosophy, the finding categories, the review workflow, the scoring,
and the output format. Your notes carry only what it cannot safely infer in one pass:

- **The stack**, especially where it would guess wrong
- **What CI already covers**, so it never duplicates it
- **What CI cannot cover**, which is where your repo actually breaks
- **Your seams**: the one module allowed to shell out, where config comes from, what layer owns what
- **A coverage matrix**: which kind of change requires which kind of test, in your vocabulary
- **Repo-specific non-findings**: the things that look wrong but are conventions here

Start from [`examples/REPO_NOTES-template.md`](examples/REPO_NOTES-template.md). Two worked
examples: a [Rust CLI](examples/REPO_NOTES-rust-cli.md) and a
[server-rendered web app](examples/REPO_NOTES-web-app.md).

## How it works

[`prompts/BASE_PROMPT.md`](prompts/BASE_PROMPT.md) is the review agent's complete instructions. The
action assembles the final prompt from it, your notes, and the PR context, then hands it to
`claude -p` with a read-only tool allowlist and a JSON schema. The model returns its findings as data
and never writes to the PR: [`scripts/review.py`](scripts/review.py) places each finding on the diff,
posts them as one review, and keeps one summary comment per PR up to date. With `passes` above 1,
the passes run in parallel and a merge step groups duplicates and drops findings too few passes
raised. Replies to comments go through
[`anthropics/claude-code-action`](https://github.com/anthropics/claude-code-action).

The agent's first step is orientation: it reads `CLAUDE.md` / `AGENTS.md` / `CONTRIBUTING.md` and
your `.github/workflows/` to learn what CI checks, because **whatever CI checks, it never mentions**.
Then it gathers the diff and check results, gates on requirements, checks for existing patterns,
traces data flow, applies a strict kill filter, and reports what survives.

Everything it can find is worth a comment only if you would ask for a change. That single rule is
what keeps the reviews readable.

## Costs and limits

- Every review is one API call chain per pass against **your** key. `claude-opus-5-5` at `xhigh` on a large
  diff is the expensive option; `claude-sonnet-5-5` with `effort: ""` is the cheap one.
- The default gating exists because a review costs money. Widen `allowed-associations`
  deliberately.
- Secrets are not available to `pull_request` runs from forked repositories, so the bot does not run
  on fork PRs. That is a safety property, not a bug: a fork PR could otherwise edit your
  `repo-notes-file` and rewrite the reviewer's instructions.
- Findings are advisory. The bot has no approval or merge rights, and the workflow requests none.

## Contributing

```sh
npm install            # dev deps, and wires the git hooks via husky
npm run lint           # markdownlint + actionlint + shellcheck
npm run lint:md        # markdown only
npm run lint:actions   # workflows only, examples included
npm run lint:sh        # scripts/ and the git hooks
```

`lint:actions` and `lint:sh` need [actionlint](https://github.com/rhysd/actionlint/blob/main/docs/install.md)
and [shellcheck](https://github.com/koalaman/shellcheck#installing) on your `PATH`. Both are native
binaries rather than npm deps, so the pre-commit hook skips a missing one with a note instead of
blocking your commit; CI always runs both, with actionlint pinned to a version.

The two tools cover different things, and the seam between them is why the shell lives where it
does. actionlint lints **workflows** - and, with shellcheck present, the shell inside their `run:`
blocks. It does not lint action *metadata*: hand it `action.yml` and it emits nonsense about a
missing `jobs:` section, so the globs in `lint:actions` exclude it deliberately. That would leave
the action's own shell unchecked, so it is not inline in `action.yml` at all - it lives in
[`scripts/`](scripts/), where shellcheck lints it directly. `npm test` runs the unit tests for
`scripts/review.py`.

Commits follow [Conventional Commits](https://www.conventionalcommits.org) with a required scope
drawn from [`commitlint.config.cjs`](commitlint.config.cjs) - `prompt`, `action`, `workflow`,
`examples`, and so on. `npm install` wires the hook that enforces it locally; CI enforces it again
on every PR.

Changes to [`prompts/BASE_PROMPT.md`](prompts/BASE_PROMPT.md) are the ones worth arguing about. The
bar is whether the change raises signal, and whether it stays repo-agnostic: anything that only
applies to one stack belongs in an `examples/REPO_NOTES-*.md` instead.

## License

[MIT License](LICENSE). Developed by Lara Kelley in 2026.
