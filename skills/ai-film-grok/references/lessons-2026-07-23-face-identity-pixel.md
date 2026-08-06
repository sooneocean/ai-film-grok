# Lesson 2026-07-23 · 像素 face-identity 哈希门禁

> **触发**：街角重逢 EP01 — 用户反馈写实人物不稳；要求把「像素级 face-identity 哈希」接到 post_audit（此前只有 warning 空壳）。  
> **P 码**：**P0 身份/视觉** · Visualize → Select  
> **片例**：`lushiran-reunion-ep01` · cast master 已锁，keyframes 多镜 FAIL = 有效漂移信号  
> **代码**：`scripts/face_identity.py` · CLI `aifilm face-identity *` · 收据 `receipts/face-identity.json`  
> **互补**：[style-lock-from-ref](lessons-2026-07-23-style-lock-from-ref.md) · [consistency §1a/S7](consistency.md) · [shaofu-cast](lessons-2026-07-22-shaofu-cast-subs-bgm-final.md)

---

## 一句话

```text
cast master enroll → keyframe 像素比对 → verified 才算脸锁闭环
没有 face-identity.json = 只有口头「像」；有 FAIL = 该镜禁止当过审 still 盲 I2V
```

---

## 失败解剖（优化前）

| 状态 | 事实 |
|---|---|
| post_audit | 仅检查「有没有文件 / verified 布尔」 |
| 收据 | 可被手写 `verified:true` 绕过，无像素证据 |
| 结果 | 脸漂仍 bulk → 成片「换演员感」 |

---

## 硬规则（F0–F8）

| # | 规则 | 要求 |
|---|---|---|
| **F0** | 有 cast_masters 必须 enroll | `aifilm face-identity enroll-bible`（或 lock-style 自动 enroll） |
| **F1** | 多 anchor | cast master + `canonical/cast/*face-lock*` 一并 enroll；比对取**最佳**匹配 |
| **F2** | 算法 | face-region 裁切 → 高斯模糊 → aHash + dHash + RGB 色史（Pillow only，无重 ML） |
| **F3** | 同文件捷径 | `sha256` 相同 → score=0 必过（修 `score or 99` 的 0 假值 bug） |
| **F4** | audit | `aifilm face-identity audit` 扫 `keyframes/`（跳过 env 空 cast、`_last`/`-seed`） |
| **F5** | verified | 全部检查 ok 且已 enroll → `verified=true`；否则 false |
| **F6** | post_audit | 无收据 / 未 verified / enroll 缺口 → `FACE_IDENTITY_DRIFT`（warning）；文案指向 audit |
| **F7** | register-still | 可选 `--require-face-identity`：像素 FAIL → 禁 approved |
| **F8** | FAIL 是信号 | photoreal 多镜 FAIL 多 = 正常；**禁止**为过门乱调阈值到「全绿」 |

### 默认阈值（v2）

| 通道 | 默认 | 含义 |
|---|---|---|
| aHash max | 22 | 模糊后面结构 |
| dHash max | 24 | 边缘差 |
| hist max | 0.72 | 肤色/头区色分布 |
| 通过 | hist_ok **且** (ahash_ok **或** dhash_ok)，score≤5 | 拒纯环境板 / 拒双 hash 全炸 |

CLI 阈值默认跟模块常量，**禁止** argparse 写死旧 14/16/0.55 盖掉模块。

---

## CLI 速查

```bash
aifilm face-identity enroll --root "$ROOT" --char-id lushiran --source canonical/cast/lushiran-master.png
aifilm face-identity enroll-bible --root "$ROOT"
aifilm face-identity verify --root "$ROOT" --image keyframes/ep01_….png --char-id lushiran
aifilm face-identity audit --root "$ROOT"            # 写 verified
aifilm face-identity audit --root "$ROOT" --strict   # 有 FAIL 则 exit 2
aifilm face-identity status --root "$ROOT"
```

### 收据形状（摘要）

```json
{
  "kind": "face-identity",
  "verified": false,
  "enrolled": {
    "lushiran": {
      "n_anchors": 8,
      "anchors": [{ "source": "…", "sha256": "…", "fingerprint": {…} }]
    }
  },
  "checks": [{ "path": "…", "ok": false, "score": 3.2, "ahash_distance": 15, "hist_distance": 0.9 }],
  "audit": { "n_fail": 5, "n_checks": 9 }
}
```

---

## Agent 工序位置

```text
style-lock plan/apply → lock-style(cast) → face-identity enroll-bible
  → pilot stills → face-identity audit（或 verify 单镜）
  → FAIL 镜 image_edit 修 still → 再 audit
  → 过再 I2V bulk
```

与 [verify-before-generate](lessons-2026-07-22-verify-before-generate.md) 对齐：**像素身份 = still 闸的一道**，不在 I2V 后才发现换脸。

---

## 片例读数（街角重逢 · 写实）

| 结果 | 解读 |
|---|---|
| 男主 MCU OK | 近景、与 master 构图接近 |
| 侧脸/强霓虹/双人/远景 FAIL | hist 或 dHash 炸 — 仍是同人问题或构图差过大 |
| verified=false | **应修 still 或改 manhua medium**，不是删收据装绿 |

---

## 禁止

- 手写 `verified: true` 跳过 audit  
- 为让全片绿而把阈值放到「石头也能过」  
- 用整页 character sheet 当唯一 anchor 且不裁 face-lock  
- env 镜强制对女主 hash（应 skip 空 cast）

---

## 验收

- [ ] `receipts/face-identity.json` 存在且含 `enrolled`  
- [ ] `audit` 后 `checks` 非空（有 keyframe 时）  
- [ ] post_audit 在无收据时出现 `FACE_IDENTITY_DRIFT`  
- [ ] `pytest tests/test_face_identity.py` 绿  
- [ ] 同文件 verify score=0  
