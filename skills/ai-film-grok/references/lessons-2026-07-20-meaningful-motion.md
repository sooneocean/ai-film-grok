# 分镜动态须有叙事意涵（Meaningful Motion · 2026-07-20）

**用户反馈**：效果不错之后，要优化分镜产出的**影片动态细节**——让动态有**实际意涵**，不是氛围微动堆叠。

## 一句话

> 每一镜 I2V 必须让观众读到：**故事世界在这一秒发生了什么变化**；运镜/眨眼只能服务这个变化，不能取代它。

## 弱 vs 强

| 弱（空动态） | 强（有意涵） |
|---|---|
| soft blink, breath, slow push-in | 手拧上门闩 → 逃路被封 |
| camera dolly, hair drift, idle | 双手撑上梳妆台 → 距离只剩半掌 |
| beautiful cinematic motion | 掀帘跨入灯光 → 角色占场 |
| 全片同一套微动 | 每 beat 一种**故事功能**的可见变化 |

## Beat → 故事问题 → 动态必须回答

| dramatic_function | 观众问题 | 动态必须让人看见 | 微动角色 |
|---|---|---|---|
| **hook** | 谁出现？占了什么空间？ | 入场 / 掀帘 / 开门 / 现身 | 垫后 |
| **approach** | 空间怎么变窄？ | 走近 / 落锁 / 关距 | 垫后 |
| **sensory** | 身体哪一处在说话？ | 呼吸起伏 / 汗珠 / 指尖颤 | **可为主**（须绑 nar 感官词） |
| **reaction** | 她怎么反应？ | 眼神 / 比心 / 一怔 / 笑 | 可为主 |
| **action** | 她做了哪件改变局势的事？ | 撑台俯压 / 解扣 / 拉近 | 垫后 |
| **afterglow** | 余韵是什么邀请？ | 停在邀请距离 / 一眨眼收钩 | 可为主 |
| **bridge** | 怎么过渡？ | 明确方向的位移/摇镜 | 可为主 |

## 写法契约（film-spec）

```json
"dsl": {
  "story_beat": "她落锁，把两人关进同一私密空间",
  "visible_change": "门闩从开到关；她的身体转向梳妆台",
  "action": "turns door latch shut with fingertips",
  "motion": "reaches latch, turns it shut, body angles to vanity — continuous, no settle hold, idle not speaking",
  "cut_on": "mid_motion"
}
```

| 字段 | 作用 |
|---|---|
| `story_beat` | 一句戏：这镜戏剧上干什么（中文可） |
| `visible_change` | 可观测世界变化（状态 A→B） |
| `action` | 英文主动词 + 物件（= nar 事件） |
| `motion` | **先**可见过程，**后** filler；continue 缝勿 settle 收尾 |

### I2V prompt 纪律

1. 第一句 = `visible_change` / 主动作过程  
2. 禁止只写 mood / cinematic / beautiful  
3. 禁止 hook/approach/action 以 blink+breath+push-in 开头  
4. 一镜一意涵；第二动作拆下一镜  
5. 与 `nar` 同事件（口白·动作锁）

## Lint 码（soft；`meaningful_motion_strict` 可硬拦）

| 码 | 含义 |
|---|---|
| `MOTION_NO_MEANING` | 几乎只有审美 filler |
| `BEAT_SEMANTICS_MISS` | 动态与 beat 家族语义不符 |
| `VISIBLE_CHANGE_MISSING` | 驱动镜缺 visible_change/story_beat 且主动作弱 |
| `PRIMARY_MOTION_WEAK` | 已有：驱动镜无主动词（vo-motion-link） |

```bash
"$AIFILM" write-spec --root "<root>"   # 写入 _meaningful_motion
"$AIFILM" preflight --root "<root>"    # soft: meaningful_motion
```

## 与既有规则

| 规则 | 关系 |
|---|---|
| **[principles.md](principles.md) P0/P4** | 本文件是可观测变化 + 语义绑定的实例 |
| 口白·动作锁 | 意涵的「说什么」；本文件是「画面为何动」 |
| mid_motion / visual_fit | 动能与剪点；本文件是**语义** |
| continuity chain | 镜间姿势；本文件是**单镜故事功能** |
| motion QA | 像素能动；本文件要求**能动且有戏** |

## Agent 检查单

- [ ] 每镜能用一句话写出 `visible_change`（A→B）  
- [ ] 闭眼听 `nar` 能猜到 motion 主动词  
- [ ] hook/approach/action 无「纯氛围微动」  
- [ ] 连续 3 镜故事功能不重复（不只是景别不同）  
- [ ] I2V 失败重试时加强**意涵动词**，不堆 blink  

## 相关

- [lessons-2026-07-17-vo-motion-link.md](lessons-2026-07-17-vo-motion-link.md)  
- [lessons-2026-07-20-action-fluency.md](lessons-2026-07-20-action-fluency.md)  
- [shot-motion.md](shot-motion.md)  
