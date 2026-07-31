# SeedVR2 video restoration research weapon

SeedVR2 is registered as a research-only restoration and upscale candidate for
the private RTX 5090. The node currently exposes the four required
`ComfyUI-SeedVR2_VideoUpscaler` class types, but that proves only custom-node
code readiness. It does not prove that any advertised DiT or VAE weight exists
on disk.

## Safe readiness probe

```bash
cd skills/ai-film-grok
./scripts/runtime-python scripts/seedvr2_probe.py
```

The probe performs one read-only `GET /object_info`. It never submits a prompt,
loads a model or accepts a model download. A successful result remains
`execution_ready=false` and `weights_state=unverified` until exact on-disk
weight fingerprints are recorded separately.

## Research boundary

- No automatic download, execution, promotion or final-media use.
- Preserve source aspect ratio, frame rate and duration.
- Bind any future canary to source, DiT and VAE SHA-256 fingerprints.
- Decode the entire output and compare geometry, frame rate and duration with
  the source.
- Review temporal consistency, faces, hands and readable text for invented
  detail.
- Include a lightly degraded fixture because restoration may oversharpen or
  overgenerate material that did not require aggressive reconstruction.
- Human review is required before any pilot promotion.

The upstream SeedVR repository describes a one-step restoration model and
calls out failure risks for severe degradation, large motion and light inputs.
The linked ComfyUI implementation advertises 3B/7B, FP16/FP8/GGUF variants and
may download models on first use. This armory therefore treats model names from
the node contract as candidates, never as installed-weight evidence.

## Sources

- <https://github.com/ByteDance-Seed/SeedVR>
- <https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler>
