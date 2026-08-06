# P0 · 画面抗重复 · 抗无聊 · 体位/特写/运镜（2026-07-29 · E病毒 ch04 避难所）

> **用户原话（两轮）**：
> 1）很多画面是重复的而且很无聊。
> 2）**肉戏太单调了啊 都是重复镜头 需要有不同体位 不同特写镜头还有运镜**。
> **片根**：`AI FILM SPACE/0729/e-virus-ch04-shelter` · 14 镜 · final 门绿仍 **观感 PARTIAL**。
> **关联**：[still-unique-no-reuse](lessons-2026-07-29-still-unique-no-reuse.md) · [high-motion-style-lock](lessons-2026-07-27-high-motion-style-lock-final.md) · [size-ladder](lessons-2026-07-21-size-ladder-hardcore-stack.md) · [evirus bulk→final](lessons-2026-07-29-evirus-ch04-bulk-final-iron.md)

## 现象（观众读到什么）

- 肉戏块 **像同一姿势 loop**：抽送节奏、构图、景别观感连着撞。
- 景别表上写了 insert/close-up，成片仍像 **中景拥抱幻灯片**（体位字段写了 doggy/straddle，像素仍是站抱）。
- **无真运镜**：整段 locked 脸/肩，没有 push-in / 侧移 / 环绕 / 抬头跟。
- **无真特写阶梯**：缺「脸反应 ↔ 结合/腰腹定器 ↔ 手/腿局部」跳切。
- 剪完后 **短、碎、平**——没有呼吸、没有机位事件。
- 门禁可全绿（clip sha 不同、mean 达标、review 过）→ **仍单调**。绿灯 ≠ 好看。

## 根因（ch04 实证）

| 层 | 发生了什么 | 观众后果 |
|---|---|---|
| **I2V motion 复制粘贴** | act/climax 几乎同一句 `rhythmic pelvic thrust breath hair sway` + 统一 headroom 套话 | 运动路径同质 → 肉眼 loop |
| **景别字被 camera 盖掉** | `dsl.shot_size=insert detail` 但 `dsl.camera.shot_size=medium`；rank 吃 camera 优先 | SIZE_LADDER 假绿/真平；定器镜看起来仍是腰上中景 |
| **头肩安全边写进每一镜** | 连 insert/定器也塞 `full head and both shoulders…` | 特写被冲淡；构图同框 |
| **姿势字段有、像素无** | paper 上 straddle/missionary/doggy/side_lying 换了，still/I2V 相位差不足 | 文件名不同 ≠ 可读差异 |
| **VO 驱动 stretch 过短** | plate 把 6s 源压到 ~3s 跟旁白 | 来不及建立信息；像 PPT 翻页 |
| **蒙太奇缺事件** | 连续 hard continue + 无 smash/反应/空镜/手部定器真跳切 | 无「剪辑惊喜」；只有顺序办事 |

**不是** stream_loop 双播（本片 stretch `loops=0`）。
**不只是** still 字节复用（见 still-unique）；**语义重复**同样致命。

## 铁律（后面不要再犯）

### A · 一镜一运动语言（I2V）
1. **禁止** 相邻 ≥2 镜共用同一 `dsl.motion` / 同一 I2V motion 主句。
2. 肉戏弧每镜至少换 **一维运动**：幅度（浅↔深）· 轴（前后/左右/转腰）· 节奏（快↔慢）· 身体部位主导（胯/腿/胸/手）· 镜头动（locked / push-in / orbit 轻）——**一次只加一种主动，勿堆词**。
3. HIGH MOTION 是 **门槛**，不是 **同一动词模板**。mean≥20 仍可无聊。

### B · 景别真变（still + camera 一致）
1. `shot_size` / `dsl.shot_size` / `dsl.camera.shot_size` **三处同值**；write-spec 后扫 rank，**连续 3 镜同 L 硬失败语义**（`SIZE_STACK_FLAT`）。
2. 肉戏块强制阶梯可读：**中/全建立 → 近脸/反应 → 定器 insert（L4）→ 再近**；act→climax **只收紧不突然回全景**。
3. **headroom 套话只写在需要头肩的镜**；insert/定器写「结合部/腰腹/手」构图，**禁止**把「完整头+双肩」硬塞进局部镜（头肩门与定器门冲突时：定器镜可无头，主戏反应镜保头）。

### C · 一镜一可读差异（still 源）
1. 字节唯一（still-unique）是底线；之上还要 **contact 抽帧可读差**：景别 **或** 姿势相位 **或** 机位轴 至少一维。
2. 禁止「只改 pose 字段、still 仍像上一张」：须 `image_edit` 出 **可见** 相位差再 I2V。
3. promote 末帧若与下一镜 still 观感≈同一构图 → **edit 再 register**，勿直接 bulk。

### F · 体位像素差（P0 · 用户 2026-07-29 强化）
1. 肉戏块 **≥4 种可读体位**（静帧 mid 一眼认得出），推荐池：骑乘 straddle · 传教 missionary · 后入 doggy · 侧位 side · 站抱 standing · 桌边 edge（可替换，禁名义换、像素不换）。
2. `sex_pose` / `dsl.sex_pose` **必须与 still 像素一致**；agent 验收：对 contact 说「这是后入」而非「这是又一个拥抱」。
3. 相邻 act 镜 **禁止** 同一体位连用 ≥2（可被反应 CU / 定器 insert 打断，但打断后主戏体位须变）。
4. 仅改 hair/光/脸角度 **不算** 换体位。

### G · 特写镜头配额（P0 · 同日）
肉戏窗（foreplay+act+climax）强制可读三类，缺一不可：
| 类型 | 最少 | 构图硬要求 |
|---|---|---|
| **脸/反应 CU** | ≥2 | 头肩在框；情绪可读（喘/咬唇/失神） |
| **定器 L4 insert** | ≥2 | 腰腹/结合/手/腿局部；**禁止**满头肩套话 |
| **关系/体位 MS–MFS** | ≥2 | 能读出谁在上/前后/侧位 |

禁止 7 镜全是「半身拥抱特写」。

### H · 运镜一镜一法（P0 · 同日）
1. I2V 每镜须写明 **唯一 camera 主句**，且相邻镜 **禁止** 同 camera：
   - 池：`locked static` · `slow push-in` · `slow pull-back` · `gentle orbit L/R` · `tilt-up follow` · `low-angle hold` · `handheld micro-shake`（一次只选一个主动）。
2. **禁止** 全段只有 `camera locked` + 同一身体动词。
3. 运镜与体位绑定写进 prompt 首句：`MEDIUM LOCK cel. Camera: slow push-in. Pose: doggy side…`
4. mean 高但运镜/体位撞车 → **仍 fail 观感**（重拍优先换 camera 或 pose，不单刷 mean）。

### D · 剪辑时间与事件（plate）
1. 办事主镜 **目标在片上 ≥4.5–6s**（VO 可垫，勿把视频压成 2.5–3.5s 连珠炮）。VO 过长用 pad/气口，**禁** setpts 把信息镜压碎。
2. 60s 级成人片：蒙太奇事件配额（与 hard-defaults 资深剪辑对齐）——**insert≥2 · 反应/空镜≥1 · smash 或轴跳≥1**；禁纯顺序幻灯片。
3. 连续 `chain_mode=continue` 时仍须 **机位/景别/体位事件**；continue ≠ 同一构图续命。

### E · 无聊预检（bulk 前 / selects）
成片前人工 10 秒扫 contact-sheet 或每镜 mid 帧：
- [ ] 相邻两镜能否 **一句话** 说出不同（「骑乘」「后入侧」「脸」「腰特写」）？
- [ ] 肉戏段 **≥4 体位** + **≥2 真 L4** + **≥2 反应 CU**？
- [ ] 相邻 I2V camera 主句不撞？
- [ ] 有无 ≥2 镜 motion 主句撞车？
- [ ] 有无 ≥3 镜连续同 size rank？

任一「否」→ **先改 still/I2V/切序，再 final**。禁止用 review-final 分数掩盖观感。

## Agent 操作清单

```text
write-spec 后
  1) 扫 motion：相邻 act/climax 主句去重；每镜写差异维
  2) 扫 size：camera.shot_size == shot_size；lint SIZE_STACK / NO_INSERT
  3) headroom 套话从 insert 镜剥离
pilot / bulk 前
  4) still_uniqueness + contact 可读差
  5) I2V 提示：MEDIUM LOCK + 本镜专属 motion（禁复制上一镜）
selects
  6) 杀「长得像」的 take；多 take max-mean 仍要看构图差
plate
  7) 主戏镜勿 VO-stretch 压碎；短 VO 可垫气，勿砍画面信息
```

## 验收

| 检查 | 通过标准 |
|---|---|
| motion 邻接 | 任意相邻 act/climax `dsl.motion` 主谓不同 |
| size 阶梯 | 无 SIZE_STACK_FLAT；肉戏块含 ≥1 L4 insert 真像素 |
| still | sha 全不同 **且** contact 相邻可读差 |
| plate 时长 | 主戏镜多数 ≥4.5s 在片上（非源片时长自我安慰） |
| 用户句 | 不再出现「重复且无聊」的同类反馈 |

## 与高动 / 尺度的优先级

冲突时：

1. **尺度 + 完整办事弧**（成人 max）
2. **可读差异 / 抗无聊**（本课）
3. **高动数字 mean**
4. 画风装饰

不得以「mean 过了」交差重复镜；也不得以「砍肉戏换花样」降尺度。

## 本片返工交付（2026-07-29 第二轮 · pose-camera rework）

**状态**：观感 **PARTIAL 改善**（体位/特写/运镜差已进片）· 尺度 **仍 PARTIAL**（软词亲密，非真 bare 插入）。

| shot | 可读体位/构图（contact） | 景别 | camera 主句 |
|---|---|---|---|
| s06_sh01 | 体检台贴脸 | CU | slow push-in |
| s06_sh02 | 床沿骑坐 | MS | gentle orbit right |
| s06_sh03 | 脸反应失声 | face CU | locked static |
| s06_sh04 | 双层床抱坐 | MFS | low-angle hold |
| s06_sh05 | 桌边后倾 | MFS | locked side hold |
| s06_sh06 | 腰手扣带定器 | insert L4 | locked insert |
| s06_sh07 | 侧卧贴紧 | MS | slow tilt-up |
| s07_sh01 | 舱壁墙抱托举 | MFS | handheld micro-shake |
| s07_sh02 | 高潮脸泪 | face CU | slow pull-back |

**工程落地**：
1. `film-spec`：`sex_pose` / `shot_size` / `dsl.camera.move` **与 still 像素对齐**（禁名义 doggy 实为站抱）。
2. still + I2V 全 unique sha；register 双轮；gates `spec/stills/clips` 绿。
3. plate：**固定 6s 槽** 手拼（`out/_pose_plate`），禁 VO-stretch 压碎；成片 `out/film_final.mp4` 84s → Desktop 同步。
4. HEAD_CROP：insert 用 `dramatic_function=sensory` + 去 `ecu` / `push-in on face` 字样；主戏反应镜保留 full head + headroom。

**再进阶（若用户要真办事像素）**：undress-anchor `image_edit` 分体位 bare → 过审再 I2V；过不了 → 诚实 PARTIAL，禁内衣冒充插入。

### GO 收口（同日晚 · DELIVERED_GO）

观感返工进片后用户 **GO** → 硬烧字幕 + 官方 closeout 链（timeline 对齐 6s 钟、SIZE 纸面、narrative 重绑、review-final、post-audit、export-desktop）。
**观感改善可交付**；尺度仍 PARTIAL（软词亲密）。收尾坑与命令链见 [closeout-gates-chaebol](lessons-2026-07-29-closeout-gates-chaebol.md) §9。

## 记忆入口

- Memory：[2026-07-29-shot-variety-anti-boring](../memory/2026-07-29-shot-variety-anti-boring.md)
- 收尾 GO：[closeout-gates-iron](../memory/2026-07-29-closeout-gates-iron.md)
- hard-defaults 行：画面抗重复·抗无聊 · 肉戏体位·特写·运镜 · 收尾门禁
- Agents IRON 同题 · session-index 2026-07-29 表行
