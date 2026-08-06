#!/bin/bash
# Force Comfy 18188→8188 (Tailscale 5090). Called by LaunchAgent + agents.
set -euo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.pyenv/shims:/usr/bin:/bin"
export AIFILM_COMFY_TUNNEL_AUTO=1
SKILL="${AIFILM_SKILL_DIR:-$HOME/.grok/plugins/ai-film-grok/skills/ai-film-grok}"
AIFILM="$SKILL/scripts/aifilm"
LOGDIR="${AIFILM_TUNNEL_LOG_DIR:-$HOME/.grok/plugins/ai-film-grok/artifacts}"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/comfy-tunnel-ensure.log"
{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ensure ==="
  if [ -x "$AIFILM" ]; then
    "$AIFILM" tunnel-ensure 2>&1 || true
  else
    echo "missing aifilm: $AIFILM"
  fi
} >>"$LOG" 2>&1
# keep log small
tail -n 200 "$LOG" >"$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG" || true
