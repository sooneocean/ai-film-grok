# Contributing · ai-film-grok

> 10-minute onboarding for humans and agents. Chinese OK in chat; **commit messages in English**.

## Source of truth

| What | Path |
|------|------|
| **Git / plugin root** | `/Users/dex/.grok/plugins/ai-film-grok` (this repo) |
| Skill symlink | `~/.grok/skills/ai-film-grok` → `…/plugins/ai-film-grok/skills/ai-film-grok` |
| Installed copy | `~/.grok/installed-plugins/ai-film-grok-*` — **do not edit**; refresh with `grok plugin update ai-film-grok` |
| Agent rules | [`AGENTS.md`](../AGENTS.md) |
| Hard product rules | [`skills/ai-film-grok/references/hard-defaults.md`](../skills/ai-film-grok/references/hard-defaults.md) |
| Review checklist | [`REVIEW_CHECKLIST.md`](./REVIEW_CHECKLIST.md) |
| Shim policy | [`SHIM_POLICY.md`](./SHIM_POLICY.md) |
| Memory / docs governance | [`MEMORY_GOVERNANCE.md`](./MEMORY_GOVERNANCE.md) |
| IRON → test map | [`reports/2026-08-06-iron-gate-coverage.md`](./reports/2026-08-06-iron-gate-coverage.md) |

## Authoritative CLI

- **Primary:** `skills/ai-film-grok/scripts/aifilm` (or `aifilm` after plugin enable)
- Helpers only: `backend-lock`, `media-queue`, `runtime-python`, `test` — not second entry points for product flow
- Every agent turn with a film root: prefer `aifilm dispatch --root <film>` first

## Config & secrets

- Copy keys from `skills/ai-film-grok/config.env.example` only
- **Never commit** `config.env`, API keys, OAuth tokens, or private film media
- Prefer `AIFILM_*` env vars documented in the example file

## Local loop (done = verified)

```bash
ROOT="$(git rev-parse --show-toplevel)"
make -C "$ROOT" check-all          # validate + ruff + doctor + pytest -m 'not slow'
make -C "$ROOT" test-hotpath       # fail-mode contracts (gates / final / compose)
# Feature change:
#   bump plugin.json (semver) + CHANGELOG.md
# Script fingerprint change:
#   make -C "$ROOT" lock-runtime
make -C "$ROOT" sync-docs          # version pointers in README/GRAPH
grok plugin update ai-film-grok    # refresh installed copy
```

## Gates: what actually runs

| Gate | When | Notes |
|------|------|--------|
| **CI** (`.github/workflows/ci.yml`) | push / PR to main | **Final source of truth**: validate, ruff, doctor core, pytest not-slow, **hotpath**, **secret scan** |
| Local pre-push (`.githooks/pre-push`) | if `core.hooksPath=.githooks` | secret scan via `gitea-publish` **if installed**; else **skips** secret scan (warn only) + light `release_gate` |
| `make release-light` | manual / pre-push default | docs + doctor core |
| `make release-check` / `AIFILM_RELEASE_GATE=full` | heavy release | full suite |

**Honest rule:** do not treat a green local push as “secrets scanned” unless `gitea-publish` is installed **or** CI has passed. CI secret scan is mandatory.

Enable hooks once per clone:

```bash
make -C "$ROOT" install-hooks
# or: git config core.hooksPath .githooks
```

## Code conventions (short)

1. **JSON I/O:** `util.read_json` (soft) / `util.require_json` (hard). No new private `_read_json*` for ordinary film JSON. Secure nofollow reads: `util.read_json_source` only for index/security paths.
2. **Volume / loudness probe:** `core.media_ops.probe_native_audio_mean_volume` — do not paste ffmpeg `volumedetect` again. Promote decisions must go through `composition_anti_hijack` (never mean/volume alone).
3. **Retry/backoff:** prefer `util.retry` when adding new loops.
4. **Public `aifilm` subcommand strings** stay stable; package moves keep hard-compat shims + tests — see [`SHIM_POLICY.md`](./SHIM_POLICY.md).
5. **No silent policy change** on heat / pilot GO / `i2v_provider`.
6. **No vanity “everything &lt;1500 LOC” peels** — peel only when a bug forces you into a monolith.

## PR / commit

- Message: English, imperative (“fix: …”, “docs: …”, “feat: …”)
- Use [`REVIEW_CHECKLIST.md`](./REVIEW_CHECKLIST.md) before push
- Outward PR/release copy: human review first (repo may be private)

## Where plans live

- Product / ship: `docs/plans/2026-08-06-optimization-todoplan.md`
- Engineering quality: `docs/plans/2026-08-06-codebase-quality-todoplan.md`
- Module layout: `docs/plans/2026-08-05-project-module-refactor.md`
