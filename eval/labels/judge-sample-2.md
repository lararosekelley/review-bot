<!-- markdownlint-disable MD013 -->

# Judge calibration: judge-sample-2

Fill in each `label:` and leave it blank to skip. A triage item is a comment the reviewer posted
that matched no known bug; label it:

- valid: a real defect worth asking the author to change.
- nit: true, but not worth a requested change.
- wrong: false, or not supported by the code.

A match item pairs a comment with a known bug the judge says it found; label it:

- yes: the comment names the same defect.
- partial: same code and a related concern, but it misses what actually goes wrong.
- no: a different defect.

## 1. git-stk PR #102: `src/commands/run.rs:58` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/8dfcccc18afadbbcaf834ec2bf5485dab5b19efd/src/commands/run.rs#L58). PR title: feat(cli): git stk run command on all branches in stack

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** A mid-run checkout error discards all collected results.

`run_each` returns `Err` through `checkout(branch)?` when a later `git switch` fails, for example because the previous branch's run left tracked files modified. `result?` then exits before `print_summary`, so the user loses the pass/fail record for the branches that already ran. Treat a checkout failure as a failed branch or stop the loop, and always print the partial summary.

<!-- review-bot:finding n=1 -->
~~~~

Judge: **valid**. The claim holds. In run.rs:77, `checkout(branch)?` exits `run_each` with an error, so the results already collected are thrown away. Then `result?` at line 57 returns before `print_summary` runs. A command that modifies tracked files (for example a formatter or codegen) can easily make the next `git switch` fail. When that happens, the user loses the per-branch pass/fail summary, which is the main output of this command.

label:

## 2. navi PR #99: `crates/navi-notifier-github/tests/poll.rs:487` (match)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/21b051a9fa9b7abb3f0bd2430b188b548a92b8bc/crates/navi-notifier-github/tests/poll.rs#L487). PR title: fix(source): defer involved-sweep pr: cursors until delivery

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Missing Coverage]** No test covers the failed-scope hold-back for the new `pr:` cursor, which is the actual fix for #98.

Both new tests only call `commit_snapshots` with an empty `failed_scopes`. If the `failed_scopes.contains(&scope)` guard in the cursor flush were dropped, they would still pass, and the at-most-once loss would come back. The repo already tests this for snapshots in `failed_scope_snapshot_is_held_back` (around line 290). Add the same style of test here: commit with `HashSet::from(["acme/widgets#1".to_string()])` and assert `pr:acme/widgets#1` is still `None`. Do the same in the Gitea `poll.rs` test.

<!-- review-bot:finding n=0 -->
~~~~

Known bug, at `crates/navi-notifier-github/src/source.rs:405`: The pr: cursor is staged even when process_pr swallowed a fetch failure, so the PR is skipped until it changes again and its event is lost.

Judge: **partial**. The comment is about the same mechanism: holding back the pr: cursor when its scope failed. But it treats the bug as only a missing test and assumes the failed_scopes guard works. The real defect is that process_pr swallows fetch failures, so the scope is never marked as failed. The cursor gets staged anyway and the event is lost. The suggested test, which seeds failed_scopes by hand, would not catch this.

label:

## 3. navi commit a1a570c: `crates/navi-notifier/src/service.rs:134` (triage)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/a1a570cf8dedcaaa3b984e539c8f4ffbacf4b92f/crates/navi-notifier/src/service.rs#L134). PR title: feat(cli): add `navi service` to manage the background service

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Architecture]** `navi uninstall` doesn't stop or remove the service this PR adds, and can delete its env file.

`setup::uninstall` removes the config dir (`crates/navi-notifier/src/setup.rs:249-252`). That dir is where `navi.env` is created, so the token file is deleted. The unit, plist or task is left behind pointing at a config and binary that are about to go away. With `Restart=on-failure` / `KeepAlive` it then restart-loops forever. Either have `setup::uninstall` detect and remove the installed service (reusing `service::uninstall`, honouring `--dry-run` and `--yes`), or at least list it in the 'what will be removed' output and the final note.

<!-- review-bot:finding n=1 -->
~~~~

Judge: **valid**. `setup::uninstall` (setup.rs:207-252) runs `remove_dir_all` on the config dir and never checks for or removes the service. That config dir is where `navi.env` lives (service.rs:385). The installed unit, plist or task stays behind, still pointing at the deleted config, and it uses Restart=on-failure with RestartSec=10 or KeepAlive. With a 10s restart delay, systemd's default limit on rapid restarts never triggers, so the service keeps restarting. Users who run `navi uninstall` would hit this, and its 'what will be removed' list doesn't mention the service.

label:

## 4. git-stk PR #291: `src/stack/nav.rs:37` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/ecceadd60018090618a3e62f6bde29e4fbf67a6d/src/stack/nav.rs#L37). PR title: feat(cli): add --from-path to nav commands so cd can follow a branch

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Error Handling]** A `worktree_holding` error is swallowed with `.ok().flatten()`.

If `git worktree list` fails, the error is dropped and the code falls through to `checkout_silently`, which then prints `switched to` and `.`. Propagate the error with `?`. The caller is then told that the worktree lookup failed, and it is not told it landed in a branch that may be held elsewhere.

<!-- review-bot:finding n=2 -->
~~~~

Judge: **wrong**. If the lookup fails, the code falls through to `checkout_silently`. That function runs `git switch`, and git won't switch to a branch that's checked out in another worktree; the switch errors out and the error is propagated with `?`. So "switched to" and "." only print when the switch actually worked. The user can't end up "in a branch held elsewhere," as the comment claims. Dropping the lookup error just falls back to a normal checkout, which handles any error itself.

label:

## 5. git-stk PR #102: `src/commands/run.rs:81` (match)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/8dfcccc18afadbbcaf834ec2bf5485dab5b19efd/src/commands/run.rs#L78). PR title: feat(cli): git stk run command on all branches in stack

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Error Handling]** A spawn error (command not found, not executable) is reported as an ordinary FAIL with no message.

`.status().is_ok_and(...)` collapses the `io::Error` into `false`. A typo such as `git stk run -- crgo test` prints `FAIL` for every branch and ends with a generic "failed on one or more branches", with no hint that the program never started. Handle the `Err` case: report `failed to run `{program}`: {err}` and abort, since the failure is identical on every branch, rather than treating it as a per-branch result.

<!-- review-bot:finding n=2 -->
~~~~

Known bug, at `src/commands/run.rs:81`: run treats a command that fails to spawn (e.g. not found) as a failed run, reporting a bogus FAIL on every branch instead of the spawn error.

Judge: **yes**. The comment names the same defect as the known bug. It says a spawn error, such as a command that isn't found, gets collapsed into a plain FAIL on every branch and the spawn error itself never appears.

label:

## 6. git-stk PR #108: `src/commands/absorb.rs:146` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/9f132e1127636f9d3dfd6822bce101ec864188c8/src/commands/absorb.rs#L146). PR title: feat(cli): start on absorb command

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** Renamed-and-modified files are blamed under the new path, which does not exist in HEAD

`git diff` detects renames by default. For a staged rename with edits, `+++ b/new` sets `file` to the new path, but the hunk's pre-image lines live under the old path. `git blame HEAD -- new` fails, so `route` returns an error and the whole absorb aborts instead of skipping the hunk. Pass `--no-renames` in `diff_against_head`, or track the old path for blame.

<!-- review-bot:finding n=1 -->
~~~~

Judge: **valid**. The claim holds. `diff_against_head` runs `git diff --unified=0 [--cached] HEAD` without `--no-renames`, and Git turns on rename detection by default (diff.renames=true). For a staged `git mv` plus edits, `parse_hunks` takes `file` from the `+++ b/new` line and ignores `from_path` unless the target is /dev/null. `blame_line_shas` then runs `git blame HEAD -- new`, which fails because that path doesn't exist in HEAD. The `?` in `route` passes that error up through `collect::<Result<_>>()?`, so the whole command aborts, `--dry-run` included, instead of skipping the hunk. Nothing in the code or docs says this is intended, and renaming a file and then editing it is a common workflow.

label:

## 7. git-stk PR #372: `src/tour/plan.rs:227` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/4704dd414062c1265e0805b3138c017cec981c3b/src/tour/plan.rs#L227). PR title: feat(tour): plan agent tours with your own agent command

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** Positional step ids (`plan-N`) are reused across different plans of the same head, so stale "reviewed" marks land on the wrong step.

The page keeps reviewed marks in localStorage under `git-stk-tour:<headSha>` and keys them by `step.id` (template.html:1280, 1484). With `--refresh-plan`, a different `--plan` file, or an agent/instructions change on the same head, `plan-3` can be a different step from before. A step the reader never opened then shows as done. Derive the id from the step's content (for example a hash of its sorted file paths), or include a plan fingerprint in it, so a re-plan does not inherit marks.

<!-- review-bot:finding n=0 -->
~~~~

Judge: **valid**. The claim holds up. Plan step ids are numbered by position (`plan-N` at `src/tour/plan.rs:227`). The page stores reviewed marks in localStorage under `git-stk-tour:<headSha>`, keyed by `step.id` (`src/tour/template.html:1280` and `:1484`). The doc comment at `src/tour/steps.rs:49` only promises the id is "Stable for a plan". If the user re-plans the same head (with `--refresh-plan`, a different `--plan` file, or a different agent), `plan-3` can name a different group of files but still shows the old mark. A reader would then see a step they never opened marked as reviewed. That is wrong behavior a user can hit, and nothing in the code or docs says it is intended.

label:

## 8. git-stk PR #130: `tests/demo.rs:349` (match)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/f6e0007940e62633ddde27ec2993f50f3fe73b56/tests/demo.rs#L349). PR title: fix(cli): offer to close dated PRs

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Missing Coverage]** No tests for the declined prompt, non-stack submit, dry-run, or rename-back paths

The only new e2e test covers the happy path in `--stack` mode. Add tests in `tests/demo.rs` for (a) answering `n` to the prompt, which keeps the review and the marker state consistent, (b) a non-stack `submit` after rename, (c) `submit --dry-run`, which must leave the marker in place and close nothing, and (d) rename-then-rename-back, which must not close the live review.

<!-- review-bot:finding n=4 -->
~~~~

Known bug, at `src/commands/submit.rs:189`: A single-branch submit closes the superseded review and clears the rename marker even though the ledger prune that removes stale rows only runs for a stack-wide submit, orphaning the old row in every other overview.

Judge: **partial**. The comment asks for a test of a non-stack submit after a rename, which is the same path as the known bug. But it's only a missing-coverage request. It doesn't say that a single-branch submit closes the old review and clears the rename marker without pruning the stale ledger row, which leaves that row orphaned in other overviews.

label:

## 9. git-stk PR #299: `src/setup.rs:92` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/a2f11d5e2407984eff6f50339bb7f2755ab62e58/src/setup.rs#L92). PR title: feat(shell): add setup --wrapper to install the stk function and its completion

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** `stk_name_taken` skips every `stk()` line, so a hand-pasted README wrapper is not seen as a collision.

The README previously told users to paste `stk() { ... }` into their rc. That rc has no `# stk wrapper:` marker and no git-stk block, but the `trimmed.starts_with("stk()")` exemption makes `stk_name_taken` return `None`. `setup --wrapper` then installs a second definition, which silently overrides the user's own. `uninstall` only removes the generated copy and leaves the hand-written one, contradicting the claim that setup never wins a collision with an existing definition. Only exempt lines inside our own block, which is the span from `COMPLETION_MARKER` to `BLOCK_END_MARKER`. Alternatively, skip the exemption entirely and rely on `has_wrapper` and the merge path. Add a test with a bare `stk() {` in the rc and no marker.

<!-- review-bot:finding n=1 -->
~~~~

Judge: **valid**. The claim holds. At `src/setup.rs:92`, `stk_name_taken` skips every line that starts with `stk()`, whether or not git-stk wrote it. The README (lines 147–161) still tells users to paste a bare `stk() {` function with no `# stk wrapper:` marker. If a user did that and then runs `setup --wrapper`, the check finds no collision and setup appends a second definition. That later copy overrides the user's version, which may be customized, and `uninstall` removes only the generated copy. This breaks the stated intent at lines 187–188, "Drop the wrapper rather than win the collision." Re-runs over our own block are already handled by the `has_wrapper` check, so the blanket exemption isn't needed for that.

label:

## 10. git-stk PR #55: `src/setup.rs:112` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/bef1ba6264b64a63dcbc29043ca7c3a4500a757d/src/setup.rs#L112). PR title: feat(cli): remind to run stk setup post-install

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Complexity]** The 'already configured' check is copy-pasted from wire_completions and handles read errors differently.

`print_completion_hint` re-implements the `COMPLETION_MARKER || "git stk completions"` detection from `wire_completions` (line 74). The two copies must now stay in sync. This one also turns any read error (e.g. a permission-denied rc file) into `false`, so it prints a misleading 'not configured' hint, while `wire_completions` returns an error for the same case. Extract one helper, e.g. `fn completions_configured(rc: &str) -> bool`, and share the NotFound-vs-error read handling.

<!-- review-bot:finding n=0 -->
~~~~

Judge: **nit**. Accurate: line 113 repeats the check from line 74, and `.unwrap_or(false)` treats any read error as "not configured". Mostly this is duplication, a maintainability point. The error-handling difference only shows up when the rc file exists but can't be read, which is rare. Even then the result is a non-interactive hint after an upgrade, and arguably it's better to print the hint than to fail the refresh.

label:

## 11. navi PR #110: `crates/navi-notifier/src/editor.rs:23` (triage)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/e50c8abb885c563edff56b4f947b111778ce9039/crates/navi-notifier/src/editor.rs#L23). PR title: feat(cli): add `navi config edit` and `navi env` to open files in $EDITOR

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** Splitting the editor string on whitespace breaks any editor path that contains a space.

With `VISUAL="C:\Program Files\Microsoft VS Code\bin\code.cmd" -w` or `/Applications/Sublime Text.app/.../subl -w`, `program` becomes `C:\Program` and the launch fails with a confusing "launching editor `C:\Program`" error. The module doc says it behaves like `git config --edit`, but git runs the string through a shell. Either parse with a shell-words-style splitter that honors quotes (the `shlex` crate on unix, a quote-aware split on Windows), or document that paths with spaces are unsupported and try the whole string as a program name first.

The Windows default of `notepad` makes this a likely path for Windows users.

<!-- review-bot:finding n=0 -->
~~~~

Judge: **nit**. The claim is accurate: `crates/navi-notifier/src/editor.rs:22` splits the editor string on whitespace, so a quoted path that contains a space would fail. But the module doc (lines 1-3) says outright that the string "is split on whitespace", so this is a known, intended limitation. Most editors are set by a bare command name on PATH (`code -w`, `subl -w`), which works fine. The comment also mentions the Windows default `notepad`, but that has no space and isn't affected. This is an edge-case improvement, not a defect worth asking the author to change.

label:

## 12. git-stk commit 0dfa614: `src/providers.rs:306` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/0dfa6140074cf66e780ed03e558a9f5ef73b78e2/src/providers.rs#L306). PR title: feat(providers): delete cleaned branches

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** `git::current_branch()?` is now called unconditionally, so `cleanup` fails on a detached HEAD even without `--delete-branch`.

`current_branch` uses `symbolic-ref --quiet`, which errors on a detached HEAD. Before this change, `git stack cleanup <branch>` with an explicit branch worked from a detached HEAD. Now it fails with "failed to determine current branch" even when the new flag is not used. Only resolve the current branch when `delete_branch` is true, for example by mapping a symbolic-ref failure to `None`. A detached HEAD can't match any branch, so it needs no refusal.

<!-- review-bot:finding n=1 -->
~~~~

Judge: **valid**. The PR adds `git::current_branch()?` at line 305 and calls it every time, whether or not `--delete-branch` is passed. `current_branch` runs `symbolic-ref --quiet`, which fails on a detached HEAD. So `cleanup <branch>` now errors from a detached HEAD even without the new flag, where it used to work. That is a real regression in existing behavior.

label:

## 13. navi PR #131: `crates/navi-notifier/src/config.rs:578` (triage)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/c206ed28cc1cbe3111801ac564bbed6af03bf266/crates/navi-notifier/src/config.rs#L578). PR title: feat(cli): validate config in `navi doctor` (static checks + --offline)

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** `is_valid_repo_glob` accepts patterns that the shared matcher can never match.

The runtime matcher `pattern_matches` allows `*` only as the whole owner and only as a trailing `*` on the name. So `ac*/repo`, `acme/*-x` and `*/*` all pass `is_valid_repo_glob`, but `*/*` aside, they match nothing, and `doctor` says 'no problems found' for a rule that silently drops or never routes events. This is the 'malformed glob' class the validator is meant to catch. Validate against the matcher's real grammar: owner is `*` or has no `*`, and name has at most one `*`, as the final character. Ideally, share the logic with `pattern_matches`. Add tests for these cases.

<!-- review-bot:finding n=2 -->
~~~~

Judge: **valid**. This is a real bug. `pattern_matches` (navi-notifier-core/src/config.rs:120) only treats `*` as a wildcard in two places: when it is the whole owner, or when it is the last character of the name. `is_valid_repo_glob` only checks that there is one `/` with something on both sides. So `ac*/repo` and `acme/*-x` pass validation but can never match a real repo, and `doctor` still reports no problems for them. The doc comment ("either may be/contain `*`") states the validator's assumption; it isn't a reason for the gap, because the matcher doesn't support those forms. Catching patterns like this is what the validator is for.

label:

## 14. navi commit a1a570c: `crates/navi-notifier/src/service.rs:347` (match)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/a1a570cf8dedcaaa3b984e539c8f4ffbacf4b92f/crates/navi-notifier/src/service.rs#L347). PR title: feat(cli): add `navi service` to manage the background service

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** Paths containing `'` break the PowerShell command in the scheduled task.

`exe` and `config` are interpolated inside single-quoted PowerShell strings with no escaping. A Windows profile path such as `C:\Users\O'Brien\...` (the config lives under the user profile) ends the string early, so the task fails at sign-in. Anything after the quote is also parsed as PowerShell code. Escape `'` as `''` in both values, and add a test with an apostrophe in the path.

<!-- review-bot:finding n=3 -->
~~~~

Known bug, at `crates/navi-notifier/src/service.rs:348`: Exe and config paths are interpolated into a single-quoted PowerShell string without escaping, so a path with an apostrophe breaks out of the quoting.

Judge: **yes**. The comment points to the same defect. The exe and config paths are placed inside single-quoted PowerShell strings without escaping, so an apostrophe ends the string early. It also suggests a fix: escape each ' as ''.

label:

## 15. navi PR #110: `crates/navi-notifier/src/cli.rs:68` (triage)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/e50c8abb885c563edff56b4f947b111778ce9039/crates/navi-notifier/src/cli.rs#L68). PR title: feat(cli): add `navi config edit` and `navi env` to open files in $EDITOR

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Surface Drift]** New `navi env` and `navi config edit` commands are not reflected in the README.

The README "Configure" step still tells users to run `$EDITOR ~/.config/navi/config.toml`, and the service section tells them to find `navi.env` by hand. Update both to point at `navi config edit` and `navi env`.

<!-- review-bot:finding n=1 -->
~~~~

Judge: **nit**. The claim is accurate. README.md:108 still says `$EDITOR ~/.config/navi/config.toml`, and README.md:155 describes `navi.env` without mentioning the new `navi env` command. But that text is still correct, and the new commands are just shortcuts for the same steps. Pointing the README at them would help discoverability, but the docs don't tell users anything false.

label:

## 16. navi PR #131: `crates/navi-notifier/src/config.rs:405` (triage)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/c206ed28cc1cbe3111801ac564bbed6af03bf266/crates/navi-notifier/src/config.rs#L402). PR title: feat(cli): validate config in `navi doctor` (static checks + --offline)

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** `KNOWN_TAGS` is shared with `digest.kinds`, but the digest only matches `EventKind::tag()`, so per-state tags pass validation and never fire.

`engine.rs:284` checks `digest_kinds.contains(event.kind.tag())`, while `match_tags()` (with `review_approved` etc.) is only used for Slack broadcast. A user who sets `digest.kinds = ["review_approved"]` gets "no problems found" from `doctor`, and the events are never digested. Use a separate list for `digest.kinds` that excludes the three per-state review tags, and add a test.

<!-- review-bot:finding n=1 -->
~~~~

Judge: **valid**. Confirmed. In `validate` (config.rs:548-549), `digest.kinds` is checked against `KNOWN_TAGS`, and that list includes `review_approved`, `review_changes_requested` and `review_commented`. But the engine (engine.rs:284) only matches digest kinds against `event.kind.tag()`, which never returns those per-state tags. `match_tags()` is used only for broadcast. So `doctor` accepts a digest setting that never matches any event, even though this validation exists to catch config that silently drops events.

label:

## 17. git-stk PR #132: `src/lock.rs:43` (match)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/27b0cf2ee2784f69b2dea178b84df24caa76c561/src/lock.rs#L43). PR title: chore(cli): add stack lock

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Safety]** A stale lock from a killed run blocks every mutating command, including the recovery commands `abort` and `undo`, and the recorded PID is never checked.

The lock is released only by `Drop`. Ctrl-C at one of the interactive prompts in `submit` or `cleanup`, or a SIGKILL, skips `Drop` and leaves `.git/stk-lock` behind. Every later `new`, `restack`, `abort`, `undo` and `continue` then fails with "another git stk operation is in progress" until the user deletes the file by hand. The lock file already holds the PID, so `acquire` should check whether that process is still alive (for example `kill(pid, 0)` or `/proc/<pid>`). If it is dead, it should reclaim the lock instead of bailing. Alternatively use an OS advisory lock (`flock` via `fs2` or `std::fs::File::try_lock`), which the kernel releases when the process dies. At minimum, exempt `abort` and `undo` from the lock.

<!-- review-bot:finding n=0 -->
~~~~

Known bug, at `src/lock.rs:43`: A lock file left by a crashed or killed process is never reclaimed, so every later git stk command fails until the user removes it by hand.

Judge: **yes**. The comment describes the same defect as the known bug. When a run is killed, the stale lock file stays behind and is never reclaimed, so every later command fails until the user deletes the file by hand.

label:

## 18. git-stk PR #130: `src/commands/submit.rs:261` (match)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/f6e0007940e62633ddde27ec2993f50f3fe73b56/src/commands/submit.rs#L261). PR title: fix(cli): offer to close dated PRs

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Safety]** Closing with branch deletion can close child PRs that still target the old branch

`close_review(&review, true)` deletes the remote old branch, but only branches in `branch_parents` get their PR base retargeted. A plain `stk submit` (non-stack) of the renamed leaf leaves its children's PRs on the platform based on the old name. Deleting that branch makes the platform close those PRs. Either skip `--delete-branch` unless every child review has been retargeted, or check for open reviews based on `old` and warn or skip the deletion.

<!-- review-bot:finding n=0 -->
~~~~

Known bug, at `src/commands/submit.rs:189`: A single-branch submit closes the superseded review and clears the rename marker even though the ledger prune that removes stale rows only runs for a stack-wide submit, orphaning the old row in every other overview.

Judge: **partial**. Both point at the same flaw: a single-branch submit still closes the superseded review for a renamed branch. But the comment's consequence is different. It says deleting the branch closes child PRs that were never retargeted. The known bug is that the ledger prune runs only on a stack-wide submit, so after the review is closed and the rename marker cleared, the old ledger row stays orphaned in the other overviews. The comment never mentions the ledger, the prune or the overviews.

label:

## 19. git-stk PR #291: `src/commands/up.rs:26` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/ecceadd60018090618a3e62f6bde29e4fbf67a6d/src/commands/up.rs#L26). PR title: feat(cli): add --from-path to nav commands so cd can follow a branch

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Complexity]** The same `nav_output` mapping is copy-pasted into four command files.

`Up`, `Down`, `Top` and `Bottom` each define an identical `nav_output()` that maps a bool to `NavOutput`, along with an identical doc comment on the flag. Add one `impl From<bool> for NavOutput` (or a `NavOutput::from_flag`) in `stack::nav` and call it from each `run`. Future changes to the mapping then happen in one place instead of four.

<!-- review-bot:finding n=1 -->
~~~~

Judge: **nit**. The claim is accurate: up.rs, down.rs, top.rs and bottom.rs each contain the same `nav_output()`. But this is a small duplication refactor, and the four copies behave correctly. It's a style suggestion, not a defect.

label:

## 20. git-stk PR #293: `src/commands/repair.rs:193` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/e0a3eec0c8aba58322a3f98a89d0f402ea49ccd5/src/commands/repair.rs#L193). PR title: feat(cli): add new --worktree, with git-stk owning the worktrees it creates

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** repair clears a valid ownership marker when run from inside the owned worktree, and compares paths with `==`.

`git::worktree_holding` leaves out the worktree you are standing in. If you run `git stk repair` from inside a worktree made by `new --worktree`, which is where the printed `cd` hint sends you, then `actual` is `None` for that branch. The live marker is then reported as stale and cleared, and `cleanup` later keeps that worktree forever. The check also uses `Some(path) != actual.as_ref()`, which is exact equality. This PR's own `git::same_path` doc warns against that, because git reports resolved paths (a symlinked `stk.worktreeDir`, `/var` vs `/private/var`) and we record `std::path::absolute`. With a symlinked dir, every `repair` clears the marker, and the next run re-adopts it only if the expected path matches. Fix: skip a branch that is `current_branch` or whose worktree is this one, and compare with `same_path`. Add a test that runs `repair` from inside the owned worktree, and one with a symlinked `worktreeDir`.

<!-- review-bot:finding n=0 -->
~~~~

Judge: **valid**. The comment is right. `worktree_holding` (git.rs:133-139) leaves out the worktree you are currently in. So when you run `repair` from inside a worktree made by `new --worktree`, `actual` is None for that branch. The `Some(path) != actual.as_ref()` arm then clears a live ownership marker, and `cleanup` never removes that worktree afterwards. The check also uses `==`, which the `same_path` doc says never to do for worktree paths. With a symlinked `stk.worktreeDir`, that clears valid markers too.

label:

## 21. navi PR #110: `crates/navi-notifier/src/envfile.rs:50` (triage)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/e50c8abb885c563edff56b4f947b111778ce9039/crates/navi-notifier/src/envfile.rs#L50). PR title: feat(cli): add `navi config edit` and `navi env` to open files in $EDITOR

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Error Handling]** `create_dir_all(dir).ok()` drops the error that explains the later failure.

If the directory cannot be created, the real cause (permission denied, a path component is a file) is dropped. The user then gets a vaguer "creating temp file in …" error. Propagate it with `.with_context(|| format!("creating {}", dir.display()))?`.

<!-- review-bot:finding n=3 -->
~~~~

Judge: **nit**. The claim is accurate: line 51 discards the `create_dir_all` error. But the failure still reaches the user. The next call, `NamedTempFile::new_in(dir)`, fails with the underlying OS error plus the directory path, so it isn't a silent failure. It also copies the existing pattern in `upsert` (line 27). This only affects how clear the error message is in an uncommon case, so it's a nit rather than a defect.

label:

## 22. git-stk PR #267: `src/commands/status.rs:57` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/d1ccaddbf441e7b46903d0d6e7488a229404cd43/src/commands/status.rs#L57). PR title: feat(list): add --reviews and --local flags for rich review info

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Missing Coverage]** The new `status` marker logic and the `list --local` flag-conflict rules have no test

`status` now makes extra provider calls (`enqueued_branches`, `check_status`) and changes its `review:` line format. The `list --local` and `--reviews` clap conflict rules are new CLI behaviour. The diff adds only unit tests of parsers plus the `list_status.rs` integration tests, which I could not tie to the `status` marker path. Add a `tests/list_status.rs` case, using the repo's existing fake `gh`, that asserts the `status` output marker for a queued review and a failing-CI review, and that `--local` makes no provider call.

<!-- review-bot:finding n=3 -->
~~~~

Judge: **wrong**. tests/list_status.rs already has the tests the comment asks for: list_local_makes_no_provider_calls (line 127), list_reviews_conflicts_with_commits_format_and_local (line 145) and status_shows_a_status_dot_for_the_reviews_pr (line 160). Queued markers are also tested near line 104. The comment names no actual bug.

label:

## 23. git-stk PR #188: `src/setup.rs:303` (match)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/446248ae376cb9edbf54141b2890b28d73c04934/src/setup.rs#L303). PR title: feat(cli): add uninstall docs/command

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Safety]** strip_completion_block deletes the line after the marker without checking it is the completion line.

If the user removed or edited the completion line but left the `# added by git-stk setup` comment, the next line, which can be any unrelated rc content, is silently dropped. Only remove the following line when it contains `git stk completions`. Add a test for the marker followed by unrelated content.

<!-- review-bot:finding n=1 -->
~~~~

Known bug, at `src/setup.rs:303`: Uninstall always deletes the line after the completion marker, so if the user removed setup's completion line but left the marker, their own next rc line is deleted.

Judge: **yes**. The comment points to the same defect. Uninstall drops the line after the marker without checking what it is. If the user removed the completion line but kept the marker, an unrelated rc line gets deleted.

label:

## 24. navi commit b766245: `crates/navi-notifier/src/upgrade.rs:38` (match)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/b766245a6de5ff7c6d3619e36284517b65795f9d/crates/navi-notifier/src/upgrade.rs#L38). PR title: feat(cli): add completions, setup, upgrade, downgrade, uninstall

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** The `--force` flag is accepted but ignored (`_force`), and `main` hard-codes `yes=false`.

`navi upgrade --force` does exactly the same as `navi upgrade`, and the non-`--head` path never checks the installed version anyway. Either implement `--force` (add an up-to-date check that `--force` bypasses) or remove the flag. `setup --refresh` is documented as "run by `upgrade` via the new binary", but `upgrade` never invokes it, so that flag has no caller.

<!-- review-bot:finding n=2 -->
~~~~

Known bug, at `crates/navi-notifier/src/upgrade.rs:38`: upgrade ignores its --force flag (_force) and always re-downloads and reinstalls even when already on the latest release.

Judge: **yes**. The comment says `--force` is accepted but ignored (`_force`), and that the non-`--head` path never checks the installed version. That means upgrade always reinstalls, with or without `--force`, which is the same defect as the known bug.

label:

## 25. git-stk PR #292: `src/commands/run.rs:153` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/bae3af080658bc677d03bfe43b4a1704c6ed7f96/src/commands/run.rs#L153). PR title: feat(run): run in a scratch worktree by default, with --no-worktree to opt out

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** `--no-worktree` now sets an explicit cwd that can vanish mid-walk, so the run aborts with a misleading spawn error.

`here` is captured once, then `run_once` does `.current_dir(&here)` on every branch. When the user starts in a subdirectory (for example `packages/web`) that is absent on an earlier branch, `git checkout` removes it. The spawn then fails with ENOENT, and `spawn_error` reports it as ``failed to run `cmd`: No such file or directory``. That blames the command and aborts the whole run, which is the case the scratch path handles with `mirrored_dir`. Before this PR the spawn had no explicit `current_dir`. Fall back to the repo root when `here` is not a directory (or reuse `mirrored_dir(&repo_root, &relative_cwd)`), and add a test with a subdirectory that exists only on the later branch.

<!-- review-bot:finding n=0 -->
~~~~

Judge: **wrong**. The claimed failure doesn't happen with the git versions people use now. `crate::git::checkout` runs git from the process's own cwd, which is `here`. Since git 2.35 (January 2022), `git checkout` won't delete the directory it was started from. It removes the tracked files inside but leaves the directory itself in place. So `here` still exists, `.current_dir(&here)` succeeds, and the spawn never fails with ENOENT. It could only happen on git older than 2.35. Even there, the code before this PR would have run the command in a deleted cwd, so this PR doesn't introduce a meaningful regression. The comment's central claim doesn't hold up.

label:

## 26. git-stk PR #94: `src/providers/github.rs:63` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/e12851e3ff9681f288d57775a4970a079f41c02a/src/providers/github.rs#L63). PR title: chore(cli): make merge --wait more durable

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Missing Coverage]** The new polling and grace-window loops have no behavioral test, and the old pending-then-settle coverage was removed.

The only tests added are for the pure `interpret_checks` classifier. Nothing runs `wait_for_checks` through the loop, so these paths are untested: no-checks then grace expiry returning true, no-checks then pending resetting the counter, pending then failure returning false, and the GitLab grace window. The `tests/merge.rs` change dropped the pending (exit 8) scenario and now covers only immediate green. Add `tests/merge.rs` cases with the fake `gh` (and `glab`) that return no-checks or pending for N calls before settling, plus a failing case. That needs a way to shorten the poll interval, for example an env or config override read by `check_poll_interval`. Without one, each such test sleeps 5s or more.

<!-- review-bot:finding n=0 -->
~~~~

Judge: **nit**. The claim is accurate. Only `interpret_checks` gained tests, and `tests/merge.rs` no longer covers the pending (exit 8) case. But the loop in `wait_for_checks` looks correct: grace expiry returns true, Pending resets the counter, and Failed returns false. The comment doesn't point to any defect, so this is a request for tests on code that works.

label:

## 27. git-stk PR #125: `src/providers/mod.rs:187` (match)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/8918300f96f03c4dbeb3fb4eeab2b2f5ae09ff1e/src/providers/mod.rs#L185). PR title: fix(providers): parse host better

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** host_of strips userinfo at the first '@' anywhere in the URL, including the path, so a look-alike URL is still detected.

For `https://evil.com/x@github.com/repo.git`, `split_once('@')` returns `github.com/repo.git`, so `host_of` yields `github.com` and the remote is detected as GitHub. This is the look-alike case the PR says it blocks. A password containing `@` has the same problem. Limit userinfo stripping to the authority, meaning the text before the first `/`, and split on the last `@` there. For example: `let authority = after_scheme.split('/').next().unwrap_or(after_scheme); let after_user = authority.rsplit_once('@').map_or(authority, |(_, h)| h); after_user.split(':').next().unwrap_or(after_user)`. Add `https://evil.com/x@github.com/repo.git` to `provider_does_not_match_lookalike_hosts`.

<!-- review-bot:finding n=0 -->
~~~~

Known bug, at `src/providers/mod.rs:185`: host_of strips userinfo at the first '@' anywhere in the URL rather than in the authority, mishandles IPv6 literals, and the configured stk.gitlabHost is compared raw, so a full-URL setting or an '@' in the userinfo or path misdetects the provider.

Judge: **yes**. The comment identifies the main defect: host_of strips userinfo at the first '@' anywhere in the URL, including the path, rather than only in the authority. That causes misdetection, for example with `https://evil.com/x@github.com/repo.git`, or when the password contains '@'. It does not mention the IPv6 mishandling or the raw comparison of stk.gitlabHost, but the root cause it names is the same as the known bug.

label:

## 28. navi PR #131: `crates/navi-notifier/src/config.rs:546` (triage)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/c206ed28cc1cbe3111801ac564bbed6af03bf266/crates/navi-notifier/src/config.rs#L546). PR title: feat(cli): validate config in `navi doctor` (static checks + --offline)

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** `digest.kinds` is validated against tags that the digest never matches.

The engine checks `digest_kinds.contains(event.kind.tag())` (`engine.rs:284`). It uses `tag()` only, not `match_tags()`. The per-state tags `review_approved`, `review_changes_requested` and `review_commented` are valid for `slack.broadcast` but never match for the digest. Because `KNOWN_TAGS` is shared, doctor stays silent about them and the user's digest entry is dropped without notice. Validate `digest.kinds` against the 11 base tags only.

<!-- review-bot:finding n=3 -->
~~~~

Judge: **valid**. The comment is correct. At `engine.rs:284`, the digest only checks `digest_kinds.contains(event.kind.tag())`. The per-state tags come from `match_tags()`, so `review_approved`, `review_changes_requested` and `review_commented` can never match a digest entry. In `config.rs`, `validate()` checks `digest.kinds` against the shared `KNOWN_TAGS` list, which includes those three tags. So `navi doctor` accepts them without a warning, and the doc comment says they are accepted in `digest.kinds`. A user would get no warning from the new doctor check, and those digest entries would quietly never match.

label:

## 29. navi commit b766245: `crates/navi-notifier/src/cli.rs:48` (triage)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/b766245a6de5ff7c6d3619e36284517b65795f9d/crates/navi-notifier/src/cli.rs#L48). PR title: feat(cli): add completions, setup, upgrade, downgrade, uninstall

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Surface Drift]** The new commands and the `NAVI_NO_UPDATE_CHECK` opt-out are not documented in the README.

The README Install, Setup and Usage sections do not mention `completions`, `setup`, `uninstall`, `upgrade`, `downgrade`, the man page install, or the daily update check and its opt-out. The README also still describes `navi` as GitHub-to-Slack, while this PR rewrites `about` to be multi-provider. Add a short section to the README covering these commands and the env var.

<!-- review-bot:finding n=2 -->
~~~~

Judge: **nit**. The README really doesn't mention the new commands or NAVI_NO_UPDATE_CHECK, so that part is true. But leaving new commands out of the README doesn't make it say anything false; it's just incomplete. The comment's other claim is wrong: README line 14 already describes navi as multi-provider (GitHub, GitLab and Gitea as sources; Slack, Discord and email as destinations), not GitHub-to-Slack. A docs gap is worth a mention but not a requested change.

label:

## 30. git-stk PR #301: `src/commands/up.rs:37` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/c062bf1597c9b3b98bf1b15dcac6db739aa80350/src/commands/up.rs#L37). PR title: feat(navigation): up/down take number of branches to move

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Surface Drift]** An all-digit child branch name can no longer be reached with `up <branch>`, and this break isn't documented.

`parse_target` sends any value that parses as an integer to `Target::Distance`. `git stk up 123` (a ticket-number child branch) used to check out `123`. Now it walks 123 branches and fails with "cannot go up 123…", and `child_branch_candidates` still offers `123` as a completion. The only note is a code comment. Put the behavior change in the README `up` text and the CHANGELOG entry. Better, when `up` is given an integer, check whether it matches a child of the current branch before treating it as a distance.

<!-- review-bot:finding n=0 -->
~~~~

Judge: **nit**. The claim is accurate: `parse_target` reads any integer as a distance, so `up 123` no longer checks out a branch named `123`. But this is a deliberate choice. The doc comment on `Target` (up.rs:26-27) says digit-only branch names "have to be reached by name from elsewhere." The README (lines 279 and 291) and the CHANGELOG also document the new `[branch | n]` distance syntax. The only gaps are a missing user-facing note about the all-digit case and an extra lookup the reviewer suggests, both for an uncommon kind of branch name. That makes it a nit, not a defect.

label:

## 31. navi commit 244e1c4: `crates/navi-notifier-github/src/source.rs:197` (triage)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/244e1c45f83fef5f54b47fbde48206fa5aa12e3e/crates/navi-notifier-github/src/source.rs#L197). PR title: feat(github): add github source with notifications poll and timeline diff

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Error Handling]** A failed PR fetch is skipped, but the `notif_since` cursor still advances, so that PR's events are lost.

On a transient failure (5xx, timeout, rate limit) the PR is skipped without updating its snapshot or thread cursor. The loop then advances `notif_since` to `poll_start - 5min`. On the next poll the notification's `updated_at` is usually older than `since`, so the thread is never listed again. A transient error therefore becomes permanent event loss. Rate-limit errors are swallowed the same way, so the engine's `RateLimited` handling never sees them. Propagate `RateLimited` and `Auth` errors, and don't advance `notif_since` past the oldest notification whose fetch failed.

<!-- review-bot:finding n=1 -->
~~~~

Judge: **valid**. The claim holds. At source.rs:193-199, any error from fetch_pr is logged and skipped, including rate-limit, auth and transient errors, so neither the snapshot nor the thread cursor is updated. The loop then always advances notif_since to poll_start minus 5 minutes (lines 232-237). Any skipped thread last updated before that cutoff drops out of the next `since` query, so its events are lost unless the thread gets new activity. The code comment explains why inaccessible PRs are skipped (deleted or permissions), but it doesn't cover transient errors or swallowing RateLimited.

label:

## 32. git-stk PR #125: `src/providers/mod.rs:185` (match)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/8918300f96f03c4dbeb3fb4eeab2b2f5ae09ff1e/src/providers/mod.rs#L183). PR title: fix(providers): parse host better

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** `host_of` splits on `@` before isolating the authority, so a path containing `@` spoofs the host.

For `https://evil.com/x@github.com/repo`, `after_scheme` is `evil.com/x@github.com/repo`. `split_once('@')` then yields `github.com/repo`, and `host_of` returns `github.com`. The remote is detected as GitHub, which is the look-alike case the new comment and test say can no longer happen. Cut the authority at the first `/` before looking for `user@`. For scp-style URLs, which have no `://`, a `:` also ends the authority, but only if no `@` comes after the `/`. A simple fix is to take `after_scheme.split('/').next()` first, then `rsplit_once('@')`, then split on `:`. For scp-style `git@host:owner/repo`, the first-`/` cut still leaves `git@host:owner`, which is fine. Add `https://evil.com/x@github.com/repo.git` to `provider_does_not_match_lookalike_hosts`.

<!-- review-bot:finding n=0 -->
~~~~

Known bug, at `src/providers/mod.rs:185`: host_of strips userinfo at the first '@' anywhere in the URL rather than in the authority, mishandles IPv6 literals, and the configured stk.gitlabHost is compared raw, so a full-URL setting or an '@' in the userinfo or path misdetects the provider.

Judge: **yes**. The comment names the main defect: host_of strips userinfo at the first '@' anywhere in the URL, not just within the authority, so an '@' in the path makes it detect the wrong host or provider. It gives a concrete example and the right fix (cut the authority first). It does not mention the IPv6 handling or the raw stk.gitlabHost comparison, but the central bug is the same one.

label:

## 33. git-stk PR #303: `src/commands/sync.rs:263` (match)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/a879172037a9cdb2c5008d5c0ded951a077bf89a/src/commands/sync.rs#L263). PR title: fix(worktree): smarter cleanup behavior for worktrees

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** A kept finished branch skips child retargeting, so sync restacks its children onto the already-landed branch.

Before, `cleanup_finished_branch` always ran and retargeted direct children onto the finished branch's parent, setting the fork point and updating the review base. It is now skipped whenever `deletion_blocker` fires. Step 3 above also deliberately skips children whose parent is in `finished`, leaving their retarget to this step. Example: `sync` from inside `feature/a`'s worktree with `feature/b` stacked on it. `feature/b` keeps `stkParent=feature/a`, its review base is never updated, and step 7 `restack` rebases `feature/b` onto the squash-merged `feature/a` instead of the trunk. Split the step: always retarget the children, and defer only the `unset_parent`/`unset_base` of the kept branch and the ref deletion. The same applies to `cleanup()`, which has the identical `continue`.

<!-- review-bot:finding n=0 -->
~~~~

Known bug, at `src/commands/sync.rs:264`: sync keeps a landed branch whose ref cannot be deleted but still passes it to the following restack, which refuses a branch held by another worktree and fails the whole sync.

Judge: **partial**. The comment points at the same code: the new skip when a finished branch is kept because its ref can't be deleted. It also links that to the later restack step. But it describes a different failure. It says the kept branch's children aren't retargeted, so they get rebased onto the landed branch. The known bug is that the kept branch is itself still passed to restack, and restack refuses a branch checked out in another worktree, so the whole sync fails. The comment never mentions restack refusing the kept branch or sync aborting.

label:

## 34. navi commit 244e1c4: `crates/navi-notifier-github/src/source.rs:130` (match)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/244e1c45f83fef5f54b47fbde48206fa5aa12e3e/crates/navi-notifier-github/src/source.rs#L101). PR title: feat(github): add github source with notifications poll and timeline diff

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** Pagination is capped at 10 pages of 100 with no signal, and the truncated list is then stored as the 'seen' set.

For a PR with more than 1000 reviews or comments, items beyond the cap are never fetched or emitted. The 10-page cap also truncates `/notifications`, while `notif_since` still advances. Log a warning when the cap is hit. For notifications, don't advance the cursor in that case.

<!-- review-bot:finding n=5 -->
~~~~

Known bug, at `crates/navi-notifier-github/src/source.rs:79`: Notification paging stops silently at MAX_PAGES while pages are still full, dropping notifications after a long gap without any warning.

Judge: **yes**. The comment says pagination stops at the 10-page cap with no signal and that this cap truncates /notifications, so notifications are dropped. It recommends logging a warning. That is the known bug.

label:

## 35. git-stk commit 0dfa614: `src/providers.rs:325` (triage)

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/0dfa6140074cf66e780ed03e558a9f5ef73b78e2/src/providers.rs#L324). PR title: feat(providers): delete cleaned branches

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Safety]** The checked-out-branch guard runs after metadata and remote PR mutations, so a refusal leaves cleanup half-applied.

`cleanup_merged_branch` has already retargeted child PRs on the provider (`gh pr edit`), rewritten children's `stackParent`, and unset the branch's own stack metadata when `cleanup_branch_deletion` hits `bail!("refusing to delete currently checked out branch")`. The command then exits with an error, but the remote PR bases and local metadata have already changed and cannot be rolled back. The same applies when `git branch -d` fails afterwards. Validate the delete preconditions before any mutation. For example, check `delete_branch && branch == current_branch` at the top of the loop iteration, or up front for all merged branches, and bail before calling `cleanup_merged_branch`. Also assert in the refusal test that `branch.feature/a.stackParent` is unchanged.

<!-- review-bot:finding n=0 -->
~~~~

Judge: **valid**. The claim is correct. At `src/providers.rs:324-325`, `cleanup_merged_branch` runs first and does real work when it isn't a dry run: it retargets child PRs on the provider, rewrites the children's `stackParent`, and unsets the branch's own parent. Only after that does `cleanup_branch_deletion` check `branch == current_branch` and bail. When no branch argument is given, `cleanup` defaults to the current branch, so the most likely `--delete-branch` use exits with an error after the remote and local changes have already been made. Nothing in the code or docs says this is intended. The existing test only checks that the branch still exists, not that the metadata is unchanged.

label:

## 36. navi PR #85: `crates/navi-notifier-github/src/source.rs:330` (triage)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/4443b196008a725c46ea4a1bec2bd620b0c8ca95/crates/navi-notifier-github/src/source.rs#L330). PR title: feat(github): detect merge-queue enter/exit via GraphQL

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Bug]** The removal event's dedup key uses `pr.updated_at`, which the comment above says GitHub doesn't reliably bump on queue changes.

If a PR is dequeued, re-enqueued and dequeued again without `updated_at` changing, both removals get the same `merge_queue_removed:<updated_at>` key. The second removal is then deduplicated and dropped. Entry events avoid this by using `enqueuedAt`. Use a discriminator that changes per transition for removals too. For example, capture the previous entry's `enqueuedAt` (store it alongside the state in the `mq:` cursor) or include the observed prior state plus the poll timestamp. Add a poll test with two consecutive removals.

<!-- review-bot:finding n=0 -->
~~~~

Judge: **valid**. At source.rs:424, the removal key is `merge_queue_removed:{updated_at}`. The comment at lines 417-418 says GitHub doesn't always bump `updated_at` when queue state changes. Entry events use `enqueuedAt` for this reason. The `delivered` table in state.rs is a persistent dedup set. So if a PR is removed from the queue twice while `updated_at` stays the same, the second removal gets the same key and its notification is silently dropped.

label:

## 37. navi commit f97c268: `crates/navi-notifier-core/src/rules.rs:96` (triage)

[Code at the PR head](https://github.com/lararosekelley/navi/blob/f97c2685701ae6f8e3a43e88510a6c92ca6e9b64/crates/navi-notifier-core/src/rules.rs#L96). PR title: feat(core): add domain model, provider traits, rule filter, and engine

~~~~text
<img src="https://raw.githubusercontent.com/lararosekelley/review-bot/main/assets/logo.svg" width="16" height="16" alt="review-bot" /> **[Error Handling]** Malformed quiet-hours config silently fails open

If `quiet_hours.enabled` is true but `start` or `end` is malformed (`"10pm"`, `"24:00"`, or empty because of `#[serde(default)]`), `parse_hhmm` returns `None`. `in_quiet_hours` then returns false and the user is pinged during hours they asked to be quiet. There is no error and no log. Validate `QuietHours` when the config is loaded and reject it, or at least `warn!` here. The `local_minutes: None` case is also a silent no-op. Add a test for a malformed value.

<!-- review-bot:finding n=3 -->
~~~~

Judge: **valid**. rules.rs:92-98 returns false whenever parse_hhmm fails, and nothing in config.rs or anywhere else validates QuietHours or logs the failure. So a user who enables quiet hours with a typo like "10pm" still gets pinged during that window, and nothing tells them why. The `local_minutes: None` case is documented as deliberate, so that part of the comment is minor, but the main claim holds.

label:
