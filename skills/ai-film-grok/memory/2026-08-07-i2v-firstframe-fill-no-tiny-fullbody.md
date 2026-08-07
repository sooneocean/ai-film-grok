# I2V 首帧必须满幅 · 禁小全身定妆（P0 · 2026-08-07 · 席德 EP02）

> **类比**：不能把「全身设定立牌照」直接塞进竖屏电影当第一格——人像会缩成邮票。  
> **闭环**：量测 → 自动补救 → 再过门 → 登记/H3/链 全路径硬拦（不是只改一次脚本）。

## 事故
- **EP02《回放泄露》**：开工为图快，把 `cast/*-master-fullbody` / 全身定妆图 **原样** 当 `keyframes/<shot>.png` → I2V。
- 量测：主体面积填充 **~0.49**（半框空白灰棚）；链式 last-frame 把小主体传遍 bulk。
- 用户原话：**「画面构图有问题吧 怎么画面这么小」** → 已 wipe 重开 + 满幅 CU 首帧。

## 铁律（以后不准再犯）
1. **禁止** 将全身 turnaround / fullbody cast master **未 cover-crop** 直接作 I2V 首帧。
2. I2V 首帧必须是 **单场景叙事静帧**，且 **主体高度填充 ≥ ~75%** 竖画幅（脸 CU / 半身 MS 优先）；灰棚大空白 = 废。
3. 开集/新链：**先** 定妆脸或状态照 → **满幅构图** still → 再 H3；**再** last→next chain。
4. 定妆图只作 **身份锚**，不是 timeline 构图。需要全身感：先 cover-crop / 重画成 MS/CU，再 I2V。
5. prompt 须带构图硬句（或机读锁）：`COMPOSITION LOCK` · `subject fills frame` · `no tiny full-body` · `no letterbox`。
6. **链式 last-frame** 须 strip letterbox（或 `ensure_fill_frame`）后再写 next keyframe；禁把黑边+小主体原样传给下一镜。

## 机读闭环（深度）

| 环节 | 行为 |
|------|------|
| **量测** | `measure_subject_fill` → `height_fill` / `area_fill` / black bars |
| **自动补救** | `ensure_fill_frame`：strip letterbox → `cover_crop_subject` → 再量 |
| **单镜门** | `assert_i2v_firstframe_fill(mode=open\|chain)` |
| **H3 前** | `assert_keyframe_ready_for_h3(..., auto_remedy=True)` |
| **整片审计** | `audit_film_composition_fill(root)` |
| **register-still approved** | 硬门 + 一次 ensure 再过；记 `composition_fill` |
| **still_source** | `assert_still_source_safe` 拒 cast path + tiny fill |
| **generation_ready** | line 含 `fill=ok\|hardN`；blockers `COMPOSITION_FILL:*` |
| **码** | `I2V_FIRSTFRAME_TINY_SUBJECT` / `CAST_FULLBODY_AS_FIRSTFRAME` / `I2V_FIRSTFRAME_LETTERBOX`(+`_SOFT`) |
| **逃生** | `AIFILM_SKIP_COMPOSITION_FILL=1`（仅调试） |

CLI 烟测：
```bash
python scripts/composition_fill_gate.py /path/to.png --json
python scripts/composition_fill_gate.py --root "$ROOT" --audit --json
python scripts/composition_fill_gate.py --root "$ROOT" --shot SHOT --ensure --json
```

阈值默认：open `hfill≥0.72` `afill≥0.55`；chain 略松 `0.68/0.50`（letterbox 硬拦仅「大黑边+主体仍小」）。

## 制度指针
- hard-defaults 表行 · Agents 指针 · 本卡

## 修复回执
- 坏链备份：`ep02/work/comp-bad-backup/`
- 修复卡：`ep02/receipts/composition-fix-2026-08-07.json`
