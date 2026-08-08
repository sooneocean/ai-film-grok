# Review checklist · ai-film-grok

Use before every non-trivial commit or PR. Goal: quality is a **habit + machine gate**, not tribal knowledge.

## Must pass

- [ ] **`aifilm doctor` / `make doctor`** green for the change class (or CI doctor core checks understood)
- [ ] **Related pytest green** — test the AREA you touched (see AGENTS AREA table)
- [ ] **Gates / final / compose / delivery changes** → `make test-hotpath` green (or CI `hotpath` job)
- [ ] **CLI or script fingerprint change** → `make check-all` + `make lock-runtime` committed
- [ ] **Feature change** → `plugin.json` semver bump + `CHANGELOG.md` entry
- [ ] **Commit message English**, clear subject
- [ ] **No secrets** in diff (`config.env`, keys, tokens, private media). CI secret scan must stay green
- [ ] **No new promote path** that ranks seeds by mean motion / volume alone — use `composition_anti_hijack`
- [ ] **No new ad-hoc JSON reader** — use `util.read_json` / `require_json` / `read_json_source`
- [ ] **No silent** heat / pilot / `i2v_provider` policy flip
- [ ] **`except Exception` discipline (CR BLOCKER · C5.4)** — bare `except:` is **banned** (`B001`); `except Exception` must `log` (`util.logger.log`) + re-raise, or return explicit partial/`{ok:false}`. Silent swallow (`pass` / `return {}` / unlogged fallback) is **NEVER** allowed. Enforced by `ruff` `BLE001` (broad-except) in `make check-all` as a **new-code gate** (existing sites carry `# noqa: BLE001` after adoption).
- [ ] **New `*Error` classes** inherit `util.errors.FilmError` (C5.2); when touching old RuntimeError-based errors, prefer FilmError base

## Complexity budget (new code)

- Prefer new functions **≤ ~80 lines** when splitting is free
- Touching a module **> 2000 LOC**: note in PR whether you peeled a pure helper + test, or why not (bug-driven only)
- Do **not** open a “split everything under 1500 LOC” sprint

## Docs / plans

- [ ] If you closed a plan item, update that plan’s status header (no stale “OPEN” for shipped work)
- [ ] Memory cards stay short (quote + 3 lines + checklist); long lessons stay under `references/lessons-*`

## After merge (maintainers)

- [ ] `git push` (pre-push light + CI full)
- [ ] `grok plugin update ai-film-grok` on machines that run production
- [ ] Non-trivial change: optional `verifier` subagent or second clean read-back

## Links

- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [AGENTS.md](../AGENTS.md)
- [IRON coverage table](./reports/2026-08-06-iron-gate-coverage.md)
