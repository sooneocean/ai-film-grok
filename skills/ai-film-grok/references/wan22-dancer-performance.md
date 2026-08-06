# Wan 2.2 Dancer performance research

Wan 2.2 Dancer is an experimental audio-conditioned choreography route on the
private RTX 5090. The live node currently advertises the global and local
Dancer diffusion-model names, the Wav2Vec audio-encoder name, and the required
ComfyUI classes. That proves discovery only: model names are not fingerprints,
and no media canary has yet been accepted.

## Safe readiness probe

```bash
cd skills/ai-film-grok
./scripts/runtime-python scripts/wan_dancer_probe.py
```

The probe performs only `GET /object_info`, `GET /models/diffusion_models`, and
`GET /models/audio_encoders`. It never loads a model, downloads a file, submits
a prompt, or changes the ComfyUI queue. Its positive result remains
`execution_ready=false` pending exact model fingerprints and a separate
bounded canary.

## Research boundary

- Do not run while the queue is non-idle or free VRAM is below 24 GiB.
- Bind the source image and audio hashes; verify source-audio rights.
- Start any future canary at the node-advertised 149-frame profile and measure
  the resulting duration rather than assuming it.
- This is not a dialogue lip-sync replacement. Visible speech still uses the
  approved LatentSync review path.
- Require full decode plus rhythm/motion, identity, background and anatomy
  stability review before a human pilot decision.
- No output can be auto-promoted or used as final media.
