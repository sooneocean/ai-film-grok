# Lesson 2026-07-21 · 卸装后禁止回穿（Still 源链 · No Re-Dress）

> **触发原话**：「衣服好像又回穿了 然后衣服被脱下来 就要脱下来 不能在穿回去 修复此严重bug」  
> **片例**：`xide-hardcore-thrust`（席德·硬核抽插）  
> **回执**：`receipts/wardrobe-redress-fix-2026-07-21.md`  
> **P 码**：P0 交付 · P1 身份/定妆 · P4 语义  
> **互补**：  
> - [keyframe-first-state-index](keyframe-first-state-index.md) → **状态照索引 + 倒推改 keyframe**  
> - [sex-undress-ladder](lessons-2026-07-21-sex-undress-ladder.md) → wardrobe rank / write-spec clamp  
> - [first-last-gen](lessons-2026-07-21-first-last-gen.md) → 末帧 promote 接戏  
> - [consistency.md](consistency.md) §1e → 静帧源硬锁  

---

## 失败解剖

| 用户感受 | 工程事实 | 根因 |
|---|---|---|
| 前面脱了，后面衣服又穿上 | film-spec `wardrobe_state=bare` 已写 | **静帧源错了**：shot05–10 又从 **全装 cast master** `image_edit` |
| write-spec 过了仍回穿 | JSON rank 单调 | **文字门禁 ≠ 像素门禁**；模型见全装 ref 就画回全装 |
| 审核双轨可以软 | suggestive 仍可半脱 | 为过审走了 cast 全装 = **剧情回穿**，比审核失败更严重 |

**一句话**：  
`wardrobe_state` 写 bare 不够；**ref 图是全装 = 成片必回穿**。  
卸装峰值之后，**唯一合法 still 源** = 已脱 still / undress-anchor / 上镜末帧，**永远不是**全装 cast master。

---

## R0 · 铁律（agent 必背）

```text
脱下 = 永久（本片内）
rank 只前进：full → armored → partial → undressed → bare
禁止：partial|undressed|bare 镜 的 image_edit(image=全装 cast master)
必须：image_edit(image=undress-anchor 或 上镜已脱 still)
I2V：motion prompt 写 Keep first-frame clothing — never re-dress
```

---

## R1 · Still 源链（生成 SOP）

| 阶段 | 合法 still 源 | 非法 |
|---|---|---|
| setup 全装 | cast master | — |
| 第一镜卸装动作 | cast master → 产出 **undress peak still** | 跳过卸装直接 act 全装 |
| undress peak 之后（含 act/climax/afterglow） | **`canonical/wardrobe/undress-anchor.*`** 或上一已脱 keyframe / promote 末帧 | **全装 cast master**、全装 style-v1 当脸锚又当衣锚 |
| I2V | 该镜 keyframe（已脱） | 另起 cast 静帧再 I2V |

### 卸装锚点（必落盘）

卸装峰值镜（首次 `partial` 顶格或 `undressed`）批准后立刻：

```bash
mkdir -p "<root>/canonical/wardrobe"
cp "<root>/keyframes/<undress-peak>.png" \
   "<root>/canonical/wardrobe/undress-anchor.png"
# receipt 记：peak shot_id + SHA
```

此后 **每一镜** `partial|undressed|bare`：

```text
image_edit(
  image = undress-anchor 或 上一已脱 still,
  prompt = "Same clothing state as reference — do NOT put clothes back on.
            Only change pose/camera. Keep half-down stockings / discarded armor / open dress.
            Costume continuity HARD."
)
```

**禁止**并行批量 `image_edit(cast)` 生成 act 十镜。

---

## R2 · Prompt 硬词（中英可混）

Still / I2V 必含至少一类：

| 类型 | 例句 |
|---|---|
| 状态锁 | `ALREADY UNDRESSED from prior` · `clothes discarded on floor` |
| 禁回穿 | `do NOT put clothes back on` · `never neat full dress` · `NEVER re-dress` |
| 像素延续 | `Keep first-frame clothing exactly` · `stockings stay half-down` |
| 身份 | 仍可写发色/脸，**衣着描述不得写回 full tech dress closed** |

write-spec 注入的 `Costume continuity HARD` 行 **不得删**。  
`prompt_injector`：undressed 时 **禁止** fallback `default_wardrobe`（全装回退）。

---

## R3 · 验收（交付前）

| 检查 | 方法 | fail |
|---|---|---|
| 像素不回穿 | 从 undress peak 起每镜抽 t=1s：半脱标记（丝袜半褪/甲落地/裙开）仍在 | 整齐全装 / 丝袜穿回腰 |
| 源链 | act 镜 still 的生成记录 ref ≠ cast full | receipt 写 cast master only |
| film-spec | `_wardrobe_continuity` 无 re-dress；无 `HEAT_WARDROBE_*` hard | write-spec fail |
| I2V | motion 句含 keep clothing；未出现「fully dressed again」 | 重 I2V |

用户说「回穿了」→ **P0**：停 bulk → 从 undress-anchor 重做 peak 之后全部 still+I2V → re-final。

---

## R4 · 与审核双轨的关系

| 可做 | 不可做 |
|---|---|
| 软裸 / 遮挡 / 剪影男 / 半脱可读 | 为过审 **整镜换回全装 cast** |
| VO 加重办事动词 | 文字 bare、像素 full |
| 换角度再试 undress-anchor | 放弃锚点从 cast 重起 |

审核失败 ≠ 授权回穿。

---

## 片例对照（xide-hardcore-thrust）

| 镜 | 坏做法 | 修法 |
|---|---|---|
| shot04 | 半脱 peak（对） | → 存 undress-anchor |
| shot05–10 旧 | `image_edit(cast 全装)` | 从 undress-anchor 只改姿势 |
| I2V 旧 | 全装首帧 | 已脱 keyframe + keep clothing |
| 成片 | 观众见回穿 | re-I2V + re-final |

---

## 链到主脊

- [SKILL.md](../SKILL.md) 硬门禁 · §1 视觉  
- [hard-defaults.md](hard-defaults.md) 卸装延续·不回穿  
- [consistency.md](consistency.md) §1e  
- [sex-undress-ladder.md](lessons-2026-07-21-sex-undress-ladder.md)  
- [first-last-gen.md](lessons-2026-07-21-first-last-gen.md)  

---

## 续课 · 2026-07-22（I2V 末帧 + promote）

**新片例**：`astra-encore-120`——still 半脱正确，**I2V 把红外套穿回**，`register-clip` promote 毒化 shot05。

完整纪律见 **[lessons-2026-07-22-i2v-endframe-no-redress.md](lessons-2026-07-22-i2v-endframe-no-redress.md)**。

| 加厚 | 要求 |
|---|---|
| 末帧门 | register 前抽 last frame：肩/胸不得整穿已脱衣物 |
| promote | 仅合法末帧可写下一镜 keyframe |
| 文字 | identity_lock 只锁脸发；full 夹克词勿进 bare 镜 |
| motion | 用转体/甩发换分，禁止用回穿换 motion_score |
