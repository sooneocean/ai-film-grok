# memory/ · 短记忆卡契约

> **用途**：人读 / agent 速查。**不是** 第二份 hard-defaults，也**不是** 完整 lesson。  
> **治理**：[docs/MEMORY_GOVERNANCE.md](../../../docs/MEMORY_GOVERNANCE.md)  
> **归档**：`archive/`（2026-08-06 激进瘦身 · 历史卡可回查）

## 四层文档

| 层 | 路径 | 写什么 |
|----|------|--------|
| 0 制度指针 | `~/.grok/Agents.md` · plugin `AGENTS.md` | 一行指针，禁贴整段 IRON |
| 1 机读门禁 | `references/hard-defaults.md` + gates 代码 | 可执行规则唯一正文 |
| 2 阶段卡 | `references/stages/*.md` | dispatch 默认加载，≤30 行 |
| 3 **本目录** | `memory/*.md` | 原话 · 三句 · checklist · 链 |
| 4 长课 | `references/lessons-*` | 片例矩阵与复盘，按需打开 |

## Active P0（≤40 · 2026-08-06 刷新）

| 主题 | 卡 |
|------|-----|
| **多 agent 5090 禁 hog（机读）** | [multi-agent-gpu-no-hog](2026-08-06-multi-agent-gpu-no-hog.md) |
| 双片排水 / takes 进度 | [dual-film-drain](2026-08-06-dual-film-drain-takes-progress.md) |
| 卸装不回穿 + 尺度兜底 | [wardrobe-no-redress](2026-08-06-wardrobe-no-redress-fullnude-fallback.md) |
| 正牌 final IRON | [suse-ep01-final](2026-08-06-suse-ep01-official-final-iron.md) |
| H3 原声季审片 | [h3-native-ship](2026-08-06-h3-native-ship-review-lessons.md) |
| 构图防抢走 | [anti-hijack](2026-08-05-composition-anti-hijack.md) |
| 毒镜 / 抗无聊 / closeout | 07-29 对应卡 |
| 成人 MAX / 高动 / 性爱时长底 | 07-27 · sex-hard-floors |
| gate-auto / fill-idle / h3_primary | 08-04 · 08-05 |
| 圣旨协议 | [user-command-is-edict](2026-08-04-user-command-is-edict.md) |
| **本周索引** | [session-index](2026-08-06-session-index.md) |

完整文件名见目录列表；旧卡在 `archive/`。

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

## 对账

有 `lessons-DATE-slug.md` 时，memory 文件名优先 `DATE-slug.md`。  
规则变更：先改 **hard-defaults**（或代码），再改 lesson，最后只改 memory 三句话/清单。
