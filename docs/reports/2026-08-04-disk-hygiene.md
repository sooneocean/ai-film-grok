# Disk hygiene inventory — 2026-08-04 (Wave Z4)

**Policy:** list first · **no delete** without explicit user OK.  
**Repo:** `/Users/dex/.grok/plugins/ai-film-grok` · plugin `2.37.9+`

## Summary

| Path | Size | Git | Recommendation |
|------|------|-----|----------------|
| `.local-runtimes/` | **4.5G** | ignored | Keep if TTS local backends still used; else document reinstall then prune per-runtime |
| `g2pW/` (repo root) | **152M** | check track status | **Single truth:** keep skill copy OR root; other → symlink |
| `skills/ai-film-grok/g2pW/` | **152M** | likely used by TTS | Prefer this as canonical for skill runtime |
| `skills/ai-film-grok/artifacts/` | **116M** | mostly ignore | 5090-evaluation media stays local; do not re-track |
| `artifacts/` (repo) | **43M** | receipts/json OK | Media untracked after P4b; leave receipts |
| `skills/ai-film-grok/receipts/` | **5M** | mixed | Keep canary JSON; no bulk media |
| `skills/ai-film-grok/config.env.bak-*` | ~3×3KB | should ignore | Move to `~/.grok/backups/` or delete after confirm |
| `nul` (repo root) | 0B | noise | Safe delete (Windows null artifact) |

## `.local-runtimes` children (top)

- `piper-mac` · `kokoro-zh` · `cosyvoice-mac` · `chatterbox-mac` · `melo-mac`  
  Each is a full venv-style tree; reinstall path lives in skill docs / config.env.example (opensource-tts).

## g2pW dual copy

Both trees contain: `g2pw.onnx`, `config.py`, mono/poly char lists, `version`.  
**Proposed (not executed):** keep `skills/ai-film-grok/g2pW` as runtime path; replace root `g2pW` with symlink after grepping import paths.

## Worktrees (local)

Several detached / **prunable** worktrees under `/private/tmp` and Codex paths.  
**Proposed (not executed):** `git worktree prune` after confirming no open jobs.

## Not recommended without reinstall plan

- Blind `rm -rf .local-runtimes` (rebuild cost high if edge falls back to local TTS).
- Deleting skill `artifacts/5090-evaluation` mid-series evaluation.

## Next actions (need user OK)

1. [ ] Confirm g2pW single-truth + symlink  
2. [ ] Confirm prune prunable worktrees  
3. [ ] Confirm delete `nul` + move `config.env.bak-*`  
4. [ ] Optional: drop unused local TTS runtimes one-by-one  

---

Generated as Wave Z4 of project-level refactor plan (2026-08-04). No files removed.
