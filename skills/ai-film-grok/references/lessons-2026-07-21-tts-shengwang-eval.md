# Lessons · 2026-07-21 · 声网开源 TTS 横评 × 技能选型

**层**：voice / skill-docs · **P 码**：P0 可复现默认 + 显式质量档；P4 一角一声不静默换商

## 结论

声网 [2026-05 开源 TTS 评测](https://www.shengwang.cn/blog/blogdetail/2026-TTS-evaluation/) 六模型里，对本技能：

| 档 | 模型 | 动作 |
|---|---|---|
| P0 | CosyVoice 2 | HTTP 适配器 `adapters/cosyvoice_tts.py`；`external` |
| P1 | Higgs Audio V2 | 情感候选；有实片再装 adapter |
| P2 | Kokoro-82M | 仅离线后备；中文不宜默认 |
| 不优先 | VibeVoice | 长音频优势与分镜短 nar 错位 |
| 红线 | Fish Speech **自托管** | CC BY-NC-SA；商用走 Fish **API** |

**默认 `edge` 不动。**

## 工程沉淀

- 文档：`voices.md` 场景路由 · `opensource-tts.md` 横评对照表  
- 适配器：`cosyvoice_tts.py`（doctor + JSON HTTP → WAV）；旧 example 转发到生产适配器  
- 验收：本机 `tts-ab edge,external`；固定 `COSYVOICE_REF_WAV` hash；measured VO

## 勿做

- 无用户批准改默认 backend  
- Neural 名塞进 CosyVoice/external voice  
- 半片 edge 半片克隆  
- 把博客 MOS 当本机验收（须实听）
