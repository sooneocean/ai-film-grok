# Lesson 2026-07-21 · 办事剧旁白荤梗硬底（Sex VO Spice）

> **触发原话**：「沉淀教训…讲的内容都要包含荤梗，因为是实打实的荤场景的成人办事剧」  
> **P 码**：P0 交付 · P4 语义 · 刺激点  
> **互补**：  
> - [sex-duration-floor](lessons-2026-07-21-sex-duration-floor.md) → 性爱秒数  
> - [sex-undress-ladder](lessons-2026-07-21-sex-undress-ladder.md) → 卸甲脱衣  
> - [intercourse-impact-benchmark](lessons-2026-07-21-intercourse-impact-benchmark.md) → 画面冲击  
> - [ecchi-story.md](ecchi-story.md) → 说书人可更荤  

---

## 失败解剖

| 用户感受 | 工程事实 | 根因 |
|---|---|---|
| 像文艺短片 | heat max + 有办事镜 | **旁白仍是「灯灭/回眸/故事开始」** |
| 画面在干，耳朵干净 | VO 与画面脱节 | 说书人没收满身体动词 |
| 尺度小 | 双关不够 | 用「规矩/夜色」装色，**无荤梗落地** |

**一句话**：实打实办事剧 = **画面办事 + 耳朵办事**；`nar` 全程要有**荤梗**，act/climax 必须有**办事动词**。

---

## 规则（代码真相）

| 项 | 值 |
|---|---|
| 触发 | `heat_scale=max`（hot 软检） |
| 每镜 `nar` | ≥1 个 **荤梗/身体/双关** 标记（`_NAR_SPICE_MARKERS`） |
| act/climax `nar` | ≥1 个 **办事动词**（沉腰/办穿/吃进/锁腰/高潮/换你顶…） |
| write-spec | 默认 `sex_vo_strict: true` on max → hard fail |
| 码 | `HEAT_VO_SPICE_MISSING` · `HEAT_VO_SEX_VERB_WEAK` · `HEAT_VO_SPICE_RATIO_LOW` |

### 弱 vs 强

| 弱（fail） | 强（pass） |
|---|---|
| 灯灭了。故事却刚好开始。 | 展厅落锁。今晚只**加演**你一场。 |
| 她回眸一笑。 | 肩带一滑，**规矩**失效。 |
| 夜色温柔。 | **沉腰吃进**。再沉，节奏是她给的。 |
| 心跳加速。 | 她**失声**。背一弓——这一场**办穿**了。 |
| 晚安。 | 贴耳：**下一场——换你顶。** |

### Agent 写作清单

1. setup 也要荤入口（加演/落锁/只办你），不要纯风光  
2. foreplay：失序 + 双关（规矩/作业/加练）  
3. act：**沉腰/顶/磨/骑/吃进** 与 `dsl.action` 同动词  
4. climax：**办穿/办完/失声/腿软/高潮**  
5. afterglow：**换你顶 / 未完 / 下一场**，禁说教  
6. 字数仍 ≤55；一句一事 + 荤点，不堆形容词  

### 与画面双轨

- 审核软化 still → **加重 VO 荤梗 + SFX**，禁止 VO 也跟着变文艺  
- 口白·动作锁：`nar` 动词 = `dsl.motion` 首要运动  

---

## 验收

```bash
"$AIFILM" write-spec --root "<root>"
# _heat_arc.vo_spice.ok true
# spice_ratio ≈ 1.0 on max
```

pytest：`tests/test_heat_arc_multi.py`（VO spice cases）。
