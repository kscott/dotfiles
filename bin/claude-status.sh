#!/bin/bash
dir=$(basename "${CLAUDE_PROJECT_DIR:-$PWD}")
branch=$(git -C "${CLAUDE_PROJECT_DIR:-$PWD}" branch --show-current 2>/dev/null)
if [[ -n "$branch" ]]; then
  echo "$dir  $branch"
else
  echo "$dir"
fi
