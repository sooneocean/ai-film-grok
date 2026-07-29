# Memory · 2026-07-29 成人尺度全链路强制拉满（Wave 1）

## 用户目标
整条生成链路把尺度 / 色气 / 成人指数强制顶格（解剖 IRON 不放行畸形）。

## 代码真相（plugin ≥2.17.3）

| 漏热 | 修法 |
|------|------|
| genre=adult 未钉 max | `normalize_story` + `select_beat_spine` → ADULT_MAX + extreme |
| sex_arc 字段缺 | plan 投影写 `sex_arc_beat` / coitus / wardrobe；lock→detail |
| 四拍时长可偏 | `SEX_ARC_RATIO_SKEW` + `SEX_ARC_RELEASE_RATIO_LOW` **warning→hard** |
| impact 只记分 | write-spec + review-final：**≥75 (A)** |
| 弱 VO 靠人改 | `apply_vo_spice_auto`（`sex_vo_auto_apply` 默认开） |
| state 缺口 soft | undress-anchor + undressed/bare **hard** on max |

## 逃生
`heat_scale:soft` · `adult_max_iron:false` · `erotic_impact_strict:false` · `sex_vo_auto_apply:false` · 各 `*_strict:false`

## 未做（Wave 2）
soften-compensate CLI · endframe wardrobe rank 自动 promote 拦 · music_energy 跟 phase · pilot 三拍绑 bulk
