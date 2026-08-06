# Lessons · 2026-07-21 · BGM 听腻 / multi-style

> **已晋升**：BGM multi-style 规则已整合进稳定文档 [bgm-generation.md](bgm-generation.md)。
> 此 lesson 保留为踩坑历史记录。

**层**：voice·post · **P**：可复现默认 + 显式换 take；不假静音

## 现象

程序 rnb 换 seed 仍像同一首歌 → 音色族未变。

## 规则

1. seed 映射 **style 族**（velvet/pulse/ambient/lofi/glitter），不只重排和声  
2. 曲库多文件 → `seed % pool` 轮换  
3. AI 音乐走 `AIFILM_MUSIC_ARGV`（失败默回落 procedural）  
4. 色气仍默认 rnb mood；dark 仅恐怖  

## 入口

[bgm-generation.md](bgm-generation.md) · `make_sfx_bed.rnb_bgm` · `resolve_music_template(seed=)`
