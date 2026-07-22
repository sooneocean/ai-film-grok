# Lesson 2026-07-22 · 用户原文保真（User Source Fidelity）

> **触发原话**：「剧情太多是之前测试的影子…完全遵照我输入的文本…每一个都是独立的内容输入…画面跟口白不对齐」  
> **P 码**：P0 交付 · P4 语义 · 叙事上游  
> **片例**：金瓶梅·第一回（ximenqing-ep01）— plan 输出满屏「展厅落锁」，用户诗白/财色旁白被抹掉  

---

## 失败解剖

| 用户感受 | 工程事实 | 根因 |
|---|---|---|
| 像别的测试片 | heat max + hardcore | `plan_shots` **整句替换** `_SPICY_NAR`（展厅落锁…） |
| 三场戏重复 | 时长≥90s 自动 dual_climax | 每场景再套完整成人脊柱 → 3×同构办事模板 |
| 角色名乱 | 角色：西门庆：… 列表 | 解析把「基调/尺度/标题」当 cast |
| 口白≠画面 | 用户诗 vs 模板 act motion | 未锁 nar↔dsl.action；模板 VO 与 story still 脱节 |

**一句话**：用户输入是脊柱；荤梗模板只能**补**，不能**盖**。多段剧本各自独立，禁止克隆同一测试骨架。

---

## 规则（代码真相）

| 项 | 值 |
|---|---|
| 旁白 | `preserve_user_nar()`：有用户句 → 保留；缺荤梗才后缀补「沉腰/色」 |
| 模板整句 | 仅当 beat `source_text` 空/无效时才用 `_SPICY_NAR` |
| dual_climax | **仅** dual 标记 / `spine=dual_climax`；**禁止** 仅因 duration≥90 自动双轮 |
| 多场景 adult | `extract_beats` 用 `_compact_adult_spine_for_scene`（3–5 拍本地弧） |
| 角色 | blocklist 元标签；`- 西门庆：` bullet 解析 |
| 场景切分 | 支持 `【00:00…】` / `### 第N集` 段 |
| write-spec 闸 | `user_source_fidelity_strict`（max 默认 true）→ `USER_SOURCE_NAR_POLLUTED` hard fail |
| 污染判定 | ≥40% 旁白含 `展厅落锁/加演/贴耳：下一场…` 库存句 |

码：`USER_SOURCE_NAR_POLLUTED` · `USER_SOURCE_TOKENS_MISSING`

---

## Agent 写作清单

1. 有完整剧本 → **先**把用户诗白/对白写进 `nar`，再考虑 sex_vo  
2. `plan run` 后扫一遍 nars：若出现「展厅」而用户没写展厅 → **立即 rewrite**，禁止 bulk  
3. 多集/多段：每段独立 film root 或独立 scene body；禁止跨集复用别片 still/clip  
4. 口白动词 = `dsl.action` 主动词 = I2V motion（`sex_vo_motion_strict`）  
5. 新片 `init` 空 root；不要把旧 film 的 prompts/clips 拷进新 root  

---

## 验收

```bash
# 用户长剧本 + hardcore 不应产出「展厅落锁」主导旁白
"$AIFILM" plan run --root "<tmp>" --file story.txt --target-duration 90 --force --apply-film-spec
python3 -c "import json;..."  # assert no 展厅落锁 in majority of nars
"$AIFILM" write-spec --root "<tmp>"  # USER_SOURCE_* 不得 hard-fail 于保真稿
```

pytest：`tests/test_user_source_fidelity.py`

---

## 相关

- [sex-vo-spice](lessons-2026-07-21-sex-vo-spice.md) — 荤梗硬底（补，不盖）  
- [adult-max-playbook](adult-max-playbook.md) — 成人脊柱  
- [verify-before-generate](lessons-2026-07-22-verify-before-generate.md) — 先验后生  
- `story_plan.preserve_user_nar` · `edit_policy.lint_user_source_fidelity`  
