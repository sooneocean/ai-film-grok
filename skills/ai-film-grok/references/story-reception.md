# Story Reception · 小说 T2T 接收器

> 小说、剧本或故事文本进入 ai-film-grok 时的**第一步**。本接收器由 Agent 在对话内
> 完成，不调用文字 API；CLI 只验证并保存它的 JSON 输出。

## 目标

把用户原文转换成可拍的导演处理包，让后续 `story.normalize → drama-graph → film-spec`
拥有明确的冲突、人物选择、视觉动作、节奏、声画和镜头意图。原文不是提示词素材，
而是可回查的故事证据；不得以润化稿替换、压缩或改写用户明确事实与台词。

## Agent 步骤

1. 保留全文并计算 UTF-8 SHA-256，写入 `source.raw_text` 和 `source.sha256`。
2. 列出不可变事实、保护台词、用户约束、信息缺口；未知项必须留在 `unknowns`。
3. 生成导演处理：logline、主题、人物目标/阻力/代价、高潮选择、结尾钩子、情绪弧、
   三幕、节奏表、视觉母题、场景 beat、声音意图、镜头意图与带 Markdown 标题的
   `planning_text`。
4. 对每个非空处理字段写 `provenance`：`source_supported` 或
   `creative_suggestion`。不可把推断包装成原文事实。
5. 对用户回显标题、logline、关键选择、成人向处理（若有）与 `unknowns`；随后可直接
   写草案，但在 story lock 前等待用户确认。

## 成人向增强

仅当用户明确要求成人向，或原文有明确成人主题时，才填 `mature_intimacy`。启用时必须：

- 所有参与角色明确为成年人（`adult_only` 和 `participants_confirmed_adult` 都必须为
  `true`），且关系与每一步亲密互动均为明确自愿；不确定时写入 `unknowns`，不得自动补全。
- 接收器会拒绝任何同时出现未成年人和亲密信号的包；成人向信号存在却没有
  启用的 `mature_intimacy` 契约也会拒绝，不能用遗漏字段或 `enabled: false` 绕过门禁。
- 将画面看点落实到叙事功能：身体距离、眼神确认、服装/环境变化、雨声/音乐、反应镜、
  节奏与转场；不得用与角色关系无关的刺激替代戏剧推进。
- 标示为 `creative_suggestion` 的亲密增强只进入草案；现有 story lock、pilot、媒体审片
  和外部/付费门禁保持不变。

## CLI 交接

```bash
aifilm plan receive --root "<film>" --file "story-reception.json"
aifilm plan run --root "<film>" --received-file "<film>/receipts/story-reception.json"
```

`plan receive` 在 story 已锁时拒绝替换；锁前若要改写 reception，显式传 `--force`。
