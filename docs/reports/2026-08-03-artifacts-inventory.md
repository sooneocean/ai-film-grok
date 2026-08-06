# Tracked artifacts inventory — 2026-08-03 (P4)

**Policy:** list first → then untrack media (P4b · 2026-08-03 继续推进).  
**Executed:** `git rm --cached` on **27** media files under `artifacts/`; local files kept on disk; root `.gitignore` now ignores canary media globs. JSON/workflow/receipts remain tracked.

## Summary

| Metric | Value |
|--------|-------|
| Tracked under `artifacts/` | **107** files · **~26 MB** |
| Media (mp4/png/jpg/wav/mp3) | **27** files |
| Largest single | hunyuan I2V pilot mp4 ~2.2 MB |

## Top media (by size)

| KB | Path |
|----|------|
| 2272 | `artifacts/armory-canaries/2026-07-30/hunyuan15-720p-i2v-sr-pilot/armory-hunyuan15_00001_.mp4` |
| 1924 | `artifacts/armory-canaries/2026-07-30/qwen-image-2512-quality/qwen2512_00001_.png` |
| 1656 | `artifacts/armory-canaries/2026-07-31/qwen-image-2512-no-text-0703/...png` |
| 1648 | `artifacts/armory-canaries/2026-07-30/qwen-image-2512-quality-retest/...png` |
| 1340 | `artifacts/lipdub-queue-20260731/front_closeup_dialogue_ja.mp4` |
| ~1 MB×n | `artifacts/frw-ab-canaries/...` flux/qwen environment A/B pngs |

## Recommendation (not executed)

1. **Keep tracked:** JSON receipts, workflow.json, README, human-review.json（契约样例）。
2. **Candidate untrack:** `*.mp4` / large `*.png` under armory + frw-ab + lipdub（可本地留档，git 只留 hash 指针在 receipt）。
3. **Disk only (already gitignored):** `.local-runtimes` ~4.5G、`g2pW` 双份 152M×2 — 清理前另列清单。
4. **Skill-side** `skills/ai-film-grok/artifacts/`：确认是否已 ignore；勿与 repo `artifacts/` 混谈。

## Command to untrack media later (user must approve)

```bash
# dry-run first
git ls-files 'artifacts/**/*.mp4' 'artifacts/**/*.png' 'artifacts/**/*.jpg' 'artifacts/**/*.wav' 'artifacts/**/*.mp3'
# then e.g.
# git rm --cached -- path1 path2 ...
```

`.gitignore` already has broad media globs under skill; **repo `artifacts/` media is currently tracked** — that is the intentional exception / debt.
