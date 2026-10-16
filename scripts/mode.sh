#!/usr/bin/env bash
#
# Decides whether this run is a full review or a reply to a comment, and
# writes mode=review or mode=conversation to $GITHUB_OUTPUT.
#
# A pull_request event, or a PR comment containing "<trigger> review", is a
# review. Any other comment is a conversation. The comment body is untrusted,
# so it arrives in the environment and is only ever matched, never evaluated.
#
# Required in the environment: EVENT, TRIGGER, COMMENT_BODY.

set -euo pipefail

mode=conversation
if [ "$EVENT" = pull_request ] || [ "$EVENT" = pull_request_target ]; then
  mode=review
elif [ "$EVENT" = issue_comment ] && [[ "$COMMENT_BODY" == *"$TRIGGER review"* ]]; then
  mode=review
fi
echo "mode=$mode" >> "$GITHUB_OUTPUT"
echo "review-bot mode: $mode"
