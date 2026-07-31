# Wan 2.2 sound-conditioned performance research

Wan 2.2 S2V is an experimental sound-conditioned image-to-video route on the
private RTX 5090. The node presently reports the Wan S2V diffusion-model name,
the Wav2Vec audio-encoder name, and the required ComfyUI node classes. Names
from a model listing are discovery evidence only, not a content fingerprint or
a real-media canary.

## Safe readiness probe

```bash
cd skills/ai-film-grok
./scripts/runtime-python scripts/wan_s2v_probe.py
```

The probe performs only `GET /object_info`, `GET /models/diffusion_models`, and
`GET /models/audio_encoders`. It never loads a model, downloads a missing file,
submits a prompt, or touches the queue. Even when its named dependencies are
present, it reports `execution_ready=false` until a separate, bounded canary
has immutable model and audio-encoder fingerprints.

## Research boundary

- Do not run while the ComfyUI queue is occupied or free VRAM is below 24 GiB.
- Keep source image and audio hashes; verify rights for the supplied audio.
- This is not a lip-sync route and cannot replace the approved LatentSync
  review path for visible dialogue.
- Any future result needs full decode, source/output timing comparison,
  audio-video alignment review, identity/background stability review and human
  review before a pilot decision.
- No output can be auto-promoted or used as final media.
