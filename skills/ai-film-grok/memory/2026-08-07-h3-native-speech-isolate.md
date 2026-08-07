# Memory · 2026-08-07 · H3 原声轻处理（修正版）

> **用户**：要原声口型，怪声只留关键语音。  
> **修正**：狠 `agate`+双 `arnndn` 会毁轨 → **默认轻处理**。

## 默认滤镜
`highpass=f=80, lowpass=f=12000, afftdn=nr=12:nf=-25, adeclick, loudnorm=I=-16:TP=-1.5:LRA=11`

## 禁
- 默认 agate / 双 arnndn  
- TTS 叠原声（XOR）  

## 交付
优先 `film_native_stable.mp4`；狠 gate 版标 BROKEN。  
见 [no-midframe-composite-flf-audio](2026-08-07-no-midframe-composite-flf-audio-iron.md)
