# memory/ · 短记忆卡契约

> **用途**：人读 / agent 速查。**不是** 第二份 hard-defaults，也**不是** 完整 lesson。  
> **治理**：[docs/MEMORY_GOVERNANCE.md](../../../docs/MEMORY_GOVERNANCE.md)  
> **归档**：`archive/`（F5 2026-08-07 · active ≤40）

## 四层文档

| 层 | 路径 | 写什么 |
|----|------|--------|
| 0 制度指针 | `~/.grok/Agents.md` · plugin `AGENTS.md` | 一行指针，禁贴整段 IRON |
| 1 机读门禁 | `references/hard-defaults.md` + gates 代码 | 可执行规则唯一正文 |
| 2 阶段卡 | `references/stages/*.md` | dispatch 默认加载，≤30 行 |
| 3 **本目录** | `memory/*.md` | 原话 · 三句 · checklist · 链 |
| 4 长课 | `references/lessons-*` | 片例矩阵与复盘，按需打开 |

## Active P0（≤40 · 2026-08-07 F5 刷新）

| 主题 | 卡 |
|------|-----|
| **多 agent 5090 禁 hog** | [multi-agent-gpu-no-hog](2026-08-06-multi-agent-gpu-no-hog.md) |
| 双片排水 / takes 进度 | [dual-film-drain](2026-08-06-dual-film-drain-takes-progress.md) |
| 卸装不回穿 + 尺度兜底 | [wardrobe-no-redress](2026-08-06-wardrobe-no-redress-fullnude-fallback.md) |
| 正牌 final IRON | [suse-ep01-final](2026-08-06-suse-ep01-official-final-iron.md) |
| H3 原声季审片 | [h3-native-ship](2026-08-06-h3-native-ship-review-lessons.md) |
| plate 有片仍无聊 / mix | [plate-boring-mean-mix](2026-08-06-plate-boring-mean-mix-iron.md) |
| C1 capacity-wait | [c1-capacity](2026-08-06-c1-capacity-wait-iron.md) |
| Comfy 隧道 auto | [tunnel-ensure](2026-08-06-comfy-tunnel-auto-ensure.md) |
| 构图防抢走 | [anti-hijack](2026-08-05-composition-anti-hijack.md) |
| 毒镜 / 抗无聊 / closeout | 07-29 poison · variety · closeout |
| 成人 MAX / 高动 / 性爱底 | 07-27 · sex-hard-floors |
| fill-idle / h3 日课 | 08-04 fill-idle · 08-06 h3-core |
| 圣旨协议 | [user-command-is-edict](2026-08-04-user-command-is-edict.md) |
| 出片诚实审计轨 | [delivery-honesty-rail](2026-08-07-delivery-honesty-rail.md) |
| **身份代际锁 E1** | [identity-generation-lock](2026-08-07-identity-generation-lock-no-mix.md) |
| **配角定妆锁 E2** | [partner-cast-master](2026-08-07-partner-cast-master-iron.md) |
| **原声轻处理 E3** | [h3-native-speech-isolate](2026-08-07-h3-native-speech-isolate.md) |
| **禁半帧复合 E4** | [no-midframe-composite](2026-08-07-no-midframe-composite-flf-audio-iron.md) |
| **I2V 首帧满幅** | [i2v-firstframe-fill](2026-08-07-i2v-firstframe-fill-no-tiny-fullbody.md) |
| **退役武器清心智** | [retired-weapon-clear-mind](2026-08-07-retired-weapon-clear-mind.md) |
| **剪辑总监 desk** | [edit-director-desk](2026-08-07-edit-director-desk.md) |
| 字幕硬烧 / 对白链 | huangdao-caption · dialogue-primary · native-xor-tts |
| 养分 / 治理 | [nutrient-matrix](../../../docs/plans/2026-08-06-nutrient-matrix.md) · [MEMORY_GOVERNANCE](../../../docs/MEMORY_GOVERNANCE.md) |
| **错误内化板** | [error-internalization](../../../docs/plans/2026-08-07-error-internalization-todoplan.md) |

完整文件名见目录列表；旧卡 / canary / session-wrap / 已 L4 长卡在 `archive/`。

## 模板（新卡必循）

```markdown
# Memory · YYYY-MM-DD · 标题

**完整课**：[lessons-YYYY-MM-DD-slug.md](../references/lessons-YYYY-MM-DD-slug.md)

## 用户原话
> …

## 三句话
1. …
2. …
3. …

## 检查清单
- [ ] …

## 片例（可选）
`path/to/film-root`
```

## 禁止

- 与 `references/lessons-*` **双写完整铁律表**
- 超过约 **60 行**
- 把 memory 当 context-routing 的 **required** 长文
- 已 ship 的 canary/session-wrap 长期堆在 active（应 `git mv` → archive）
- active 超过 **40** 张（F5）

## 对账

有 `lessons-DATE-slug.md` 时，memory 文件名优先 `DATE-slug.md`。  
规则变更：先改 **hard-defaults**（或代码），再改 lesson，最后只改 memory 三句话/清单。
