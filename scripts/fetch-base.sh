#!/usr/bin/env bash
#
# Fetches the pull request's base commit as refs/review-bot/base, so the repo
# notes and the agent-facing docs are read as they stand before the PR: a PR
# cannot rewrite the rules it is reviewed by. Without the ref, both are read
# from the checkout.
#
# Required in the environment: GH_TOKEN, PR_NUMBER.

set -euo pipefail

if ! base=$(gh pr view "$PR_NUMBER" --repo "$GITHUB_REPOSITORY" --json baseRefOid --jq .baseRefOid) ||
  ! git fetch --quiet --no-tags --depth=1 origin "$base" ||
  ! git update-ref refs/review-bot/base "$base"; then
  echo "::notice::could not fetch the PR's base, so its repo notes and docs are read from the checkout"
fi
