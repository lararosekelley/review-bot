<!-- markdownlint-disable MD013 -->

# Judge calibration: triage sample

Each item is a comment the reviewer posted that matched no known bug, with the judge's call.
Fill in `label:` with valid, nit, or wrong. Leave it blank to skip.

- valid: a real defect worth asking the author to change.
- nit: true, but not worth a requested change.
- wrong: false, or not supported by the code.

## 1. git-stk PR #130: `src/prompt.rs:20`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/f6e0007940e62633ddde27ec2993f50f3fe73b56/src/prompt.rs#L20). PR title: fix(cli): offer to close dated PRs

~~~~text
**[Safety]**

Every other confirmation in the repo (`confirm`, used by merge, setup and upgrade) defaults to no. This helper treats an empty answer or EOF as yes, and it is used to close a PR and delete its remote branch. A non-interactive run (CI, a script, or stdin closed) therefore does both without anyone confirming. Make EOF mean no, or require `--yes` for non-interactive runs. A bare Enter at a TTY can keep the default yes, but only if EOF is distinguished from it by checking whether `read_line` returned 0.
~~~~

Judge: **nit**. The facts are right: `confirm_default_yes` (src/prompt.rs:20) treats both empty input and EOF as yes, and `close_superseded_review` (src/commands/submit.rs:253) uses it to close a review and delete its branch. But this is deliberate and documented in both places ("a non-interactive run proceeds"). The function only runs after the replacement review already exists under the renamed branch, and it is skipped under --dry-run. So it retires a superseded review rather than throwing away work. The comment disputes a design choice; it does not find a real bug.

label: nit - src/prompt.rs:18-19 documents EOF/non-interactive as yes on purpose, and the only caller (submit.rs close_superseded_review) closes a review already replaced by a fresh one. Later a526414 fix(cli): refine prompting behavior (#248) rewrote the prompt but explicitly kept EOF taking the default so scripted callers work. (labeled by Claude, high confidence)

## 2. navi PR #110: `crates/navi-notifier/src/cli.rs:67`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/e50c8abb885c563edff56b4f947b111778ce9039/crates/navi-notifier/src/cli.rs#L67). PR title: feat(cli): add `navi config edit` and `navi env` to open files in $EDITOR

~~~~text
**[Surface Drift]**

Two new commands (`navi env`, `navi config edit`) are not reflected in the README. Its setup section still tells users to run `$EDITOR ~/.config/navi/config.toml` (README.md:108) and to put tokens in `navi.env` without saying how (README.md:155). Update those lines to point at the new commands.
~~~~

Judge: **valid**. Checked README.md. Line 108 still says `$EDITOR ~/.config/navi/config.toml`, and line 155 tells users to put tokens in `navi.env` without saying how to open it. Nothing in the repo mentions `navi env` or `navi config edit`, so the README was never updated for the two new commands. Users won't find out about them, so this is a docs gap worth fixing.

label: valid - PR adds `navi config edit` and `navi env` without touching README.md, which still said `$EDITOR ~/.config/navi/config.toml`. The very next commit c6f1f33 docs(readme): sync with the current CLI and config surface replaced that line with the new commands. Later fix: c6f1f33 docs(readme): sync with the current CLI and config surface, trim prose. (labeled by Claude, medium confidence)

## 3. navi commit 9518b42: `dist-workspace.toml:13`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/9518b42bf78f35d7597c1b99ebe1f1d11c5b47a4/dist-workspace.toml#L13). PR title: chore(release): add cargo-dist release config

~~~~text
**[Surface Drift]**

This adds shell, PowerShell and Homebrew install channels, but `crates/navi-notifier/README.md` still documents only `cargo install navi-notifier --locked`. Add the install one-liners and `brew install lararosekelley/tap/...` to the README once the release workflow exists. Also check the formula name. dist defaults it to the package name (`navi-notifier`), while the binary users run is `navi`. If that isn't what you want, set `formula = "navi"`.
~~~~

Judge: **nit**. The facts check out. `crates/navi-notifier/README.md:6` only shows `cargo install navi-notifier --locked`. The package is `navi-notifier` and it ships the binary `navi`, so dist's default formula name would be `navi-notifier`. But the comment itself says the README update should wait until the release workflow exists, and release.yml isn't committed yet. It also gives no reason the default formula name is wrong: naming the formula after the package while it installs a differently named binary is common and works. This is a docs follow-up and a speculative naming preference, not a defect in this config.

label: nit - dist-workspace.toml adds installers but the release workflow did not exist yet (the comment itself says 'once the release workflow exists'); install docs came later with 528da3f docs(docs): document one-line install, which kept the default navi-notifier formula name. Deferred docs, not a defect in this PR. (labeled by Claude, medium confidence)

## 4. git-stk PR #266: `src/stack/nav.rs:212`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/b4b770c91afc4aa1e400533a9d50ea8d51c7ac23/src/stack/nav.rs#L212). PR title: feat(list): separate stacks better in list --all

~~~~text
**[Surface Drift]**

This changes the `list --all` output: the trunk is now repeated once per trunk-sharing stack, with blank-line-separated blocks. `README.md:186-188` still documents the old behavior ("the trunk once at the bottom, each stack's tree above it"). Update that paragraph to describe the per-stack blocks with the repeated trunk base.
~~~~

Judge: **valid**. The comment is correct. At the PR head, `print_all_stacks` (src/stack/nav.rs:212-292) draws one block per direct child of the trunk, and each block repeats the trunk as its base. The README was not changed and README.md:186-188 still says "the trunk once at the bottom, each stack's tree above it". That user-facing doc is now wrong, so asking the author to update it is worthwhile.

label: valid - src/stack/nav.rs:212 now prints one block per trunk child each repeating the trunk, while README.md:186-188 still says 'the trunk once at the bottom'. That sentence was never updated and survives on main in docs/COMMANDS.md:59. (labeled by Claude, medium confidence)

## 5. git-stk PR #312: `src/commands/submit.rs:651`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/bb07db8196e5cb9e7a53911a2ead137b77b6a854/src/commands/submit.rs#L651). PR title: feat(github): read GitHub's native stacks behind stk.githubStacks

~~~~text
**[Bug]**

`register_native_stack` is gated only on `--stack`/`--downstack`, not on whether the provider registers stacks. With `stk.githubStacks` off, or on GitLab, Gitea or the demo provider, a stack-wide submit still makes one `review_for_branch` call per branch (two `gh` calls for GitHub, since it falls back to the merged lookup). The `?` here means a failed lookup now fails a submit whose reviews were already created. When a review is missing it also prints "skipped stack registration", which is new output for providers this PR says it leaves untouched. This contradicts "off means today's behaviour byte for byte" and the "best effort, never fatal" comment on the function.

Return before the loop when the provider keeps no stacks. `would_register` already uses `registers_stacks()` for the dry run, but the real run never checks it:

```suggestion
    if branches.is_empty() || !review_provider.registers_stacks() {
        return Ok(());
    }
```

(Apply it at the top of the function, replacing the `branches.is_empty()` check on lines 639-641, and leave this line as it is.) Add a test in `tests/submit.rs` that a stack-wide submit with the setting off makes no extra review lookups and prints no registration line.
~~~~

Judge: **valid**. Confirmed: register_native_stack runs on every --stack/--downstack submit and calls review_for_branch per branch with `?`, regardless of registers_stacks(). Only the dry-run path checks registers_stacks(). So with the setting off or on other providers, you get extra lookups, a possible fatal error after the reviews already exist, and a new "skipped stack registration" line. That breaks both the function's own "best effort, submit still succeeds" doc comment and the PR's "off means today's behaviour" promise. The suggested early return is correct.

label: valid - register_native_stack (submit.rs:633-660) runs review_for_branch with `?` per branch with no registers_stacks() check, so non-GitHub/setting-off submits do extra lookups and can fail or print the skip line. Guard added in 10b3250 (setting) and then exactly as suggested in 38c1380. Later fix: 38c1380 fix(submit): ask the provider whether it registers, not the config key. (labeled by Claude, high confidence)

## 6. navi commit f97c268: `crates/navi-notifier-core/src/engine.rs:116`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/f97c2685701ae6f8e3a43e88510a6c92ca6e9b64/crates/navi-notifier-core/src/engine.rs#L116). PR title: feat(core): add domain model, provider traits, rule filter, and engine

~~~~text
**[Bug]**

`run_once` documents `dry_run` as not "advancing provider cursors", but `source.poll(self.state.as_ref())` runs unconditionally. Per the `Source` contract in `traits.rs`, `poll` persists advanced snapshots and cursors itself. A `--dry-run` therefore consumes the diff: a real run afterwards sees no change and never emits the events the preview showed. The same applies to a real run where delivery fails. The snapshot has already advanced, so "retried next pass" only holds if the source re-emits. The `dry_run_sends_nothing_and_leaves_state` test misses this because `MockSource` never writes state and the test only checks `was_delivered`.

Either pass a read-only or no-op `StateStore` wrapper to `poll` when `dry_run` is set, or change the trait so `poll` returns the new snapshot or cursor for the engine to commit after delivery. Cover it with a test whose mock source writes a snapshot or cursor in `poll`.
~~~~

Judge: **valid**. The doc comment on `run_once` (engine.rs:110-111) says dry_run does not advance provider cursors. But line 116 calls `source.poll(self.state.as_ref())` every time, and the `Source` contract (traits.rs:48-50) says `poll` writes advanced snapshots and cursors back to state. So a dry run uses up the diff, and a later real run never sees those events. That breaks the documented behavior, and the failed-delivery retry concern follows from the same design.

label: valid - engine.rs:116 calls source.poll(self.state) unconditionally while traits.rs:48-52 says poll persists snapshots/cursors, contradicting the dry_run doc. Fixed by ce3a94a, which moved snapshot persistence to commit_snapshots after delivery and skips it on dry run. Later fix: ce3a94a feat(core): defer snapshot commit until after delivery. (labeled by Claude, high confidence)

## 7. git-stk PR #291: `README.md:144`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/ecceadd60018090618a3e62f6bde29e4fbf67a6d/README.md#L144). PR title: feat(cli): add --from-path to nav commands so cd can follow a branch

~~~~text
**[Bug]**

When `git stk up/down/top/bottom --from-path` fails (held-branch collision, no parent, ambiguous fork), stdout is empty, so this runs `cd ""`. In bash and zsh that is a successful no-op. The `|| return` never fires and the `stk` function returns 0 even though the navigation failed. The PR's own rationale is that a failed navigation must not look like success to a script. Capture the path first so git-stk's exit status is what propagates:

```suggestion
    up|down|top|bottom) dest=$(git stk "$@" --from-path) || return; cd "$dest" || return ;;
```
~~~~

Judge: **valid**. The claim holds. In README.md:144 the snippet is `cd "$(git stk "$@" --from-path)" || return`. When git-stk fails, stdout is empty and git-stk's exit status is thrown away. In bash and zsh, `cd ""` succeeds without changing directory, so the `|| return` never runs and `stk` returns 0. Assigning the output to a variable first fixes this, because the assignment carries git-stk's exit status. This is a small change to a snippet users will copy into their shell config.

label: valid - README.md:144 `cd "$(git stk ... --from-path)"` masks git-stk's exit status. The 'successful no-op' claim holds in zsh and older bash, though bash 5.3 errors with 'null directory'. ca0101c adopted the capture-then-cd fix. Later fix: ca0101c docs(shell): harden the stk wrapper snippet against a failed navigation. (labeled by Claude, medium confidence)

## 8. navi commit a1a570c: `crates/navi-notifier/src/service.rs:26`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/a1a570cf8dedcaaa3b984e539c8f4ffbacf4b92f/crates/navi-notifier/src/service.rs#L26). PR title: feat(cli): add `navi service` to manage the background service

~~~~text
**[Bug]**

`config_path` is passed through verbatim from `--config` (`resolve_config_path` returns an explicit path as-is, and `--config` is `global`). `navi --config ./navi.toml service install` writes `run --config "./navi.toml"` into the unit/plist/task, and `env_file_path` derives a relative `navi.env` the same way. The service starts with its own working directory (`/` for launchd, not your shell's cwd), so it can't find the config and crash-loops (`Restart=on-failure` / `KeepAlive`). Make the path absolute before generating anything, e.g. `let config_path = std::path::absolute(config_path)?;` at the top of `install`.

Relatedly, `install` never checks that the config exists. `navi service install` before `navi init` enables a unit that fails every 10s.
~~~~

Judge: **valid**. `resolve_config_path` (config.rs:296) returns an explicit `--config` path unchanged, and `--config` is a global flag. `install` and `env_file_path` (service.rs:381) never make the path absolute, so a relative path goes straight into ExecStart, EnvironmentFile, the launchd plist and the Windows task. Services don't start in the shell's working directory, so the service can't find the config. systemd also rejects a relative EnvironmentFile path outright. The fix is a one-line change and worth asking for.

label: valid - service.rs:25 install passes config_path verbatim (config.rs resolve_config_path returns explicit paths as-is) into ExecStart and env_file_path, so a relative --config breaks a service with a different cwd. Still unfixed on main (resolve_config_path unchanged, no absolute() in service.rs). (labeled by Claude, medium confidence)

## 9. git-stk PR #113: `src/providers/mod.rs:162`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/2def14f61b0c00de24826f49de38183897f4f94b/src/providers/mod.rs#L162). PR title: feat(cli): self-hosted gitlab, linear/jira docs, nicer guide formatting on small terminals

~~~~text
**[Surface Drift]**

The doc comment names `stk.gitlab.host`, but the key is `stk.gitlabHost` (`GITLAB_HOST_KEY`, the README, and the tests all use that). A user who follows this comment sets a key that is never read.

```suggestion
/// `host/owner/repo` (HTTPS) form. A configured `stk.gitlabHost` widens
```
~~~~

Judge: **valid**. The comment is correct. src/providers/mod.rs:162 says `stk.gitlab.host`, but the real key is `stk.gitlabHost`. That is the value of `GITLAB_HOST_KEY` in src/settings.rs:19, and the README and tests/provider.rs use the same name. The doc comment names a config key that doesn't exist, so it's a factual error rather than a wording issue, and the fix is a one-line change.

label: nit - src/providers/mod.rs:162 doc comment says stk.gitlab.host but settings.rs:19 GITLAB_HOST_KEY is stk.gitlabHost. True, but it is a private fn doc comment, so the user impact is overstated; fixed in passing by 96f4162 feat/docs cleanup (#120). Later fix: 96f4162 feat/docs cleanup (#120). (labeled by Claude, medium confidence)

## 10. navi PR #85: `crates/navi-notifier-github/src/source.rs:784`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/4443b196008a725c46ea4a1bec2bd620b0c8ca95/crates/navi-notifier-github/src/source.rs#L784). PR title: feat(github): detect merge-queue enter/exit via GraphQL

~~~~text
**[Complexity]**

The new `ts_key`, `is_fresh_no_queue` and `merge_queue_change` were inserted between the `/// Parse \`https://api.github.com/repos/{owner}/{repo}/pulls/{number}\`` doc comment and `parse_pr_url`. `ts_key` now carries the wrong doc and `parse_pr_url` has none. Move this doc line back above `fn parse_pr_url`, or place the new helpers elsewhere.
~~~~

Judge: **valid**. The comment is accurate. At source.rs:784 the doc comment for parse_pr_url sits directly above ts_key, which already has its own doc line on 785. So ts_key ends up with two doc lines, one of them wrong, and parse_pr_url at line 828 has no doc at all. The misplacement came from inserting code in the wrong spot and is easy to fix, so it's worth asking the author to move the line back.

label: nit - source.rs:784 leaves the parse_pr_url doc line above ts_key and parse_pr_url (line 828) has none; true but cosmetic. Corrected later in a39f423 during a refactor that tidied comments. Later fix: a39f423 refactor(forge): share is_settled/ts_key/excerpt with the gitlab source + tidy comments. (labeled by Claude, high confidence)

## 11. git-stk PR #94: `src/providers/github.rs:72`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/e12851e3ff9681f288d57775a4970a079f41c02a/src/providers/github.rs#L72). PR title: chore(cli): make merge --wait more durable

~~~~text
**[Missing Coverage]**

The new polling behavior has no test: not pending→green, not the grace window (`NoneYet` ×6 then merge, and the reset on `Pending`), and nothing at all for the GitLab `None`/reset logic in `gitlab.rs`. The only integration test touched (`merge_all_wait_gates_each_merge_on_checks`) now exits 0 on the first poll, so the loop and sleep are never exercised. The cause is that `check_poll_interval()` is a function returning a hard-coded 5s with no override. Any pending or no-checks test would take at least 30s, and the function has no reason to exist as a function. Make the interval and grace injectable, for example through an env var that the `tests/merge.rs` fake-CLI tests set. Then add tests with a fake `gh` that returns 8 then 0, and one that returns "no checks reported" then 0. Add the same for `glab` with a null `head_pipeline` followed by `success`.
~~~~

Judge: **valid**. The comment's claims check out. `check_poll_interval()` in `src/providers/mod.rs:16` always returns 5s and can't be overridden. The polling loops in `github.rs:72-99` and `gitlab.rs:87-109` have no tests: not pending then green, not the grace count, not the reset on `Pending`. Only `interpret_checks` has unit tests, and the one integration test exits 0 on the first poll, so the loop never runs. The grace and reset logic is the main change in this PR, and the fixed interval makes it impractical to test (at least 30s per case). Asking for an injectable interval and tests is reasonable.

label: nit - True: src/providers/mod.rs:16 check_poll_interval is a hard-coded 5s, and the tests/merge.rs change replaced the pending case with exit 0, so the poll loop at src/providers/github.rs:72-98 and gitlab None handling are untested. Coverage request only; never added, and the function is unchanged on main. (labeled by Claude, medium confidence)

## 12. git-stk PR #188: `src/setup.rs:210`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/446248ae376cb9edbf54141b2890b28d73c04934/src/setup.rs#L210). PR title: feat(cli): add uninstall docs/command

~~~~text
**[Bug]**

Detection uses `contents.contains(COMPLETION_MARKER)` but removal in `strip_completion_block` requires a whole line equal to the marker (`line.trim() == COMPLETION_MARKER`). If the marker appears mid-line (e.g. inside a longer comment), uninstall lists "completion line in <rc>", asks for confirmation, then silently removes nothing, and the "removed … completion line" message is skipped. Compute `strip_completion_block(&contents)` up front and use that result as the detection, so the plan and the action cannot disagree.
~~~~

Judge: **nit**. The mismatch is real. Detection at line 210 uses `contains(COMPLETION_MARKER)`, while `strip_completion_block` (line 297) only matches a line whose trimmed text equals the marker. But the marker is a specific string that setup always writes on its own line. It would only appear mid-line if the user edited the rc file by hand in an unusual way, so the bug needs an unlikely input. If it did happen, uninstall would remove nothing, which is harmless. Making the plan and the action use the same check is a reasonable cleanup, not a required fix.

label: nit - True mismatch: src/setup.rs:210 detects with contents.contains(COMPLETION_MARKER) while strip_completion_block (setup.rs:297) needs a whole-line match. Only matters if the marker sits mid-line, which is unlikely, and the only effect is a no-op plus a misleading list. 445b2ab (#208) tightened stripping but left detection as contains(). (labeled by Claude, medium confidence)

## 13. navi commit b766245: `crates/navi-notifier/src/setup.rs:250`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/b766245a6de5ff7c6d3619e36284517b65795f9d/crates/navi-notifier/src/setup.rs#L250). PR title: feat(cli): add completions, setup, upgrade, downgrade, uninstall

~~~~text
**[Safety]**

`remove_dir_all` deletes the whole navi config directory. On Linux that is `~/.config/navi`, so it removes the user's `config.toml`, which holds their forge and Slack tokens. That is irreversible, and `--yes` skips the only guard. The prompt text says "config and install receipt", but nothing here limits the deletion to the receipt. The final note says state is "left", which is inconsistent with wiping the config. Delete only the files navi itself created (the install receipt and the `update-check` stamp), or make config removal an explicit separate opt-in such as `--purge`. As written, `uninstall -y` also deletes config on a reinstall-style cleanup.
~~~~

Judge: **nit**. It's true that `remove_dir_all` deletes the whole navi config directory, including `config.toml` and its tokens. But that looks deliberate and is disclosed: the docstring says it removes "the config/receipt directory", the prompt lists "config and install receipt", and the final note says "~/.config/navi is removed above; state db is left". That note is consistent with the deletion, so the comment's inconsistency claim misreads it. The comment also implies the prompt promises a receipt-only deletion, which it doesn't. Adding a `--purge` flag is a reasonable design preference, not a defect.

label: nit - crates/navi-notifier/src/setup.rs:250 does remove_dir_all on ~/.config/navi on Linux, which includes config.toml. The doc comment (setup.rs:190) and prompt ('config and install receipt') state that config is removed, so this is a design choice. The closing note's wording is inconsistent. Unchanged on main. (labeled by Claude, medium confidence)

## 14. git-stk PR #293: `src/settings.rs:150`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/e0a3eec0c8aba58322a3f98a89d0f402ea49ccd5/src/settings.rs#L150). PR title: feat(cli): add new --worktree, with git-stk owning the worktrees it creates

~~~~text
**[Bug]**

`stk.worktreeDir` is read as a raw string, so `~` is never expanded. The README example this PR adds is `worktreeDir = ~/code/myrepo-worktrees`. With that value, `std::path::absolute` yields `<cwd>/~/code/myrepo-worktrees`, so `new --worktree` creates a literal `~` directory inside whatever directory the command ran from. A relative value also resolves against the cwd, not the repo, so the location depends on where the user ran the command.

Read the key with `git config --type=path --get`, which expands `~` and `~user`. Add a path-typed getter next to `config_get_bool`. Either resolve relative values against the repo root or document that they are cwd-relative. Add a test with a `~`-prefixed value.
~~~~

Judge: **valid**. The bug is real. `worktree_dir` (src/settings.rs:147-150) reads the key with plain `git config --get`, which does not expand `~`, and then passes the result to `std::path::absolute`, which resolves it against the cwd. With the README example this PR adds (`worktreeDir = ~/code/myrepo-worktrees`, README.md:499), the command would create a literal `~` directory under the cwd. Reading the key with `--type=path` fixes it.

label: valid - src/settings.rs:147-150 reads stk.worktreeDir with plain git config --get and calls std::path::absolute, so the README example 'worktreeDir = ~/code/myrepo-worktrees' resolves to <cwd>/~/... Still unfixed on main (settings.rs:227-231, README.md:312). (labeled by Claude, high confidence)

## 15. git-stk PR #102: `src/commands/run.rs:77`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/8dfcccc18afadbbcaf834ec2bf5485dab5b19efd/src/commands/run.rs#L77). PR title: feat(cli): git stk run command on all branches in stack

~~~~text
**[Bug]**

The dirty-tree check only runs once, before the loop, but the user's command runs between checkouts. A build or test command that modifies tracked files (lockfile or snapshot updates, formatters) or creates untracked files makes the next `git switch` fail. The `?` then aborts `run_each` and discards every result collected so far, so the summary is never printed and the user sees only "failed to check out X". Either keep the partial results and print the summary before propagating the error, or check `worktree_is_clean()` after each command and report that branch as dirty. There is no test for a command that dirties the tree.
~~~~

Judge: **valid**. This is a real problem. `worktree_is_clean()` is only checked once, before the loop (run.rs:32). `run_each` calls `checkout(branch)?` (`git switch`) after each command has run. If a command dirties a tracked file that differs between stacked branches (common with lockfiles and snapshots), the switch fails. The `?` then throws away the `results` vector, `print_summary` never runs, and the user sees only "failed to check out X". The comment overstates one point: untracked files, or edits to files that are the same on both branches, don't make `git switch` fail. In those cases the changes are carried onto the next branch without any warning, which is arguably worse. The underlying fragility is real, and the fix the comment suggests is worth doing.

label: valid - src/commands/run.rs:77 propagates a checkout failure with ?, which discards collected results before print_summary (run.rs:57-59). A command that dirties tracked files that differ between branches makes git switch fail. 58ae67a (run in scratch worktree by default) sidesteps the user's checkout but still uses ? on checkout_detached_in, and --no-worktree keeps this path. (labeled by Claude, medium confidence)

## 16. git-stk PR #267: `src/providers/mod.rs:326`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/d1ccaddbf441e7b46903d0d6e7488a229404cd43/src/providers/mod.rs#L326). PR title: feat(list): add --reviews and --local flags for rich review info

~~~~text
**[Missing Coverage]**

`generic_annotate` has no test. It is the only annotation path for GitLab and Gitea, and it is also the fallback when GitHub's batched GraphQL fails. It filters `open_reviews` by branch, merges queue state, and swallows per-branch errors, and none of that is exercised. `tests/list_status.rs` only fakes `gh api graphql`, so the success path is covered but the fallback is not. Please add an integration test in `tests/list_status.rs` where the `api graphql` fake fails and `pr list`/`pr view` fakes supply the data, and ideally one GitLab/Gitea `list` test.
~~~~

Judge: **wrong**. The comment says generic_annotate has no coverage, but that's false. `list` calls `annotate_branches` (src/commands/list.rs:28). For GitLab and Gitea, that defaults to `generic_annotate`. The existing test `tests/list_markdown.rs:43` (`list_annotates_gitlab_mr_numbers_without_the_deprecated_opened_flag`) runs `list` with the gitlab provider and a faked `mr list`, then asserts `!34` appears. So the open_reviews filter-by-branch path is already exercised. Coverage of the GraphQL-failure fallback is thinner, but it reuses this same function.

label: nit - True: generic_annotate (src/providers/mod.rs:326) is the GitLab/Gitea path and the GitHub fallback (github.rs:215), and tests/list_status.rs only fakes a successful api graphql. Coverage request only; later commits added related tests (e.g. a failing-graphql and a gitlab status test in tests/list_status.rs), not as a direct fix. (labeled by Claude, medium confidence)

## 17. navi commit b766245: `crates/navi-notifier/src/upgrade.rs:30`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/b766245a6de5ff7c6d3619e36284517b65795f9d/crates/navi-notifier/src/upgrade.rs#L30). PR title: feat(cli): add completions, setup, upgrade, downgrade, uninstall

~~~~text
**[Bug / Safety]**

This hand-rolls a config dir instead of using `ProjectDirs::from("dev", "navi", "navi")`, the seam `config.rs:300` uses, so the two disagree. On macOS, which is a release target, `config.toml` is in `~/Library/Application Support/dev.navi.navi`, but this returns `~/.config/navi`. On Windows it returns `%LOCALAPPDATA%\navi`, while directories uses `%APPDATA%`. The update-check stamp therefore lands in a different place from the real config, and `uninstall` will `remove_dir_all` an unrelated `~/.config/navi` on macOS.

On Linux the two paths do match. There `uninstall` (`setup.rs:250`) recursively deletes the user's `config.toml`, which holds Slack, GitHub and SMTP credentials. It does this with no backup and only a generic prompt, and `-y` skips even that. It also does not delete the cargo-dist receipt: that sits under the app name (`navi-notifier`), not `navi`.

Suggested fix:
- Derive the directory from `ProjectDirs`.
- Have `uninstall` delete only files navi owns, for example the update-check stamp and the receipt.
- Leave `config.toml` alone, or name it explicitly in the prompt and require a separate opt-in to delete it.
~~~~

Judge: **valid**. The bug is real. `upgrade::config_dir()` builds the path by hand from XDG_CONFIG_HOME, then LOCALAPPDATA, then ~/.config, and appends `navi`. `config.rs:300` uses `ProjectDirs::from("dev","navi","navi")` instead, so the two give different paths on macOS (~/Library/Application Support/dev.navi.navi) and on Windows (%APPDATA% vs %LOCALAPPDATA%). Because of this, the update-check stamp lands away from the real config, and `uninstall` (`setup.rs:250`) runs `remove_dir_all` on a ~/.config/navi directory that navi doesn't own on macOS. On macOS it also never removes the real config. The part about credentials is weaker, since the prompt does say "config and install receipt". The path mismatch alone is worth fixing.

label: valid - crates/navi-notifier/src/upgrade.rs:30-36 builds XDG/LOCALAPPDATA/~/.config + 'navi', while config.rs:300 uses ProjectDirs::from(dev,navi,navi), so on macOS uninstall deletes ~/.config/navi instead of the real config dir. The cargo-dist receipt is keyed by package name navi-notifier (Cargo.toml:2), so it is not removed either. Unchanged on main. (labeled by Claude, medium confidence)

## 18. git-stk PR #102: `src/commands/run.rs:56`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/8dfcccc18afadbbcaf834ec2bf5485dab5b19efd/src/commands/run.rs#L56). PR title: feat(cli): git stk run command on all branches in stack

~~~~text
**[Error Handling]**

`let _ = crate::git::checkout(&original);` swallows a failed restore. This is the realistic case: the command leaves tracked or untracked files that conflict with `original`, or modifies a tracked file, so `git switch` refuses. The command then exits as if it succeeded, or reports only the command failure, and the user is left on the last stack branch with no message. The README promises "returns you to the branch you started on". Report the restore failure, for example with `eprintln!` of a warning that names `original`, or by returning it when `result` is `Ok`.
~~~~

Judge: **valid**. Line 56 (`let _ = crate::git::checkout(&original);`) does throw away the restore error. If every branch passed, the command exits 0 and leaves the user on the last stack branch, which breaks the stated promise of returning to the starting branch. One detail is overstated: `git::status` writes git's stderr when it fails, so the user sees git's raw error, but git-stk itself says nothing and the exit code still reports success. Reporting this failure is a reasonable change to ask for.

label: valid - src/commands/run.rs:56 'let _ = crate::git::checkout(&original)' silently ignores a failed restore, leaving the user on another branch with no message, which contradicts the README promise. The same line survives in the --no-worktree path after 58ae67a. (labeled by Claude, medium confidence)

## 19. git-stk PR #94: `src/providers/mod.rs:18`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/e12851e3ff9681f288d57775a4970a079f41c02a/src/providers/mod.rs#L18). PR title: chore(cli): make merge --wait more durable

~~~~text
**[Missing Coverage]**

The new behavior (grace window then proceed, grace reset on a real pending state, GitLab `None` pipeline tolerance) has no test. Only the pure `interpret_checks` classifier is unit-tested. The loops themselves aren't exercised, and GitLab `wait_for_checks` has no test at all. Because the interval is hard-coded to 5s and `CHECK_GRACE_POLLS` to 6, the `tests/merge.rs` fake-CLI tests could only reach the grace path by sleeping 30s. Make the interval and grace injectable into the loop (e.g. a shared helper taking interval/grace parameters that the providers call with the constants). Then add fake-`gh` and fake-`glab` tests for "no checks, then pending, then green" and "no checks past the grace window". As it stands, `check_poll_interval()` is a function returning a constant with no override, which adds indirection without enabling anything.
~~~~

Judge: **nit**. The claim checks out. `check_poll_interval()` just returns a hard-coded 5s and `CHECK_GRACE_POLLS` is fixed at 6. The tests in tests/merge.rs only cover green and failed checks, so neither provider's grace-window loop or GitLab's `None` handling is tested. Still, this asks for a refactor to make the loops testable plus new tests. It doesn't point to an actual bug in the loop logic, so it's a reasonable suggestion rather than a defect worth requiring a change for.

label: nit - Duplicate of n=11: src/providers/mod.rs:13-18 hard-codes CHECK_GRACE_POLLS=6 and a 5s interval, so the loops and gitlab wait_for_checks are untested and only interpret_checks has unit tests. Coverage/testability request; never changed on main. (labeled by Claude, medium confidence)

## 20. navi commit 6ac3538: `crates/navi-notifier/src/config.rs:100`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/6ac3538d7bea049cc97e7172f5df2a7a084b23c4/crates/navi-notifier/src/config.rs#L100). PR title: feat(gitea): add gitea/forgejo source reusing the forge engine

~~~~text
**[Surface Drift]**

This adds a new user-facing `[gitea]` config section and provider, but `README.md` still says Gitea/Forgejo is "planned" (line 11). The crates table (around line 149) also has no `navi-notifier-gitea` row. The earlier docs commit (`e580ccb`) listed the GitLab and Discord providers, so this one should do the same. Update both places and mention the `NAVI_GITEA_TOKEN` and `api_base` settings.
~~~~

Judge: **valid**. I checked this against the code and it holds. README.md:11 still says Gitea/Forgejo support is "planned", and the crates table at lines 147-151 has no navi-notifier-gitea row. But this PR adds a user-facing `[gitea]` config section with `api_base` and a `NAVI_GITEA_TOKEN` default. The repo already updated the docs when it added GitLab and Discord, so this is real, user-visible docs drift worth fixing.

label: valid - At the PR head, README.md:11 still says Gitea/Forgejo is 'planned' and the crates table has no navi-notifier-gitea row, while config.rs adds a [gitea] section. The next commit c536b58 'docs(docs): add fairy logo and list gitea provider' updated both places. Later fix: c536b58 docs(docs): add fairy logo and list gitea provider. (labeled by Claude, medium confidence)

## 21. git-stk PR #301: `src/commands/up.rs:35`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/c062bf1597c9b3b98bf1b15dcac6db739aa80350/src/commands/up.rs#L35). PR title: feat(navigation): up/down take number of branches to move

~~~~text
**[Surface Drift]**

This silently changes `git stk up <name>` for digit-only child branches (e.g. issue-number branches like `123`). Before, `git stk up 123` checked out the child. Now it is parsed as a distance and fails with "cannot go up 123: ... is only 1 branch below ...". There is no way left to pick that child by name with `up`. The code comment mentions it, but neither the CHANGELOG entry nor the README does. Please record the behavior change in both. Better, resolve the ambiguity in favour of the existing contract: if the value exactly matches a child of the current branch, treat it as a branch. Otherwise treat it as a distance. That check needs the current branch, so move it into `checkout_child`.
~~~~

Judge: **nit**. The claim is accurate. `parse_target` (up.rs:34-39) reads any integer string as a distance, so `up 123` no longer picks a child branch named `123`, and neither CHANGELOG nor README mentions this. But the author clearly chose this on purpose: the code comment at lines 26-27 calls out the tradeoff. Child branches named only with digits are an unusual edge case, and plain `git checkout 123` still works. So this is worth noting, not worth requesting a change.

label: nit - True that parse_target (src/commands/up.rs:35) reads any integer as a distance, but the Target doc comment states digit-only branch names must be reached by name elsewhere, so this is a documented design choice affecting a rare naming case. Merged unchanged in 96ba137 and still the same on main. (labeled by Claude, medium confidence)

## 22. git-stk PR #130: `src/commands/submit.rs:253`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/f6e0007940e62633ddde27ec2993f50f3fe73b56/src/commands/submit.rs#L253). PR title: fix(cli): offer to close dated PRs

~~~~text
**[Bug]**

The prompt always says "and delete its branch", but `GitLabProvider::close_review` ignores `delete_branch` and runs only `glab mr close`. On GitLab the user is told the branch is deleted when it is not. Fix: have the provider report whether it deleted the branch, or word the prompt according to provider capability.
~~~~

Judge: **valid**. The claim checks out. The prompt at submit.rs:253-255 always asks "...and delete its branch?", and the code then calls close_review(&review, true). GitLabProvider::close_review (gitlab.rs:116) ignores `_delete_branch` and runs only `glab mr close`. Its own comment says the remote branch "may linger". The demo provider ignores the flag too. So on GitLab, the user agrees to a branch deletion that never happens. The PR adds this misleading prompt, so it is worth fixing.

label: valid - submit.rs:253 prompt says 'and delete its branch' for every provider, while GitLabProvider::close_review (src/providers/gitlab.rs:116) ignores delete_branch and only runs glab mr close. So GitLab users get a false prompt. Prompt and gitlab impl are unchanged on main. (labeled by Claude, medium confidence)

## 23. git-stk PR #188: `tests/setup.rs:205`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/446248ae376cb9edbf54141b2890b28d73c04934/tests/setup.rs#L205). PR title: feat(cli): add uninstall docs/command

~~~~text
**[Missing Coverage]**

Both integration tests plant a perfectly shaped install. Nothing covers the paths that make uninstall destructive: declining the prompt (no `-y`, stdin `n`/EOF must leave everything intact), an rc file whose marker is not followed by the completion line, an rc file with no marker (a hand-added `git stk completions` line must be left alone), and nothing installed. Add integration tests in `tests/setup.rs` using the same `plant_install` helper for these, plus a unit test in `src/setup.rs` for the marker-without-completion-line case.
~~~~

Judge: **valid**. The comment is accurate. The only uninstall integration tests are `uninstall_removes_the_setup_and_installer_footprint` (`-y`) and `uninstall_dry_run_removes_nothing`, and both start from a complete install. Nothing tests declining the prompt (no `-y`, stdin `n` or EOF), having nothing installed, or a hand-added completion line with no marker. One of the listed cases also hides a real bug: `strip_completion_block` always deletes the line right after the marker (`end = marker + 2`) without checking that it is the completion line. If a user edited their rc file, one of their own lines would be silently removed. Since this command deletes files, asking for these tests is a reasonable change to request.

label: valid - The coverage gap it names includes a real bug: strip_completion_block (src/setup.rs) always removed the line after the marker, even when it was not the completion line. Later fixed with exactly the requested unit test in 445b2ab. The other requested integration tests were never added. Later fix: 445b2ab fix(upgrade): only remove lines that came from us in uninstall (#208). (labeled by Claude, medium confidence)

## 24. navi commit a1a570c: `crates/navi-notifier/src/service.rs:106`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/a1a570cf8dedcaaa3b984e539c8f4ffbacf4b92f/crates/navi-notifier/src/service.rs#L106). PR title: feat(cli): add `navi service` to manage the background service

~~~~text
**[Architecture]**

This PR adds a persistent user service that is not known to `navi uninstall` (setup.rs:193), which the CLI describes as reversing "`setup` and the installer". Running `navi uninstall` deletes the config dir (including `navi.env`) and says to remove the binary, but leaves the unit, plist or task enabled. It then starts at every login or restarts every 10s against a missing config/binary. `uninstall` should detect an installed service and stop and remove it (or at least list it and point to `navi service uninstall`), including in its `--dry-run` output.
~~~~

Judge: **valid**. `setup::uninstall` (setup.rs:193) only removes the completion line, the man page and the config dir. It never checks for or removes the systemd unit, launchd plist or scheduled task that this PR adds, and `init` now offers to install that service. After `navi uninstall`, the unit stays enabled with Restart=on-failure and RestartSec=10 (KeepAlive on macOS), but its config and binary are gone, so it keeps failing and restarting. This is a real gap in the uninstall path the PR should cover.

label: valid - setup.rs uninstall (around line 193) removes completions, the man page and the config dir (which holds navi.env) but never checks for the systemd/launchd/schtasks service that service.rs installs with Restart=on-failure. That leaves an enabled service behind. Never addressed: setup.rs uninstall still has no service handling on main. (labeled by Claude, medium confidence)

## 25. navi PR #110: `crates/navi-notifier/src/editor.rs:11`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/e50c8abb885c563edff56b4f947b111778ce9039/crates/navi-notifier/src/editor.rs#L11). PR title: feat(cli): add `navi config edit` and `navi env` to open files in $EDITOR

~~~~text
**[Missing Coverage]**

The PR adds editor resolution (`VISUAL` → `EDITOR` → default, blank-value filtering, flag splitting), `envfile::edit` (creates `navi.env` at 0600 when missing, leaves an existing file untouched) and `config_cmd::edit` (missing-config error, parse warning), with no tests. The rest of the crate keeps unit tests next to the code (`envfile.rs` and `config_cmd.rs` have `mod tests`). Please extract a pure `resolve_editor(visual: Option<String>, editor: Option<String>) -> String` that can be tested without touching process env, and add tests for `envfile::edit` using a fake editor such as `VISUAL=true`. They should check that a new `navi.env` is mode 0600 and that an existing one is not overwritten. Also add one for `config_cmd::edit` bailing on a missing config.
~~~~

Judge: **nit**. The comment is accurate: `editor::open`, `envfile::edit` and `config_cmd::edit` have no tests, while nearby modules have `mod tests`. Still, this is thin glue code for launching an interactive editor. It's simple, and testing it means changing process env (`VISUAL`) or spawning processes, which can make tests flaky. No bug is identified, so asking for tests is a suggestion rather than a needed fix.

label: nit - True that editor.rs, envfile::edit and config_cmd::edit have no tests, but this is thin glue around env vars and spawning a process. No tests were ever added: editor.rs on main still has no test module. (labeled by Claude, medium confidence)

## 26. navi commit f97c268: `crates/navi-notifier-core/src/rules.rs:98`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/f97c2685701ae6f8e3a43e88510a6c92ca6e9b64/crates/navi-notifier-core/src/rules.rs#L80). PR title: feat(core): add domain model, provider traits, rule filter, and engine

~~~~text
**[Error Handling]**

Quiet hours fail open and silently. With `enabled = true` and a malformed `start`/`end` (e.g. `"8am"`, `"24:00"`) or `local_minutes == None`, `in_quiet_hours` returns `false` and the user gets pinged during the hours they asked to be left alone, with no log or error. Validate `HH:MM` when the config is loaded (or at least `warn!` here). Also, `config.rs` documents "non-urgent events are suppressed", but there is no urgency notion here. Every kind, including `ReviewRequested`, is dropped, and given the snapshot-advance issue on `poll` those drops may be permanent. Either implement the exemption or fix the doc.

Missing coverage: no test for the same-day window, the `start == end` case, or malformed times. The repo-level `deny` precedence over `allow` and the `local_minutes: None` path are also untested.
~~~~

Judge: **valid**. The claim matches the code. If `start`/`end` are malformed, `in_quiet_hours` silently returns false and events still get delivered. Nothing validates the times or logs a warning: `parse_hhmm` is only called here, and there is no `warn!` in rules.rs. `config.rs:97` says "non-urgent events are suppressed", but there is no notion of urgency, so every event kind is dropped during quiet hours. The listed test gaps are also real: the only quiet-hours test covers the window that wraps midnight. One overstatement: `local_minutes == None` turning quiet hours off is documented as intended. Even so, the main point about failing open on bad config, plus the doc mismatch, is worth asking the author to fix.

label: valid - in_quiet_hours (rules.rs:80-98) returns false on a malformed HH:MM with no log, and config.rs:97 documents 'non-urgent' suppression that does not exist. Later aab8410 added HH:MM validation (flags_bad_quiet_hours_time test), 650709d removed the 'non-urgent' wording, and 63e5796 deferred quiet-hours events instead of dropping them. Later fix: aab8410 feat(cli): validate config in `navi doctor` (static checks + --offline). (labeled by Claude, medium confidence)

## 27. git-stk PR #266: `tests/navigation.rs:534`

[Code at the PR head](https://github.com/lararosekelley/git-stk/blob/b4b770c91afc4aa1e400533a9d50ea8d51c7ac23/tests/navigation.rs#L530). PR title: feat(list): separate stacks better in list --all

~~~~text
**[Missing Coverage]**

The comment says the fork stays in one block, but the assertions only check that each branch name appears somewhere in the output. They would still pass if `feature/c` and `feature/d` were split into separate blocks, and also if `feature/a` and `feature/b` were merged into one. Split stdout on `"\n\n"` and assert that there are two blocks. Assert that `feature/a` is alone in one of them and that `feature/b`, `feature/c` and `feature/d` are all in the other. Each block should contain exactly one `(trunk)`.
~~~~

Judge: **nit**. It's true that the loop at lines 532-534 only checks that each name appears, so it doesn't test what its comment says. But the test already asserts `(trunk)` appears exactly twice (lines 520-524). Splitting c and d into separate trunk blocks would make that 3, and merging a and b would make it 1, so both failures the comment names are already caught. Parsing the blocks would only add a little extra strictness.

label: wrong - The test (tests/navigation.rs:516-521) asserts that exactly two '(trunk)' markers appear, and the trunk repeats per block. Splitting c/d into separate blocks would give 3, and merging a with b would give 1, so both regressions the comment names would fail. Test merged unchanged in 954fdbb. (labeled by Claude, medium confidence)

## 28. navi PR #131: `crates/navi-notifier/src/config.rs:420`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/c206ed28cc1cbe3111801ac564bbed6af03bf266/crates/navi-notifier/src/config.rs#L402). PR title: feat(cli): validate config in `navi doctor` (static checks + --offline)

~~~~text
**[Architecture]**

`KNOWN_TAGS` is a hand-copied third list of event tags alongside `EventToggles::is_known_tag` and `EventKind::match_tags` in core. The doc comment says it is "kept in sync with the model by the `broadcast_tags_are_all_known` test", but no such test exists. The test that was added (`default_broadcast_tags_are_all_known`) only checks that the default broadcast set validates, so a new `EventKind` variant will not fail anything. Also, `digest.kinds` is matched against `event.kind.tag()` only (`engine.rs:284`), so the per-state `review_approved`, `review_changes_requested` and `review_commented` tags in `digest.kinds` never match, yet they pass validation here. Derive the list from core (or add a test that iterates the `EventKind` tags), and validate `digest.kinds` against the umbrella tags only.
~~~~

Judge: **valid**. I checked each claim against the code and they all hold. No test named `broadcast_tags_are_all_known` exists. The only related test, `default_broadcast_tags_are_all_known`, checks just the default broadcast set, so the doc comment points to a test that isn't there and nothing catches drift. The bigger problem is `digest.kinds`: it is matched only against `event.kind.tag()` (engine.rs:284), so the per-state tags `review_approved`, `review_changes_requested` and `review_commented` can never match. Validation still accepts them for `digest.kinds` (config.rs:548-549). That is exactly the kind of silently dead config this validator is meant to catch.

label: valid - The KNOWN_TAGS doc (config.rs:402-404) cites a broadcast_tags_are_all_known test that did not exist, and default_broadcast_tags_are_all_known only validates defaults. Later a698c63 added known_tags_cover_every_event_tag, which iterates EventKind::match_tags. The digest.kinds per-state tag point was not addressed. Later fix: a698c63 refactor(cli): dedupe provider id lists + enabled/creds across config, providers, wiring, doctor. (labeled by Claude, high confidence)

## 29. navi commit 244e1c4: `crates/navi-notifier-github/src/source.rs:203`

[Code at the PR head](https://github.com/lararosekelley/navi/blob/244e1c45f83fef5f54b47fbde48206fa5aa12e3e/crates/navi-notifier-github/src/source.rs#L203). PR title: feat(github): add github source with notifications poll and timeline diff

~~~~text
**[Error Handling]**

A corrupt or unparseable snapshot for one PR returns `Err` from the whole `poll` through `?`. That discards `events` already collected for earlier PRs, even though their snapshots were persisted on line 222, so those events are lost for good. It also wedges the source. `notif_since` is never advanced, so every later poll hits the same PR and fails the same way. This is inconsistent with the `fetch_pr` failure path just above, which skips only that PR.

On a snapshot parse error, `warn!` and either skip that PR or treat the snapshot as absent. Don't abort the poll.
~~~~

Judge: **valid**. The code matches the comment. At line 204, `?` propagates a snapshot parse error out of `poll`. Events from earlier PRs in the same loop are dropped, but their snapshots and thread cursors were already written (lines 222 and 224), so those events are suppressed for good. `notif_since` (line 236) is never advanced and this thread's cursor isn't written either, so every later poll hits the same corrupt snapshot and fails again. This contradicts the skip-on-error handling of `fetch_pr` just above it. Because the fields use `#[serde(default)]`, a corrupt snapshot is unlikely in practice, but if one ever happens the source stops working permanently and events are silently lost. The suggested fix (warn, then skip or treat the snapshot as absent) is cheap.

label: nit - True that a snapshot parse error at source.rs:201-203 aborts poll via ?, unlike the fetch_pr skip path. But snapshots are written by navi itself and every PrSnapshot field is #[serde(default)], so corruption is unlikely. The same ? on parse is still on main (source.rs:359-361). (labeled by Claude, medium confidence)
