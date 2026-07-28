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

Large viewpoint changes are not identity-locked: the 2511 angle-change pilot
did not pass the pixel identity gate. Qwen Layered and Qwen Control remain
blocked until weights, nodes and a real pilot are verified.

The CubeyAI adult pair passed the normal motion floor once but not the meat
motion floor and regressed on an adjacent seed. It can be selected only for an
explicit experimental pilot. Production routing fails closed until a profile
passes mean motion `>=20`, identity/contact review and human approval. The K3NK
pair is retained only for experiment reproduction and is never auto-routed.

## Commands

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
```

For edit preparation, upload the source first and pass the returned remote
filename through `--input-image-name`.

## Current verified node

- API: `http://192.168.88.52:8188`
- GPU: RTX 5090, 32 GB class
- ComfyUI root: `C:\ComfyUI_windows_portable\ComfyUI`
- Default URL resolution order: explicit `--base-url`, then
  `AIFILM_COMFYUI_BASE_URL`, then the verified armory node.

Before mutations, read `/queue`. Never interrupt an unknown running prompt.
Large model installation still uses `.part` download, exact byte count,
SHA-256 verification and atomic rename before it can enter the armory.
