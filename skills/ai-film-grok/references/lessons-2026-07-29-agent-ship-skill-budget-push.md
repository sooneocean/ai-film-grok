# Lesson · 2026-07-29 · Agent 出货：SKILL 预算 / runtime-lock / 热度分层 / 对白·衣着（P0）

## 背景

同日多 wave 推 adult max + wardrobe ladder + dialogue_drama 时，**pre-push 反复红**：SKILL 超 6k、runtime-lock 漂移、工作区脏、文档锚点被裁掉。  
目标：把「会绿、会推、后面不重踩」写死。

## 铁律

| # | 坑 | 规则 |
|---|---|---|
| A1 | `SKILL.md` 膨胀 | **≤6000 字节**硬门。新 P0 进 SKILL 时**先压后加**；细节只链 `references/lessons-*` / `memory/*`。 |
| A2 | 裁短裁掉锚点 | 文档测要：`directors-lens.md`、`lessons-2026-07-20-directors-lens.md`、`先 Director’s Lens`、`grok_primary`、`seedance-2-fast-i2v`、`frw_video_model`、`frw-degrade-dispatch.md`、`caption_mode`、`transition_fluency`、`cut-silk-bilingual`、`title-double-burn` / `lessons-2026-07-20-title-double-burn.md`、`plate-cards blank`。 |
| A3 | 改 script 忘 lock | 任意 `scripts/*.py` 指纹变 → **重建** `runtime-lock.json` 再 doctor/push。 |
| A4 | 脏树 push | pre-push：**tracked 变更须先 commit**。并行 agent 写档时先 `status` 再 push；必要时 amend 进同一 tip 再推。 |
| A5 | 假完成 | 「commit 了」≠「push 绿」。完成= `origin/main` 含 tip + release-check 过。 |
| H1 | heat 分层 | **media-queue**：`hard_fail`（通常 &lt;A）硬拦。**final / review-final / export**：`final_ok`（≥S 默认 90 + 弧/时长）。`needs_boost`  alone 不挡 queue。 |
| H2 | 逃生诚实 | queue：`AIFILM_SKIP_HEAT_QUEUE_GATE`；final：`--skip-heat-gate` / `AIFILM_SKIP_HEAT_FINAL_GATE`。pilot skip **不**绕 heat。 |
| D1 | dialogue_drama | `vo_mode=dialogue_drama`：`dialogue_spoken_lang=ja`、`narration_spoken_lang=zh`；角色口 `spoken_text` 日文 + `caption_text` 中文；**禁止**用说书 `nar` 抢编辑时钟；源文保真查 caption/dialogue/audio_cues，不只查 `nar`。 |
| D2 | TTS 预演 | `tts-rehearsal` 读 **voice audio_cues.spoken_text**，禁止用字幕当 TTS 文。 |
| W1 | wardrobe ladder | 逐件卸装：列 garments → 串行 state I2I → `state-index approve-state` 本地登记；**不调出图 API**。未批 exact `wardrobe_state_id` → state-index **hard**。 |
| W2 | weapon canary | `submit` ≠ completed；须 `--complete` 绑 decode + 人审 hash 才 promote。 |

## 验过才算

```bash
wc -c skills/ai-film-grok/SKILL.md   # ≤6000
cd skills/ai-film-grok && PYTHONPATH=scripts python3 -c "
from pathlib import Path
from runtime_policy import build_runtime_lock, verify_runtime_lock
import json
r=Path('.').resolve(); p=r/'runtime-lock.json'
p.write_text(json.dumps(build_runtime_lock(r), indent=2)+'\n')
assert verify_runtime_lock(r, p)['ok']
"
git status -sb   # 干净
git push origin main
```

## 相关

- adult max Wave1–6：`memory/2026-07-29-adult-max-pipeline-force.md`
- closeout / evirus / anatomy / shot-variety：同日 `memory/2026-07-29-session-index.md`
- hard-defaults 表：`hard-defaults.md` 本课行
