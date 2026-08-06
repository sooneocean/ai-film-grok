# Final 渲染 checkpoint / resume

`aifilm final --resume` 会读取：

```text
<film-root>/receipts/checkpoints/final-render.json
```

checkpoint 只保存单镜 `stretch/lipsync` 中间产物，签名绑定：输入 clip 的路径与文件 fingerprint、目标时长、画布尺寸、fps、裁切范围和 lipsync 模式。签名不匹配或输出文件不存在时，该镜会重新处理。

```bash
aifilm final --root <film-root> --resume
aifilm final --root <film-root> --force
```

- `--resume` 只跳过签名一致且文件可读的中间产物。
- `--force` 清空 checkpoint 后重新处理。
- checkpoint 不是 manifest、quality receipt、pilot approval 或 final delivery 证据；最终仍必须经过 preflight、inventory、技术 QA、`review-final` 和人工完整观看。
- checkpoint 写入采用原子替换；中途失败的镜头不会写入完成记录。
