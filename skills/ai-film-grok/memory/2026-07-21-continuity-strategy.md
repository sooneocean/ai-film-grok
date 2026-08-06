# 記憶沉澱：首尾幀與連貫性優化策略 (Continuity Strategy)

> **觸發條件**：當執行 `/plan` 規劃分鏡，或執行 `write-spec` 生成劇本時，需嚴格遵守此策略，以解決單一場景內片段割裂感過重的問題，同時兼顧跨場景的敘事彈性。

## 1. 場景內 (Intra-scene)：強制連續 (`chain_mode: continue`)
在**同一時間與空間**的敘事段落內，相鄰鏡頭必須盡可能保持連續，避免無意義的切換。
- **設定**：預設將相鄰鏡頭的 `chain_mode` 設為 `continue`。
- **動作首尾呼應 (Match on Action)**：撰寫提示詞 (Prompt) 時，必須將動作拆解。例如：Shot 1 的 `end_pose` 是「手伸向門把」，Shot 2 的 `start_pose` 必須接續「手握住門把並轉動」。
- **首尾幀嚴格繼承**：Shot 2 的生成必須依賴 Shot 1 的 `last_frame`（透過 `extract-frame --promote-keyframe` 提取），以滿足 `continuity_chain.py` 的九項檢查（姿勢、視線、手與道具、行進方向、軸線、髮型、服裝、天氣、光線），確保字節級或視覺高度一致。

## 2. 跨場景 (Inter-scene)：果斷切換 (`chain_mode: cut`)
**劇本絕不受限於單一場地**。當敘事需要轉換空間、時間跳躍，或是進入全新的情境時，必須打破連續性鏈條。
- **設定**：果斷使用 `chain_mode: cut`（或 `hard`）。
- **重置視覺錨點**：在新場景的第一鏡，不繼承上一場景的首尾幀。重新生成一張全新的 establishing shot（環境底圖 env_plate）與人物靜幀，確保敘事能夠自由跳躍到任何新環境。

## 3. 環境與空間的錨定 (Environment Plate)
對於同一個場景內的特寫或中景鏡頭，即使構圖改變，也應利用該場景建立鏡頭（Establishing Shot）的背景作為 `env_plate`，防止背景生成時發生「空間漂移」的割裂感。
