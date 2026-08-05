# Session wrap · ship finish (2026-08-05)

## Shipped tip
- **SHA**: `23b85400e74a43877f47c66a59042fad1e1b5891`
- **Branch**: `main` = `origin/main` (push OK, light gate)
- **Version**: 2.39.66

## What shipped
1. **S5.3 capacity-wait**: `wait_for_comfy_capacity` / `recover_capacity_contention` + CLI `--capacity-wait-sec` (never cancel foreign; hard max 600s). Tests in `test_h3_until_empty.py`.
2. **Voice normalize leaves**: `final.voice.normalize_cast_voices` / `normalize_cast_tts_backends` wired from `render_final`; Chinese locks; ja→zh remap. Tests in `test_final_voice_normalize.py`.
3. Docs/CHANGELOG/runtime-lock pointers for 2.39.66.

## Key commits (on main)
- `752ad1ae` chore(final): re-export normalize_cast_* from final package
- `9a0c35bf` feat: S5.3 capacity-wait + cast voice normalize leaves (v2.39.66)
- `76d626f7` feat(h3): capacity-wait on until-empty and final voice normalize leaves
- (+ prior unpushed combo R2 / re-lock that were included in the push stack)

## Merge-all
- **Already in main**: all local codex/* / feat/* / refactor/* inspected tips except seedvr2.
- **FF-merged**: none needed (no branch was strictly ahead-of-main in a clean FF line).
- **Deferred**: `codex/seedvr2-armory` (ahead=4 behind=317, diverged; not force-merged).

## Deferred / not done
- Full overnight H3 `queue_empty` drain (still needs idle 5090).
- Non-ff merge of stale codex history branches.
- Force-delete of local feature branches.

## Evidence (scratch)
- `git-push.log`, `merge-all.log`, `ship-pytest.log`, `git-final-status.log`

## Final tip after wrap docs
- SHA: `23b85400e74a43877f47c66a59042fad1e1b5891`

## Remote tip after successful push
- **SHA**: `f08a1d37ff8aa4c280a97172ecee50a6f5ce41a8`
- **push_exit**: 0 (light gate; AIFILM_TTS_BACKEND=edge for doctor preferred TTS)
