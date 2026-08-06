#!/bin/bash
# Session wrap + push any unpushed main commits. No force-push.
# Logs to /tmp during the run so we do not self-block release-light.
set -uo pipefail
export PATH="/Users/dex/.grok/bin:/Users/dex/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
ROOT="/Users/dex/.grok/plugins/ai-film-grok"
RESULT_A="$ROOT/artifacts/session-wrap-2026-08-03-result.txt"
RESULT_B="/tmp/aifilm-wrap-result.txt"
RUNLOG="/tmp/aifilm-wrap-run.log"
cd "$ROOT" || exit 1

STATUS="FAILED"
: >"$RUNLOG"

{
  echo "=== START $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
  echo "=== 1) status / log ==="
  git status -sb
  git log -2 --oneline
  head -5 plugin.json

  WRAP="skills/ai-film-grok/memory/2026-08-03-workflow-merge-all-wrap.md"
  WRAP_COMMITTED=0
  if [[ -f "$WRAP" ]] && git status --porcelain -- "$WRAP" | grep -q .; then
    echo "=== 2) commit wrap (exact message) ==="
    git add -- "$WRAP"
    if git commit -m "docs(memory): session wrap for workflow merge-all v2.31.22"; then
      WRAP_COMMITTED=1
    fi
  else
    echo "=== 2) wrap already clean or missing ==="
  fi

  # Clear wrap-tool dirt only
  git checkout -- "$RESULT_A" 2>/dev/null || true
  rm -f "$ROOT/artifacts/RUN-WRAP.command" 2>/dev/null || true

  echo "=== 3) porcelain after wrap / cleanup ==="
  git status --porcelain || true

  MAIN=$(git rev-parse main 2>/dev/null || echo missing)
  ORIGIN=$(git rev-parse origin/main 2>/dev/null || echo missing)
  echo "main=$MAIN"
  echo "origin/main=$ORIGIN"

  CLEAN_HEAD=0
  if git diff --quiet 2>/dev/null && git diff --cached --quiet 2>/dev/null; then
    CLEAN_HEAD=1
  fi

  # Stash unrelated WIP so light gate can run when we need to push
  STASHED=0
  if [[ "$WRAP_COMMITTED" -eq 1 ]] || [[ "$MAIN" != "$ORIGIN" ]]; then
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null \
      || [[ -n "$(git ls-files --others --exclude-standard 2>/dev/null | head -1)" ]]; then
      echo "=== 3b) stash WIP for push (keep index false) ==="
      if git stash push -u -m "session-wrap-auto-stash-$(date +%H%M%S)"; then
        STASHED=1
      fi
    fi
    echo "=== 4) make release-light (need push path) ==="
    if make release-light; then
      echo "release-light OK"
      echo "=== 5) push origin main (no force) ==="
      if git push origin main; then
        echo "push OK"
        MAIN=$(git rev-parse main)
        ORIGIN=$(git rev-parse origin/main)
        STATUS="DONE"
      else
        echo "push FAILED"
        STATUS="FAILED"
      fi
    else
      echo "release-light FAILED"
      STATUS="FAILED"
    fi
    if [[ "$STASHED" -eq 1 ]]; then
      echo "=== 5b) restore WIP stash ==="
      git stash pop || echo "stash pop had conflicts — check git stash list"
    fi
  else
    echo "=== 4) skip release-light (main already == origin; wrap clean) ==="
    STATUS="DONE"
  fi

  echo "=== 6) grok plugin update ==="
  if command -v grok >/dev/null 2>&1; then
    if grok plugin update ai-film-grok; then
      echo "plugin update OK"
    else
      echo "plugin update FAILED (non-fatal if already current)"
    fi
  else
    echo "grok CLI not on PATH"
  fi

  echo "=== FINAL ==="
  git status -sb
  git log -1 --oneline
  MAIN=$(git rev-parse main 2>/dev/null || echo missing)
  ORIGIN=$(git rev-parse origin/main 2>/dev/null || echo missing)
  echo "main=$MAIN"
  echo "origin/main=$ORIGIN"
  if [[ "$MAIN" == "$ORIGIN" ]]; then
    echo "main_eq_origin=yes"
    # If we couldn't push new wrap because of dirt but main already synced: PARTIAL only if wrap needed commit
    if [[ "$WRAP_COMMITTED" -eq 1 && "$STATUS" != "DONE" ]]; then
      STATUS="PARTIAL"
    elif [[ "$STATUS" == "FAILED" && "$MAIN" == "$ORIGIN" ]]; then
      STATUS="PARTIAL"
    fi
  else
    echo "main_eq_origin=no"
  fi
  echo "clean_head=$CLEAN_HEAD"
  echo "STATUS=$STATUS"
  echo "=== END $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
} >"$RUNLOG" 2>&1 || true

if grep -q '^STATUS=DONE' "$RUNLOG" 2>/dev/null; then
  STATUS="DONE"
elif grep -q '^STATUS=PARTIAL' "$RUNLOG" 2>/dev/null; then
  STATUS="PARTIAL"
else
  STATUS="FAILED"
fi

{
  echo "STATUS=$STATUS"
  echo "at=$(date '+%Y-%m-%dT%H:%M:%S%z')"
  echo "--- run log ---"
  cat "$RUNLOG" 2>/dev/null || true
} | tee "$RESULT_B" >"$RESULT_A"

# Keep RESULT_A from blocking the next gate only if we still need push; leave receipt as-is.
exit 0
