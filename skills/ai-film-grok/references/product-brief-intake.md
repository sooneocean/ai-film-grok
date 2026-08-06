# Product Brief Intake · 产品片 brief 扩展流程

> v1.23 · 把 ai-film-grok 从纯叙事扩展到产品介绍片（30-60s launch film / demo / 产品讲解）
> 灵感来源：reference-driven-cinematic-video 的 Product Brief Expansion 工序

## 何时用

用户给的 brief 不是故事/剧本，而是：

- 产品介绍 / 飞书文档 / 官网链接 / 功能清单
- 想做 30-60 秒产品介绍片（中文/英文）
- 想做科技感产品发布片（曲面屏 / UI macro / 代码流）
- 想复刻参考片的镜头语法套到自己的产品上

## 流程

### 0 · 产品 brief 扩展

```bash
"$AIFILM" brief expand --text "<产品介绍文本>" --title "<产品名>" --target-duration 40
# → receipts/product-brief.json
```

**自动产出**（纯文本分析，无 LLM 调用）：

| 字段 | 说明 |
|------|------|
| `product_name` | 产品名（首行启发式） |
| `promise` | 核心一句话承诺 |
| `audience.familiarity` | 受众对品类的熟悉度 |
| `audience.pain_markers` | 痛点关键词 |
| `proof_markers` | 证据类型（stats/screenshot/demo/repo/website） |
| `missing_assets` | 缺失素材清单（agent 需搜索或索要） |
| `brochure_phrase_warnings` | 广告腔/ AI 味短语检测 |
| `scene_plan` | 5 拍产品片场景计划（hook/pain/reveal/proof/close） |
| `narrative_angle` | 建议叙事角度（demo_first / problem_solution / before_after / category_education） |
| `research_needed` | 是否需要 web 搜索补全 |

### 1 · 研究补全（Research Sidecar）

当 `research_needed=true` 时，agent 用 `web_search` 补全：

- 官方产品页 / 文档 / GitHub repo
- 公开 demo / 截图 / app store listing
- 竞品和品类语言
- 论坛/评论中的用户痛点原话

产出 `claim-ledger`：每个 claim 标注来源，区分 safe-to-use 和 not-safe-to-use。

### 2 · 参考视频审计（可选）

用户给参考视频时：

```bash
"$AIFILM" analyze-reference "<reference.mp4>" --root "<root>"
# → reference-analysis/shot-grammar.json + contact-sheet.jpg + keyframes/
```

agent 读 `shot-grammar.json`，把 `suggested_dsl_overrides` 映射到 film-spec shots。

### 3 · 写 film-spec（genre=product）

把 product-brief 的 scene_plan 转成 film-spec scenes/shots：

```json
{
  "genre": "product",
  "scenes": [...],
  "vo_mode": "storyteller",
  "target_duration_sec": 40
}
```

### 4 · 质检 + 交付

```bash
"$AIFILM" final --root "<root>" --post-engine hyperframes
"$AIFILM" quality-check "<root>/out/film_final.mp4" --root "<root>" --min-score 80
"$AIFILM" review-final --root "<root>" --approve ...
```

## 5 拍产品片节拍

| 拍 | 比例 | 目的 | 运镜提示 |
|----|------|------|---------|
| 1 hook | 12% | 第一秒抓住注意力 | flash/sweep |
| 2 pain | 18% | 让观众感受到痛点 | hard_cut |
| 3 reveal | 20% | 产品亮相 | mesh_bend/zoom |
| 4 proof | 35% | 证据/工作流/数据 | parallax/card_rail |
| 5 close | 15% | 收束 + 记忆点 | match_cut/fade |

## 视觉载体选择

**一个强视觉概念贯穿全片**，不要堆叠多个幻灯片场景：

- 曲面屏 / Cyclorama → 科技感产品（加载 `cyclorama-curved-screen`）
- UI macro → 软件产品
- 代码流 → 开发者工具
- 产品 render → 硬件产品
- 动效字体 → 品牌片

## 相关

- [research-to-storyboard](../scripts/product_brief.py) — brief 扩展模块
- [quality-check](quality-check-video.md) — 成片客观质检
- [analyze-reference](reference-audit.md) — 参考视频反推
- [hard-defaults.md](hard-defaults.md) — 交付门禁
