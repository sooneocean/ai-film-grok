# Wan 2.2 Fun Control research

Wan 2.2 Fun Control is an experimental reference-image plus control-video route
for guided motion on the private RTX 5090. The live node advertises both Fun
Control conditioning nodes, the Wan 2.2 I2V pair, and the Wan 2.2 CLIP Vision
file. That is only named-dependency discovery: it is not a weight fingerprint,
workflow validation or a media canary.

## Safe readiness probe

```bash
cd skills/ai-film-grok
./scripts/runtime-python scripts/wan_fun_control_probe.py
```

The probe performs only `GET /object_info`, `GET /models/diffusion_models`, and
`GET /models/clip_vision`. It never loads a model, downloads a file, uploads a
reference/control video, submits a prompt, or modifies the queue. It always
reports `execution_ready=false` until an explicit pilot workflow and immutable
model fingerprints exist.

## Research boundary

- Require an idle queue, at least 24 GiB free VRAM and 12 GiB free RAM.
- Bind source-reference and control-video SHA-256 values and verify the rights
  to both inputs.
- Review control following, temporal consistency, identity, geometry and
  background stability on the full decoded result.
- It cannot serve as dialogue lip-sync; visible dialogue keeps the separate
  LatentSync review gate.
- No output can be auto-promoted or used as final media.
