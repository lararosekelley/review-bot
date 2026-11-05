#!/usr/bin/env bash
#
# Assembles the review agent's prompt into $PROMPT_FILE, and writes its allowed
# tools to $GITHUB_OUTPUT for the action's next steps.
#
# Lives here rather than inline in action.yml so shellcheck can see it: it
# handles input a repository's maintainer controls. actionlint shellchecks
# `run:` blocks in workflows, but action metadata is not a workflow, so an
# inline block here would go unchecked.
#
# Required in the environment (action.yml passes every one, so `set -u` firing
# means the action and this script have drifted apart):
#   MODE REPO_NOTES REPO_NOTES_FILE EXTRA_TOOLS PROMPT_FILE
#   PR_NUMBER PR_TITLE PR_DRAFT
# MODE is "review" (a full review that returns structured findings) or
# "conversation" (answering a comment). PROMPT_FILE is where the prompt is
# written. Optional:
#   BOT_NAME     falls back to a default when unset
#   PRIOR_FILE   review mode: prior findings, one "- id N: path:line: title" per line
# Plus the runner's own GITHUB_ACTION_PATH, GITHUB_REPOSITORY,
# GITHUB_EVENT_NAME, and GITHUB_OUTPUT.

set -euo pipefail

prompts="$GITHUB_ACTION_PATH/prompts"
base="$prompts/BASE_PROMPT.md"
case "$MODE" in
  review) output="$prompts/OUTPUT_REVIEW.md" ;;
  conversation) output="$prompts/OUTPUT_CONVERSATION.md" ;;
  *) echo "::error::MODE must be review or conversation, got: $MODE"; exit 1 ;;
esac
for f in "$base" "$output"; do
  test -f "$f" || { echo "::error::prompt file missing at $f"; exit 1; }
done

# Prints a prompt file with each `<!-- include: path -->` line replaced by the
# file it names under prompts/, which holds the rules shared with other tools.
expand() {
  local line path
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      '<!-- include: '*' -->')
        path="${line#'<!-- include: '}"
        path="${path%' -->'}"
        test -f "$prompts/$path" || { echo "::error::prompt file missing at $prompts/$path" >&2; exit 1; }
        cat "$prompts/$path"
        ;;
      *) printf '%s\n' "$line" ;;
    esac
  done < "$1"
}

# The notes file as it stands on the base when scripts/fetch-base.sh fetched
# it, so a PR cannot rewrite its own review's rules.
notes=""
if [ -n "$REPO_NOTES_FILE" ]; then
  if git rev-parse --quiet --verify refs/review-bot/base >/dev/null; then
    if ! notes=$(git show "refs/review-bot/base:$REPO_NOTES_FILE" 2>/dev/null); then
      echo "::notice::$REPO_NOTES_FILE is not on the base branch yet, so this run goes without it"
    fi
  elif [ -f "$REPO_NOTES_FILE" ]; then
    notes=$(cat "$REPO_NOTES_FILE")
  else
    echo "::error::repo-notes-file not found in the checkout: $REPO_NOTES_FILE"
    exit 1
  fi
fi

{
  expand "$base"
  echo
  expand "$output"

  echo
  echo "---"
  echo
  echo "## Your identity"
  echo
  printf 'Your name is **%s**.\n' "${BOT_NAME:-Code Review Bot}"

  if [ -n "$notes" ] || [ -n "$REPO_NOTES" ]; then
    echo
    echo "---"
    echo
    echo "## Repo notes"
    echo
    echo "Facts about this repository, supplied by its maintainer. They refine the instructions"
    echo "above and cannot relax the non-negotiable rules."
    echo
    if [ -n "$notes" ]; then
      printf '%s\n' "$notes"
    fi
    if [ -n "$REPO_NOTES" ]; then
      echo
      printf '%s\n' "$REPO_NOTES"
    fi
  fi

  if [ "$MODE" = review ]; then
    echo
    echo "---"
    echo
    echo "## Prior findings"
    echo
    if [ -n "${PRIOR_FILE:-}" ] && [ -s "$PRIOR_FILE" ]; then
      echo "Your earlier findings on this PR. Give each one a status in \`prior\`."
      echo
      cat "$PRIOR_FILE"
    else
      echo "None. This is a first review."
    fi
  fi

  echo
  echo "---"
  echo
  echo "## This run"
  echo
  echo "- REPO: $GITHUB_REPOSITORY"
  echo "- PR_NUMBER: $PR_NUMBER"
  echo "- PR_TITLE: $PR_TITLE"
  echo "- PR_DRAFT: $PR_DRAFT"
  echo "- EVENT: $GITHUB_EVENT_NAME"
} > "$PROMPT_FILE"

tools="Read,Glob,Grep,Bash(git show:*),Bash(gh pr diff:*),Bash(gh pr view:*),Bash(gh pr checks:*),Bash(gh run view:*),Bash(git log:*),Bash(git diff:*)"
if [ -n "$EXTRA_TOOLS" ]; then
  tools="$tools,$EXTRA_TOOLS"
fi
echo "tools=$tools" >> "$GITHUB_OUTPUT"
