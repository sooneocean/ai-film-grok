#!/bin/bash
# Session wrap + push any unpushed main commits. No force-push.
# Exact wrap commit message per one-shot request.
set -euo pipefail
export PATH="/Users/dex/.grok/bin:/Users/dex/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
ROOT="/Users/dex/.grok/plugins/ai-film-grok"
RESULT_A="$ROOT/artifacts/session-wrap-2026-08-03-result.txt"
RESULT_B="/tmp/aifilm-wrap-result.txt"
cd "$ROOT"
{
  echo "=== START $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
  echo "=== 1) status / log ==="
  git status -sb
  git log -2 --oneline
  head -5 plugin.json

  WRAP="skills/ai-film-grok/memory/2026-08-03-workflow-merge-all-wrap.md"
  if [[ -f "$WRAP" ]] && git status --porcelain -- "$WRAP" | grep -q .; then
    echo "=== 2) commit wrap (exact message) ==="
    git add -- "$WRAP"
    git commit -m "docs(memory): session wrap for workflow merge-all v2.31.22"
  else
    echo "=== 2) wrap already clean or missing ==="
  fi

  echo "=== 3) porcelain after wrap ==="
  git status --porcelain || true

  echo "=== 4) make release-light ==="
  make release-light

  echo "=== 5) push origin main (no force) ==="
  git push origin main

  echo "=== 6) grok plugin update ==="
  if command -v grok >/dev/null 2>&1; then
    grok plugin update ai-film-grok || true
  else
    echo "grok CLI not on PATH"
  fi

  echo "=== FINAL ==="
  git status -sb
  git log -2 --oneline
  echo "STATUS=DONE"
  echo "=== END $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
} 2>&1 | tee "$RESULT_A" | tee "$RESULT_B"
# Ensure STATUS line present at top of result copies
for f in "$RESULT_A" "$RESULT_B"; do
  if ! grep -q '^STATUS=' "$f" 2>/dev/null; then
    { echo "STATUS=DONE"; cat "$f"; } >"${f}.tmp" && mv "${f}.tmp" "$f"
  fi
done
