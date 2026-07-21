# Changelog

All notable changes to **ai-film-grok** are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/) · versioning: [SemVer](https://semver.org/) (mirrors `plugin.json`).

## [1.0.0] — 2026-07-21

### Added

- Independent git root at `~/.grok/plugins/ai-film-grok` with GitHub remote.
- `AGENTS.md` absolute-path entry for coding agents.
- GitHub Actions CI: `plugin validate` + pytest.
- Grok plugin packaging: `plugin.json`, slash commands `/ai-film-grok` `/aifilm`.
- Full skill body under `skills/ai-film-grok` (dispatch eight-ring, Imagine I2V, edge TTS, HyperFrames/FFmpeg).

### Notes

### CI

- GitHub Actions: `validate-core` + `test-full` both required (full suite green on main).
- Pinned deps via `skills/ai-film-grok/requirements.lock`.

- Local secrets stay in `skills/ai-film-grok/config.env` (gitignored).
- User skill path is a symlink into this plugin skill directory.
