#!/usr/bin/env bash
#
# Installs the pinned Claude Code CLI that the review passes run, and creates
# the run's working directory.
#
# Required in the environment: CLAUDE_CODE_VERSION, WORK_DIR.

set -euo pipefail

mkdir -p "$WORK_DIR"
npm install --global --no-fund --no-audit --loglevel=error "@anthropic-ai/claude-code@$CLAUDE_CODE_VERSION"
claude --version
