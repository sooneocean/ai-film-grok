# build_dispatch 分段地图（2026-08-07 · α.2 只文档）

**Status:** MAP ONLY · 不默认 peel  
**模块:** `skills/ai-film-grok/scripts/spine/dispatch.py`

| 段 | 内容 | 下游 |
|----|------|------|
| D0 装载 | root/manifest/craft/locks | 全部 |
| D1 能力 | capability cache · weapon | weapon_route |
| D2 阶段 | project_stages | stage status |
| D3 next | next_actions/blocked_by | next_action |
| D4 重选 | re-select | 防陈旧 |
| D5 摘要 | drama graph + jobs | 非破坏 |
| D6 打包 | packet + receipt | dispatch.json |
