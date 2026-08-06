# memory/ · 短记忆卡契约

> **用途**：人读 / agent 速查。**不是** 第二份 hard-defaults，也**不是** 完整 lesson。

## 四层文档（复习）

| 层 | 路径 | 写什么 |
|----|------|--------|
| 0 制度指针 | `~/.grok/Agents.md` · plugin `AGENTS.md` | 一行指针，禁贴整段 IRON |
| 1 机读门禁 | `references/hard-defaults.md` + gates 代码 | 可执行规则唯一正文 |
| 2 阶段卡 | `references/stages/*.md` | dispatch 默认加载，≤30 行 |
| 3 **本目录** | `memory/*.md` | 原话 · 三句 · checklist · 链 |
| 4 长课 | `references/lessons-*` | 片例矩阵与复盘，按需打开 |

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
- [ ] …

## 片例（可选）
`path/to/film-root`
```

## 禁止

- 与 `references/lessons-*` **双写完整铁律表**
- 超过约 **60 行**（片例对照表可例外，但仍须链 lesson）
- 把 memory 当 context-routing 的 **required** 长文

## 对账

有 `lessons-DATE-slug.md` 时，memory 文件名优先 `DATE-slug.md`（无 `lessons-` 前缀）。  
规则变更：先改 **hard-defaults**（或代码），再改 lesson，最后只改 memory 的三句话/清单措辞。
