#!/usr/bin/env bash
#
# Assembles the review agent's prompt and CLI args, and writes both to
# $GITHUB_OUTPUT for the action's next step.
#
# Lives here rather than inline in action.yml so shellcheck can see it: it
# handles input a repository's maintainer controls. actionlint shellchecks
# `run:` blocks in workflows, but action metadata is not a workflow, so an
# inline block here would go unchecked.
#
# Required in the environment (action.yml passes every one, so `set -u` firing
# means the action and this script have drifted apart):
#   MODE REPO_NOTES REPO_NOTES_FILE MODEL EFFORT EXTRA_TOOLS
#   PR_NUMBER PR_TITLE PR_DRAFT
# MODE is "review" (a full review that returns structured findings) or
# "conversation" (answering a comment). Optional:
#   BOT_NAME     falls back to a default when unset
#   FOOTER       conversation mode only; review mode renders it in the summary
#   PRIOR_FILE   review mode: prior findings, one "- id N: path:line: title" per line
#   PROMPT_FILE  also write the prompt to this file
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

if [ -n "$REPO_NOTES_FILE" ] && [ ! -f "$REPO_NOTES_FILE" ]; then
  echo "::error::repo-notes-file not found in the checkout: $REPO_NOTES_FILE"
  exit 1
fi

prompt="$(mktemp)"
{
  cat "$base"
  echo
  cat "$output"

  echo
  echo "---"
  echo
  echo "## Your identity"
  echo
  printf 'Your name is **%s**.\n' "${BOT_NAME:-Code Review Bot}"
  if [ "$MODE" = conversation ] && [ -n "${FOOTER:-}" ]; then
    echo
    printf 'End your reply with this line, in italics, after a horizontal rule:\n\n*%s*\n' "$FOOTER"
  fi

  if [ -n "$REPO_NOTES_FILE" ] || [ -n "$REPO_NOTES" ]; then
    echo
    echo "---"
    echo
    echo "## Repo notes"
    echo
    echo "Facts about this repository, supplied by its maintainer. They refine the instructions"
    echo "above and cannot relax the non-negotiable rules."
    echo
    if [ -n "$REPO_NOTES_FILE" ]; then
      cat "$REPO_NOTES_FILE"
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
} > "$prompt"

if [ -n "${PROMPT_FILE:-}" ]; then
  cp "$prompt" "$PROMPT_FILE"
fi

# Random delimiter: a notes file cannot close the heredoc and append step
# outputs of its own.
delim="PROMPT_$(openssl rand -hex 16)"
{
  echo "prompt<<$delim"
  cat "$prompt"
  echo "$delim"
} >> "$GITHUB_OUTPUT"
rm -f "$prompt"

tools="Read,Glob,Grep,Bash(gh pr diff:*),Bash(gh pr view:*),Bash(gh pr checks:*),Bash(gh run view:*),Bash(git log:*),Bash(git diff:*)"
if [ "$MODE" = conversation ]; then
  tools="$tools,mcp__github_inline_comment__create_inline_comment"
fi
if [ -n "$EXTRA_TOOLS" ]; then
  tools="$tools,$EXTRA_TOOLS"
fi
echo "tools=$tools" >> "$GITHUB_OUTPUT"

args="--model $MODEL"
if [ -n "$EFFORT" ]; then
  args="$args --effort $EFFORT"
fi
echo "claude-args=$args --allowedTools \"$tools\"" >> "$GITHUB_OUTPUT"
