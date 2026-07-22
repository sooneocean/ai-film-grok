# Lesson 2026-07-22 · I2V 末帧回穿 + promote 毒化（No Re-Dress · 动像素）

> **触发原话**：「卸甲不回穿里面又出现前面脱下的红外套」  
> **片例**：`astra-encore-120`（阿斯特拉·闭馆加演）  
> **回执**：`astra-encore-120/receipts/wardrobe-redress-fix-2026-07-22.md`  
> **P 码**：P0 交付 · P1 身份/定妆 · P4 语义  
> **互补（必读）**：  
> - [lessons-2026-07-21-wardrobe-no-redress-still.md](lessons-2026-07-21-wardrobe-no-redress-still.md) → **still 源链**（静帧禁 cast 全装）  
> - [lessons-2026-07-21-first-last-gen.md](lessons-2026-07-21-first-last-gen.md) → promote 末帧→下镜首帧  
> - [lessons-2026-07-21-sex-undress-ladder.md](lessons-2026-07-21-sex-undress-ladder.md) → wardrobe rank  
> - [consistency.md](consistency.md) §1e / §1f  

---

## 一句话

**脱下 = 永久** 不只卡 still 源：  
`I2V 末帧若把外套穿回` → `register-clip promote` 会把**毒像素**写成下一镜 keyframe → 全片回穿。

静帧过闸 ≠ 动态过闸。**末帧才是真相。**

---

## 失败解剖（astra-encore-120 · shot04→05）

| 用户感受 | 工程事实 | 根因 |
|---|---|---|
| 前面脱了红外套，后面又穿上 | shot04 首帧 partial（半脱）合法 | **I2V 运动把外套穿回肩/胸** |
| 下镜也坏了 | `_last_shot04` torso 红外套红区 ≈11.9% | **promote 把毒末帧写成 shot05.png** |
| write-spec / Costume HARD 已写 | prompts 仍注入 full 套装句 | **identity_lock 每镜写 `ceremonial red jacket`** → 文字助推回穿 |

| 资产 | 毒前 | 修后 |
|---|---|---|
| shot04 末帧 | 全装红外套穿回 | 外套离肩/落地（torso 红外套红区 ≈0.4%） |
| shot05 源 | = 毒末帧 | undressed 无外套 + 合法 promote |
| undress-anchor | 错锚 / 未锁峰值 | = 无外套峰值 still |

---

## R0 · 铁律（agent 必背 · 2026-07-22 加厚）

```text
1) still 源：peak 后禁止 image_edit(全装 cast)     ← 07-21
2) I2V 源：只吃本镜 keyframe（已脱）              ← 07-21
3) I2V prompt：Keep first-frame clothing HARD
   do NOT put [discarded garment] back on
4) register-clip 后立刻抽 last frame 人眼/粗检：
   肩/胸是否又穿回已脱衣物？
   YES → fail clip，禁止 promote，重 I2V
   NO  → 才允许 promote → 下镜 keyframe
5) identity_lock / Character 行：只锁脸发
   全装词只写在 wardrobe_state=full 变体
   undressed|bare 禁止写「jacket ON / full costume」
6) motion 分不够：加大转体/甩发/走步
   禁止用「穿回外套」换 motion_score
```

---

## R1 · register-clip 末帧门（P0 · 新增）

```bash
# 伪流程 — 每镜 register 前/后必做
ffmpeg -y -sseof -0.05 -i clips/<shot>.mp4 -frames:v 1 /tmp/last.png
# 人眼：肩/胸/腰 是否出现已丢弃的主外套/盔甲/丝袜穿回腰
# 可选粗检：上半身 ceremonial-red 像素占比 vs 首帧（突增 = 回穿嫌疑）

# 回穿 → 不要 register 为 approved；不要让 auto-promote 写下一镜
# 不回穿 → register + 允许 promote；若为本片 undress peak：
cp keyframes/_last_<shot>.png  canonical/wardrobe/undress-anchor.png
```

**promote 是接戏神器也是回穿加速器**：只 promote **衣着合法** 的末帧。

---

## R2 · I2V prompt 模板（卸装后）

```text
Keep first-frame clothing exactly.
Do NOT put the red jacket / armor / discarded garment back on.
Never re-dress. Clothes discarded stay off the body.
Strong body motion OK: turn, step, hair whip, lean —
but wardrobe state must not reverse.
```

partial 卸外套镜 end_pose 必须写清：  
`jacket off torso / falling / on floor — NEVER neatly worn again`

---

## R3 · 文字源污染（identity_lock）

| 坏 | 好 |
|---|---|
| identity 永远含 `ceremonial red ruffled jacket + white corset when full` 整段进每镜 | identity = **脸/发/瞳/签名饰品 only** |
| bare 镜 Character 仍列 full 套装 | `wardrobe_variants[state]` 分叉；undressed = `jacket DISCARDED off-body` |
| subject 复制 full 描述 | `dsl.subject` 按 `wardrobe_state` 选 SUBJECTS[full\|partial\|undressed\|bare] |

write-spec 注入的 `Costume continuity HARD` **保留**；不得靠它掩盖全装 ref / 毒末帧。

---

## R4 · 与 07-21 still 课的分工

| 课 | 卡什么 |
|---|---|
| 07-21 still 源链 | **生成静帧时** 用了全装 cast → 回穿 |
| **07-22 I2V 末帧**（本课） | **静帧已对**，I2V 把衣穿回 + promote 扩散 |

两课都过 = 卸装不回穿才算过。

---

## R5 · 验收清单

- [ ] undress peak 后每镜 last frame：已脱标记在（外套不在肩/胸整穿）  
- [ ] promote 后的 `keyframes/<next>.png` 与合法 last **同衣着**  
- [ ] undress-anchor 存在且为无主外套峰值  
- [ ] prompts undressed/bare 无 `jacket ON` / `full stage costume` 当当前态  
- [ ] 用户说「又回穿」→ 停 bulk → 从 undress-anchor 重做 peak 后 still+I2V  

---

## 链到主脊

- [SKILL.md](../SKILL.md) 硬门禁 · §1 视觉  
- [hard-defaults.md](hard-defaults.md)  
- [consistency.md](consistency.md) §1e + §1f  
- [AGENTS.md](../../../../AGENTS.md) 日常影音 Combo  
- 片例回执：`/Users/dex/AI FILM SPACE/0721/astra-encore-120/receipts/wardrobe-redress-fix-2026-07-22.md`
