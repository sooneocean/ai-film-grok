#!/bin/bash
# Session wrap + push any unpushed main commits. No force-push.
set -euo pipefail
export PATH="/Users/dex/.grok/bin:/Users/dex/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
ROOT="/Users/dex/.grok/plugins/ai-film-grok"
RESULT="$ROOT/artifacts/session-wrap-2026-08-03-result.txt"
cd "$ROOT"
{
  echo "=== START $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
  echo "=== 1) status / log / stash / version ==="
  git status -sb
  git log -5 --oneline
  git stash list || true
  head -5 plugin.json

  WRAP="skills/ai-film-grok/memory/2026-08-03-workflow-merge-all-wrap.md"
  if [[ -f "$WRAP" ]] && git status --porcelain -- "$WRAP" | grep -q .; then
    echo "=== 2) commit wrap ==="
    git add -- "$WRAP"
    git commit -m "docs(memory): session wrap for workflow Wave A–F (v2.31.20–23)" || true
  else
    echo "=== 2) wrap already clean or missing ==="
  fi

  # Commit other clean docs-only dirt if only wrap-like paths (avoid half-WIP)
  echo "=== 3) porcelain after wrap ==="
  git status --porcelain || true

  if git status --porcelain -- skills/ai-film-grok/runtime-lock.json | grep -q .; then
    echo "=== lock-runtime ==="
    make lock-runtime
    git add skills/ai-film-grok/runtime-lock.json
    git commit -m "chore(runtime): refresh lock after wrap" || true
  fi

  echo "=== release-light ==="
  make release-light

  echo "=== push (no force) ==="
  git push origin main

  echo "=== plugin update ==="
  if command -v grok >/dev/null 2>&1; then
    grok plugin update ai-film-grok || true
  else
    echo "grok CLI not on PATH"
  fi

  echo "=== FINAL ==="
  git status -sb
  git log -3 --oneline
  git stash list || true
  echo "DONE"
  echo "=== END $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
} >"$RESULT" 2>&1
