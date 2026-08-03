# 2026-08-03 · 电影对白主链（中文口白 + 正反打 + HF 字幕）

## 原话
把分镜改成「电影对白主链」：有对白就角色口型说话，没对白就纯画面；去掉第三人称旁白。散文自动抽互动正反打；final 字幕统一 HyperFrames；语音改中文为主。

## 三句
1. 默认 `vo_mode=dialogue_drama` + `dialogue_spoken_lang=zh`（Edge 晓伊/云希）。
2. 散文拆句 → 交替 speaker + reverse/OTS 反应镜；无对白=纯画面，禁说书 `nar` 填钟。
3. 字幕 **仅 HyperFrames** 烧中文 `caption_text`（plate `subs=off`）。

## 清单
- [x] 中文主语音 + 正反打 + HF 字幕 + 对白主链默认
- [x] `test_dialogue_primary_chain.py` + check-all 绿（v2.33.0）

## 链
- hard-defaults · stages/voice · stages/post · dialogue-first · v2.33.0
