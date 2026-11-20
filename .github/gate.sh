#!/usr/bin/env bash
# Decides whether a timed (scheduled) run should do the work.
# GitHub's timer can fire late or skip a run, so the workflow wakes up at several
# backup times. The first wake-up inside the window does the update; later ones see
# that the report was already saved and skip.
#   Window (New York time): Sunday 18:00-19:59
set -u
out=${GITHUB_OUTPUT:-/dev/stdout}
if [ "${EVENT:-schedule}" != "schedule" ]; then echo "run=true" >> "$out"; exit 0; fi

h=$(TZ=America/New_York date +%-H); dow=$(TZ=America/New_York date +%u)
if [ "$dow" != 7 ] || { [ "$h" != 18 ] && [ "$h" != 19 ]; }; then
  echo "Skipping: outside Sunday 6-8pm New York."; echo "run=false" >> "$out"; exit 0
fi
since=$(date -u -d "TZ=\"America/New_York\" $(TZ=America/New_York date +%F) 18:00" +%Y-%m-%dT%H:%M:%SZ)
saved=$(gh api "repos/$GITHUB_REPOSITORY/commits?sha=main&since=$since&per_page=50" \
          -q '[.[] | select(.commit.message | startswith("Market rotation"))] | length' 2>/dev/null || echo 0)
if [ "${saved:-0}" -gt 0 ]; then
  echo "Skipping: this week's report was already saved."; echo "run=false" >> "$out"
else
  echo "Running this week's report."; echo "run=true" >> "$out"
fi
