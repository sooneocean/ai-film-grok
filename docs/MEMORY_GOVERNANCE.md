# Memory / docs governance · ai-film-grok

Prevent context bloat and dual-truth docs. Authority order is fixed.

## Authority stack (read top-down)

1. **`references/hard-defaults.md`** — hard product rules (edit + tests).
2. **`references/stages/*`** — per-stage agent cards (dispatch context).
3. **`memory/*`** — short session cards only (quote + 3 lines + checklist + lesson link).
4. **`references/lessons-*`** — long postmortems; **do not** paste whole files into agent context.
5. **`docs/plans/*`** — execution boards; status headers must stay 账实一致.

## memory/ retention

| Rule | Detail |
|------|--------|
| Shape | Dated `YYYY-MM-DD-topic.md`; max ~80 lines preferred |
| Content | User quote + 3 bullets + checklist + optional lesson pointer |
| No secrets | Never paste tokens, `url.user:pass@host`, or `config.env` |
| Soft cap | Prefer **≤ 100** active cards; when over, archive oldest to `memory/archive/` (keep index links) |
| Age | Cards **> 60 days** with no hard-defaults pointer → archive candidate |
| Index | `memory/README.md` lists active P0 cards only |

## What agents must not do

- Paste entire `lessons-*` into every turn.
- Rewrite hard-defaults by only editing memory (memory is index, not law).
- Claim OPEN items already SHIPPED in plan headers.

## Related

- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [REVIEW_CHECKLIST.md](./REVIEW_CHECKLIST.md)
- skill `memory/README.md`
