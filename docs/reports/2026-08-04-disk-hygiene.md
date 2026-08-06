# Disk hygiene inventory — 2026-08-04 (Wave Z4 → **EXECUTED C4**)

**Policy:** list first · delete only with user OK.  
**Repo:** `/Users/dex/.grok/plugins/ai-film-grok` · plugin **2.38.4**

## Executed (user OK · C4 2026-08-04)

| Action | Freed | Notes |
|--------|-------|-------|
| `rm -rf g2pW/` (repo root) | **152M** | Duplicate of skill-side; no code refs to root path |
| `rm -rf .local-runtimes/` | **~4.5G** | Offline TTS (cosy/kokoro/chatterbox/piper/melo); **edge remains default**; cosy/kokoro never auto-selected |
| Keep `skills/ai-film-grok/g2pW/` | — | Canonical copy (152M, gitignored) |

**Plugin tree after:** ~635M (was ~5.2G).

## Remaining (optional later)

| Path | Size | Note |
|------|------|------|
| `skills/ai-film-grok/g2pW/` | 152M | Ignored; drop only if polyphone unused forever |
| `skills/ai-film-grok/artifacts/` | ~local | 5090-evaluation media |
| worktrees under `/tmp` | varies | `git worktree prune` when idle |

## Reinstall (if local TTS needed again)

See `config.env.example` / opensource-tts notes for cosyvoice-local · kokoro-local · chatterbox · piper. Edge/MiMo/Fish do not need `.local-runtimes`.

---

Wave Z4 inventory listed first; C4 executed deletes after user nod.
