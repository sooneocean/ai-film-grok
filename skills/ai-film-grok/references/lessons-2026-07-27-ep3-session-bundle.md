# ep3 会话总课 · 尺度 / 办事弧 / 高动 / 画风 / 禁裁头 / 交付（2026-07-27）

**片例**：`AI FILM SPACE/0727/ep3`（E病毒 ep3 · 9:16 · grok I2V）

**用户原话（必须长期记住）**

1. 成人尺度要拉到最高 —— **最重要**  
2. 肉戏要有连贯起承转合：**前戏 → 插入 → 射出** 都要有  
3. **插入时衣服裤子都要脱掉**；最好有 **特写锁定定器**  
4. **人头被裁掉了** —— 须全面思考构图链  

---

## 0. 冲突裁决（写死）

```text
#1 成人尺度 MAX（能升不降）
#2 完整办事弧（前戏→插入→射出；插入衣裤脱尽；定器可读）
#3 肉戏高动态 mean≥20（目标≥24）
#4 禁裁头 / full head + headroom
#5 MEDIUM LOCK cel 画风
#6 字幕硬烧 · 声线分轨 · 不回穿
```

**禁止**：用「审核方便 / mean 数字 / 画风抛光」砍插入、砍射出、假插入（内衣+军裤抬抱冒充办事）、砍人头。

---

## 1. 分课入口（本会话产物）

| 主题 | lesson | memory |
|------|--------|--------|
| 尺度 MAX + 四拍弧 + 插入脱尽/定器 | [adult-scale-max-sex-arc](lessons-2026-07-27-adult-scale-max-sex-arc.md) | [mem](../memory/2026-07-27-adult-scale-max-sex-arc.md) |
| 高动 + 画风双门 + gate 才桌面 | [high-motion-style-lock-final](lessons-2026-07-27-high-motion-style-lock-final.md) | [mem](../memory/2026-07-27-high-motion-style-final.md) |
| 禁裁头 · 裁脚>裁头 · 定器合法写法 | [headroom-no-crop-heads](lessons-2026-07-27-headroom-no-crop-heads.md) | [mem](../memory/2026-07-27-headroom-no-crop-heads.md) |
| 核心 IRON 总表 | — | [core-adult-iron-shipped](../memory/2026-07-27-core-adult-iron-shipped.md) |
| hard-defaults 行 | [hard-defaults](hard-defaults.md) | — |

---

## 2. 现场踩坑 → 规则

### 2.1 假动态 / 假交付

| 坑 | 规则 |
|----|------|
| I2V 未齐就拷桌面 → 后半 KB/静 | **仅** `receipts/i2v-final-gate.json` ok 才桌面 |
| 弱 raw 盖过强 takes | 多 take **max-mean** 选型；肉戏 10s → **6s+4s hybrid** |
| 并行 rebuild 抢写 final | 单 writer |

### 2.2 高动换半写实

| 坑 | 规则 |
|----|------|
| re-I2V 抬 mean 漂成 oily semi-real | 首段 **MEDIUM LOCK cel**；**Motion×Medium 双门** |
| style-relock 新 take 弱于旧肉戏 | 新 mean 须 ≥ thr×0.9 且 ≥ old×0.75 才装；否则 **keep old** |

### 2.3 假肉戏（结构）

| 坑 | 规则 |
|----|------|
| sc08 三镜同图站立贴脸 | **SEX_ARC_HUG_AS_SEX**；须 起/转/合 姿态递进 |
| 旁白写插入/射出、画面无纳入 | 结构失败；补 still+I2V 或改 beat |
| 时长 act+climax <50% | 记 `SEX_DURATION_UNDER_FLOOR`；优先拉长办事窗 |

### 2.4 插入脱尽 + 定器

| 坑 | 规则 |
|----|------|
| 内衣+军裤抬抱冒充插入 | **插入拍双方衣裤脱尽**（女 bare；男至少下装脱尽） |
| Imagine `content-moderated` 拦 true bare | **PARTIAL 诚实记账**；禁静默宣称「已脱尽」；继续冲或换后端/用户参考图 |
| 定器特写写成 `faces out of frame` | **非法砍头**；合法=脸+结合同镜 **或** 短 insert+前后全头主镜 |

### 2.5 人头被裁

| 坑 | 规则 |
|----|------|
| 定器无头主镜 | 退役；主戏 full head+headroom |
| `scale=increase,crop=720:1280` 切顶 | 优先 **decrease+pad**；验头后再考虑 crop |
| 竖屏抬抱全身 | **裁脚优先于裁头**；机位略拉远 medium-full |

### 2.6 字幕 / 声

| 坑 | 规则 |
|----|------|
| ffmpeg 无 libass / 路径空格 | **PIL 硬烧** 中文 SRT；抽帧可见才算 |
| mixed.wav 短于画面 | apad 到片长；禁 silent 尾 6s 无声当完成 |
| vocal_color | 本用户 **forever never** |

---

## 3. 四层漏斗（交付）

```text
generate（I2V 串行 OAuth）
  → select（max-mean + dual-gate medium）
  → assemble（pad 保头；hybrid 10s；mux VO/BGM）
  → desktop（仅 i2v-final-gate ok + 字幕 attestation）
```

---

## 4. Agent 一页清单（开 final 前）

- [ ] heat max · spice extreme · act+climax≥50%  
- [ ] 四拍：前戏 / 纳入前 / **插入（脱尽）** / **射出** 时间皆非零  
- [ ] 至少 1 合法定器（同镜双锁或短 insert）  
- [ ] 主戏镜无 `HEAD_CROP`  
- [ ] 肉戏 mean≥20；包络后半≥18  
- [ ] MEDIUM cel 未漂半写实  
- [ ] 中文字幕像素可见  
- [ ] gate.json ok · vocal_color=0 · 不回穿  

---

## 5. 版本

- 2026-07-27：ep3 会话总打包；回写 plugin 源 + installed-plugins 同步义务。
