# MMAudio SFX pilot

MMAudio is a **review-gated, non-commercial SFX lane** for the private RTX
5090 audio node. It may enrich internal non-commercial cuts after explicit
human approval, but it is not a commercial production source.

## License and readiness boundary

- Upstream code is MIT.
- Official pretrained checkpoints are CC BY-NC 4.0 and are restricted here to
  internal non-commercial research.
- Upstream documents Linux/Ubuntu testing, not native Windows production
  support.
- `models.sfx=true` means the pinned adapter, clean repository, offline weights,
  checkpoint fingerprint, and explicit license metadata are configured. It
  does not mean a candidate passed human listening review.
- Every generated artifact starts as `pending_human_review` with
  `production_eligible=false`. A reviewer may promote it only to
  `approved_noncommercial`; commercial and formal delivery remain blocked.
- A real video-conditioned 5.0-second canary passed generation, hash binding,
  full decode, 44.1 kHz stereo format and duration checks on 2026-07-29. It
  remains pending human listening and therefore is a pilot weapon, not a final
  source.
- The VibeVoice-ASR cross-check returned one silence segment and one
  Spanish-like sentence candidate. That may be ASR hallucination or
  speech-like leakage in the generated Foley; either way it blocks automatic
  approval and demonstrates why the no-speech listening attestation is
  mandatory.

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
AIFILM_MMAUDIO_RUNNER=C:\aifilm-audio-node\mmaudio_runner.py
AIFILM_AUDIO_NODE_FFMPEG=<absolute path to ffmpeg.exe>
AIFILM_AUDIO_NODE_SOX=<absolute path to sox.exe>
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

Bind the service to `127.0.0.1:8788` on Windows and reach it through an SSH
tunnel. Do not expose the bearer-authenticated HTTP service or video uploads
directly on the LAN:

```bash
ssh -fN \
  -L 127.0.0.1:18788:127.0.0.1:8788 \
  "<windows-ssh-host>"
export AIFILM_AUDIO_NODE_URL=http://127.0.0.1:18788
```

## Generate, review, and attach

Text-to-audio:

```bash
aifilm sfx-candidate generate \
  --root "<film>" \
  --prompt "wooden door closes in a quiet apartment, no music, no speech" \
  --duration 8 \
  --seed 5100 \
  --noncommercial-research-ok
```

Video-conditioned:

```bash
aifilm sfx-candidate generate \
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

MMAudio can produce speech-like sounds or unwanted music. Before listening,
run the private VibeVoice-ASR cross-screen. It binds the exact candidate WAV
hash and an ASR receipt to the pending candidate. A non-silence transcript is
only a **candidate signal**: it may be recognition hallucination, so it never
rejects or approves a take automatically. Human listening still decides.

Run `aifilm sfx-candidate screen-speech --root <film> --asset-id <asset-id>`
before approval. Human listening must check synchronization, intelligibility
leakage, unwanted music, clipping, scene relevance, and loop seams. Failure
stays pending or is discarded; there is no automatic production promotion.

After listening to the complete candidate:

```bash
aifilm sfx-candidate approve \
  --root "<film>" \
  --asset-id "<asset-id>" \
  --reviewer "<reviewer>" \
  --heard-full \
  --sync-confirmed \
  --no-speech-confirmed \
  --no-music-confirmed \
  --artifact-free-confirmed \
  --asr-speech-reviewed
```

Attach only to an internal non-commercial film. This writes
`delivery_scope=noncommercial_internal`; the timeline and stem renderers verify
the signed approval receipt again:

```bash
aifilm sfx-candidate attach \
  --root "<film>" \
  --asset-id "<asset-id>" \
  --shot-id "<shot-id>" \
  --kind foley \
  --start-offset-sec 0 \
  --duration 5 \
  --material cloth \
  --noncommercial-internal-ok
```

Use `sfx-candidate reject` for failed candidates. Never attach a pending
candidate, and never change an MMAudio film back to a commercial delivery scope.
