# Comfy 5090 weapon armory

The armory turns a creative intent into a pilot-verified local ComfyUI route.
Its machine-readable truth is `registry/comfy-weapons.json`; workflow templates
live under `templates/comfy/`. No SSH private key, password, token or prompt is
stored in the registry.

## Agent routing rule

For a new still or edit request with no already-locked provider:

1. Read dispatch `weapon_route`. When it reports `status=ready`, the current
   demand is unlocked and the plugin auto-selects the named weapon. Do not ask
   the user to choose a provider again.
2. Run its concrete route command. Live model read-back is the default.
3. Use only the returned verified weapon. Do not route to a merely installed,
   unverified or blocked model.
4. Compile the workflow with `aifilm comfy prepare`; the prompt comes from a
   file so it is not exposed in shell arguments or receipts.
5. Submit with `aifilm comfy run-workflow`, then download, decode, hash and
   visually review the artifact.
6. Existing film provider locks, pilot approval, identity/style gates and bulk
   authorization still win. The armory never silently changes a locked film.

`film-spec.json` can formally lock still routing with
`"still_provider": "grok"` or select this local armory with
`"still_provider": "comfy_lan"`; `"auto"` leaves demand routing unlocked.
An explicit `image_edit` operation routes to Qwen Edit instead of being
misclassified as text-to-image.

`auto_select=true` means provider choice is automatic for an in-scope user
request. It does not make the route `advance` eligible and does not write a
Professional stage lock; generation and registration still need their normal
receipts and gates.

If live read-back fails or no verified weapon matches, fail closed and report
the blocker. `--offline` is for deterministic planning/tests, not production
generation.

## Verified intent map

| Need | Intent | Weapon | Default |
|---|---|---|---|
| Highest practical local text-to-image quality | `text-to-image`, `keyframe`, `character-still`, `poster`, `chinese-text` | `qwen-image-2512-quality` | 928x1664, 50 steps, CFG 4, Euler/simple, shift 3.1 |
| Local wardrobe/color/object edit with identity retention | `local-image-edit`, `wardrobe-edit`, `color-edit`, `identity-preserving-edit` | `qwen-image-edit-2511-local` | FP8 mixed + verified 4-step edit LoRA |
| General local I2V | `image-to-video`, `i2v`, `general-i2v` | `wan22-i2v-quality` | Official Wan 2.2 high/low pair, 20 steps |
| Adult intimacy I2V | `adult-intimacy-i2v` | `wan22-adult-intimacy-baseline` | Adult attestation required |
| Adult meat-motion pilot | `adult-meat-motion-i2v` | `wan22-adult-meat-pilot` | Experimental opt-in, pilot only, human approval required |
| Stable talking-avatar pilot | `talking-avatar-stable-pilot` | `infinite-talk-stable-pilot` | 640², 20 steps, audio scale 1; identity stable but Japanese mouth articulation still needs review |
| Expressive talking-avatar pilot | `talking-avatar-expressive-pilot` | `fantasy-talking-6step-pilot` | 640², 6-step technical canary; strong motion with known identity/color drift |

Large viewpoint changes are not identity-locked: the 2511 angle-change pilot
did not pass the pixel identity gate. Qwen Layered and Qwen Control remain
blocked until weights, nodes and a real pilot are verified.

The CubeyAI adult pair passed the normal motion floor once but not the meat
motion floor and regressed on an adjacent seed. It can be selected only for an
explicit experimental pilot. Production routing fails closed until a profile
passes mean motion `>=20`, identity/contact review and human approval. The K3NK
pair is retained only for experiment reproduction and is never auto-routed.

## Private audio weapons

The 5090 audio node is a separate private capability plane. `aifilm team snapshot`
records its live readiness alongside the visual armory.

| Need | Weapon | Availability rule | Promotion rule |
|---|---|---|---|
| Chinese narration / Japanese dialogue | Qwen3-TTS | node health reports `tts=true` | normal voice locks still apply |
| Instrumental BGM takes | ACE-Step 1.5 | node health reports `music=true` | approve into BGM library before final |
| Room tone / transitions | Stable Audio Open 1.0 | node health reports `ambient=true` with pinned provenance | candidate-only; human and license review before asset-pool promotion |
| Video-bound experimental SFX | MMAudio | node health reports `sfx=true` | internal non-commercial research only |

Stable Audio's capability id is `rtx5090-music-ambient`.
It makes the reviewable route discoverable but never authorizes a formal
timeline or final stem.

## Commands

`aifilm node status` is the only concise live readiness report for the private
5090. It reports `reachable`, `busy`, `degraded`, or `unavailable`; a registry
entry marked verified is historical evidence, never a claim that the node is
online now. `node recover --confirm` first proves that the queue is idle and
then delegates only to the allowlisted Comfy recovery route.

`aifilm weapon probe` checks registered requirements live. `weapon canary`
plans a bounded pilot by default; `--execute --confirm` is required before a
submission. `weapon promote` only creates a hash-bound, human-approved
promotion packet. It never edits the registry or changes the default provider.

```bash
# Static registry or live readiness
aifilm comfy armory
aifilm comfy armory --live

# Automatic route selection; current model folders are checked
aifilm comfy route --intent text-to-image
aifilm comfy route --intent local-image-edit --identity-lock
aifilm comfy route --intent image-to-video
aifilm comfy route --intent adult-intimacy-i2v

# Compile without submitting. The receipt stores only hashes, not the prompt.
aifilm comfy prepare \
  --intent text-to-image \
  --prompt-file prompt.txt \
  --seed 42 \
  --filename-prefix aifilm/shot01 \
  --out receipts/shot01-comfy-api.json \
  --receipt receipts/shot01-armory.json

aifilm comfy run-workflow \
  --workflow receipts/shot01-comfy-api.json \
  --receipt receipts/shot01-run.json

# Talking-avatar routes are never production-auto. Both inputs must already
# exist in ComfyUI input storage and the experimental pilot gate is explicit.
aifilm comfy prepare \
  --intent talking-avatar-stable-pilot \
  --production-stage pilot \
  --allow-experimental \
  --prompt-file performance-prompt.txt \
  --seed 20260729 \
  --input-image-name approved/hero.png \
  --input-audio-name approved/hero-ja.wav \
  --filename-prefix aifilm/talking/hero \
  --out receipts/hero-infinite-api.json \
  --receipt receipts/hero-infinite-prepare.json

aifilm comfy run-workflow \
  --workflow receipts/hero-infinite-api.json \
  --weapon-id infinite-talk-stable-pilot \
  --production-stage pilot \
  --allow-experimental \
  --receipt receipts/hero-infinite-run.json
```

For edit or talking-avatar preparation, upload the sources first and pass the
returned remote filenames through `--input-image-name` and
`--input-audio-name`. Generic custom-node approval is not used: registered
workflows permit only compiler binding changes and exact versioned Python
module identities.

## Current verified node

- API: `http://127.0.0.1:18188` through an SSH tunnel to node loopback
- GPU: RTX 5090, 32 GB class
- ComfyUI root: `C:\ComfyUI_windows_portable\ComfyUI`
- Default URL resolution order: explicit `--base-url`, then
  `AIFILM_COMFYUI_BASE_URL`, then the verified armory node.

Before mutations, read `/queue`. Never interrupt an unknown running prompt.
Large model installation still uses `.part` download, exact byte count,
SHA-256 verification and atomic rename before it can enter the armory.

## SeedVR2 research lane

`seedvr2-video-restoration-research` records the live custom-node contract
without treating advertised model choices as installed weights. Probe it with:

```bash
cd skills/ai-film-grok
./scripts/runtime-python scripts/seedvr2_probe.py
```

The command is read-only and intentionally reports `execution_ready=false`.
See `seedvr2-video-restoration.md` for the weight-fingerprint, full-decode,
source-comparison and human-review gates required before a bounded canary.

## Wan 2.2 S2V research lane

`wan22-s2v-performance-research` is a sound-conditioned I2V research route.
Its dependency probe checks only the node contract and named model listings:

```bash
cd skills/ai-film-grok
./scripts/runtime-python scripts/wan_s2v_probe.py
```

It does not make a queued prompt executable. It remains excluded from dialogue
lip-sync and final delivery until an idle-queue resource gate, model and audio
encoder fingerprints, full decode, alignment review and human review all pass.

## Wan 2.2 Dancer research lane

`wan22-dancer-performance-research` records the paired global/local Dancer
dependency contract without treating its model names as fingerprints or pilot
evidence:

```bash
cd skills/ai-film-grok
./scripts/runtime-python scripts/wan_dancer_probe.py
```

It is limited to research. A future canary requires an idle queue, 24 GiB free
VRAM, hash-bound source image/audio, exact weight fingerprints, full decode and
human review; it never substitutes for dialogue lip-sync or final media.
