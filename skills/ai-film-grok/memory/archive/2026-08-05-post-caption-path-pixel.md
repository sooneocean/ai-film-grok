# Memory · 2026-08-05 · 后期字幕路由 + 像素机检 P0

## 用户原话
> 帮我优化我的流程有关于后期的部分提出优化todo plan

## 三句
1. **一集一 `caption_path`**：`master_hf`（plate off + HF）或 `ship_hardburn`（板硬烧）；回执 `receipts/post-route.json`。  
2. **像素有字**：`aifilm caption-pixel-check` 底带 ink 机检；closeout 合入 `caption_pixel` + `evidence_fresh`。  
3. **禁双烧**；门绿默认 master_hf；赶 ship / `--ship-hardburn` 走硬烧。

## 清单
- [x] `post_route.py` · `caption_pixel_check.py`
- [x] `final --caption-path` / CLI pixel-check
- [x] closeout 阶梯 + 测 `test_post_caption_route`
- [x] stages/post · hard-defaults · deliver · CHANGELOG 2.39.15

## 链
stages/post · hard-defaults 字幕 ship · closeout · huangdao caption-hardburn
