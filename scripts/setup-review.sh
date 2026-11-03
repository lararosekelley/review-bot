#!/usr/bin/env bash
#
# Installs the pinned CLI that reviews and replies run (Claude Code, or
# opencode from its GitHub release), and creates the run's working directory.
#
# Required in the environment: HARNESS, CLAUDE_CODE_VERSION, OPENCODE_VERSION,
# WORK_DIR. Plus the runner's own RUNNER_ARCH, RUNNER_TEMP, and GITHUB_PATH.

set -euo pipefail

mkdir -p "$WORK_DIR"
case "$HARNESS" in
  claude-code)
    npm install --global --no-fund --no-audit --loglevel=error "@anthropic-ai/claude-code@$CLAUDE_CODE_VERSION"
    claude --version
    ;;
  opencode)
    case "$RUNNER_ARCH" in
      X64) asset=opencode-linux-x64.tar.gz ;;
      ARM64) asset=opencode-linux-arm64.tar.gz ;;
      *) echo "::error::opencode has no build for runner arch $RUNNER_ARCH"; exit 1 ;;
    esac
    base="https://github.com/anomalyco/opencode/releases/download/v$OPENCODE_VERSION"
    dir="$RUNNER_TEMP/opencode"
    mkdir -p "$dir/bin"
    curl -fsSL --retry 3 -o "$dir/$asset" "$base/$asset"
    curl -fsSL --retry 3 -o "$dir/SHA256SUMS" "$base/SHA256SUMS"
    (cd "$dir" && grep " $asset\$" SHA256SUMS | sha256sum -c -)
    tar -xzf "$dir/$asset" -C "$dir/bin" opencode
    echo "$dir/bin" >> "$GITHUB_PATH"
    "$dir/bin/opencode" --version
    ;;
  *) echo "::error::harness must be claude-code or opencode, got: $HARNESS"; exit 1 ;;
esac
