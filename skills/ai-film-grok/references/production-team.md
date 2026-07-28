# 精品製片劇組：總監 agent 編排

`aifilm team` 把 AI 劇組變成一份可審計的作戰表，而不是一串模糊的「多 agent」承諾。它不會自動呼叫模型、不會提交任務、更不會跨越付費或人類核准邊界。

劇組有六位各自可否決的總監：Showrunner（故事）、攝影／視覺、表演、聲音、剪輯，以及品質交付。每人有明確守護目標、必看證據，並必須指派至少一個模型 capability 或明確的本機工具。M1 適合腳本批評、提示詞／連續性分析、剪輯與解碼 QA；區網 5090 適合經過 canary 驗證的重影音、聲音或嘴型模型。兩者都不是「已可用」的假設：5090 的 capability 必須 `ready + pilot_verified`，M1 的工具也要在該片的驗收流程中留下實際證據。

先取得不花錢的能力快照，再建立作戰表：

```bash
aifilm team snapshot --out artifacts/<film>/receipts/capability-snapshot.json
aifilm team scaffold --root artifacts/<film> \
  --capabilities artifacts/<film>/receipts/capability-snapshot.json
```

編輯 `production-team.json`：將每個 `model_capability_ids` 填入快照中屬於該總監專業領域的 ID；`local_tools` 僅是操作備註，不能取代可驗證模型。此檔只是責任與能力配置，不是授權。再在每次開始新階段前驗證：

```bash
aifilm team validate \
  --plan artifacts/<film>/production-team.json \
  --capabilities artifacts/<film>/receipts/capability-snapshot.json
```

`snapshot` 會即時讀取 M1 的 QA／後期工具，以及 SSH tunnel 後的 5090 Comfy armory、音訊節點與嘴型節點；它不會生成媒體、不會花錢。驗證會拒絕未配置總監、錯誤工種領域、未知／失效／未 pilot 的模型，以及能力快照已變更的舊計畫。通過只代表「有合格的劇組配置」；故事鎖、pilot、付費生成、Picture Lock 與 Master Lock 仍由既有 Director Contract、部門 handoff 與人類核准門檻把關。
