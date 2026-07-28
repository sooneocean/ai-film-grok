# MMAudio SFX pilot

MMAudio is an **experimental, non-commercial SFX lane** for the private RTX
5090 audio node. It is not a production default.

## License and readiness boundary

- Upstream code is MIT.
- Official pretrained checkpoints are CC BY-NC 4.0 and are restricted here to
  internal non-commercial research.
- Upstream documents Linux/Ubuntu testing, not native Windows production
  support.
- `models.sfx=true` means the pinned adapter, clean repository, offline weights,
  checkpoint fingerprint, and explicit license metadata are configured. It
  does not mean a candidate passed human listening review.
- Every generated artifact remains `pending_human_review` with
  `production_eligible=false`. Do not mix it into commercial or formal
  delivery.

## Node configuration

Use a separate Python 3.11 environment. Copy `scripts/mmaudio_adapter.py` beside
the private audio service and configure all values explicitly:

```text
AIFILM_AUDIO_NODE_SFX_MODEL=hkchengrex/MMAudio-large-44k-v2
AIFILM_AUDIO_NODE_SFX_LICENSE=CC-BY-NC-4.0
AIFILM_AUDIO_NODE_SFX_CHECKPOINT_FINGERPRINT=<64-char SHA-256>
AIFILM_MMAUDIO_REPO_COMMIT=<40-char clean git commit>
AIFILM_MMAUDIO_CHECKPOINT_SHA256=<same 64-char SHA-256>
AIFILM_MMAUDIO_VAE_SHA256=<v1-44.pth SHA-256>
AIFILM_MMAUDIO_SYNCHFORMER_SHA256=<synchformer_state_dict.pth SHA-256>
AIFILM_MMAUDIO_PYTHON=C:\aifilm-audio-node\mmaudio-venv\Scripts\python.exe
AIFILM_AUDIO_NODE_SFX_PROBE_ARGV=["C:\\aifilm-audio-node\\mmaudio-venv\\Scripts\\python.exe","C:\\aifilm-audio-node\\mmaudio_adapter.py","--repo","C:\\AI_Models\\MMAudio","--probe"]
AIFILM_AUDIO_NODE_SFX_ARGV=["C:\\aifilm-audio-node\\mmaudio-venv\\Scripts\\python.exe","C:\\aifilm-audio-node\\mmaudio_adapter.py","--repo","C:\\AI_Models\\MMAudio","--prompt","{prompt}","--duration","{duration}","--seed","{seed}","--out","{out}","--video","{video}"]
```

The adapter forces Hugging Face and Transformers offline. Install all weights
before enabling the service. Downloads must use a `.part` file, expected byte
count, checksum verification, and atomic rename. Never let the inference
process auto-download or silently update a model.

The authenticated node and its administrator-controlled environment are the
trust root; this is drift detection, not remote attestation against a malicious
node administrator. Health and every submission rerun the heavyweight probe;
every render also rechecks the clean commit and all weight hashes.

## Canary

Text-to-audio:

```bash
aifilm sfx-canary \
  --root "<film>" \
  --prompt "wooden door closes in a quiet apartment, no music, no speech" \
  --duration 8 \
  --seed 5100 \
  --noncommercial-research-ok
```

Video-conditioned:

```bash
aifilm sfx-canary \
  --root "<film>" \
  --video "<approved-silent-shot.mp4>" \
  --prompt "synchronized cloth movement and footsteps, no music, no speech" \
  --duration 8 \
  --seed 5101 \
  --noncommercial-research-ok
```

The client uploads at most 128 MiB and the node accepts at most 30 seconds. The
receipt stores hashes, model provenance, and license scope—not the prompt or
local source path.

MMAudio can produce speech-like sounds or unwanted music. Human listening must
check synchronization, intelligibility leakage, unwanted music, clipping,
scene relevance, and loop seams. Failure stays pending or is discarded; there
is no automatic production promotion.
