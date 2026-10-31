#!/usr/bin/env bash
# Run the deterministic composition test from the LearnHarness checkout so that
# tsx and node_modules resolve, while pointing the app at the real data dir.
set -euo pipefail

REPO="${LEARNHARNESS_REPO:-$HOME/Work/LearnHarness}"
DATA="${LH_DATA_DIR:-$REPO/data}"
TEST_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/prompt-composition.test.ts"

if [[ ! -d "$REPO/node_modules" ]]; then
  echo "missing $REPO/node_modules — run bun/npm install in the LearnHarness checkout first" >&2
  exit 2
fi
if [[ ! -f "$TEST_FILE" ]]; then
  echo "missing test file: $TEST_FILE" >&2
  exit 2
fi
if [[ ! -f "$DATA/settings.json" ]]; then
  echo "missing settings: $DATA/settings.json — run scripts/apply.py first" >&2
  exit 2
fi

cd "$REPO"
LH_DATA_DIR="$DATA" LEARNHARNESS_REPO="$REPO" npx tsx --test "$TEST_FILE"
