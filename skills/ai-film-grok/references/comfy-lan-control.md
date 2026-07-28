# Private ComfyUI LAN control

`comfy_lan` is an explicit local GPU lane. It never replaces `grok_primary`
silently and never routes to ComfyUI API nodes unless the operator passes the
external-provider approval flag.

## Configure

```bash
export AIFILM_COMFYUI_BASE_URL="http://192.168.88.52:8188"
```

Only `http(s)://localhost` or a literal private/loopback IP is accepted.
Credentials, URL paths, public IPs, redirects and hostnames are rejected.
Restrict Windows Firewall port `8188` to the controller machine; never expose
the server through router port forwarding.

## Read-only control

```bash
aifilm comfy probe
aifilm comfy inventory
aifilm comfy queue
```

`inventory` reads bounded system, GPU, feature, model-count and queue data. It
does not request `/object_info` for every installed node and does not print
prompt payloads.

## Run an API workflow

Export with **File → Export Workflow (API)**, then:

```bash
aifilm comfy upload --file assets/start-frame.png

aifilm comfy run-workflow \
  --workflow workflows/wan22-i2v-api.json \
  --overrides workflows/wan22-shot-overrides.json \
  --timeout 1800 \
  --receipt receipts/comfy-run.json
```

The optional overrides file is a typed node-input mapping, for example
`{"6":{"text":"camera pushes in"},"3":{"seed":42}}`. Overrides may change
existing inputs but cannot add nodes, change node classes or invent inputs.

The default gate checks every referenced node through
`/object_info/{class_type}` and rejects ComfyUI external API nodes. A workflow
that intentionally invokes an external provider requires:

```bash
--allow-external-api-nodes
```

That flag is approval for the submitted workflow only; it does not change the
global provider default.

Completion uses the matching `client_id` on `/ws`, with `/history/{prompt_id}`
as the authoritative read-back. Returned artifacts can be fetched explicitly:

```bash
aifilm comfy download \
  --filename clip.mp4 \
  --subfolder video \
  --type output \
  --out clips/clip.mp4
```

## Mutating controls

Queue mutation and model unloading require an explicit confirmation flag:

```bash
aifilm comfy cancel --prompt-id PROMPT_ID --confirm
aifilm comfy free-memory --confirm
```

`cancel` deletes only the named pending prompt. It interrupts a running prompt
only when that prompt is the sole running job, because ComfyUI `/interrupt` is
global.

## Wan 2.2 provider

The registered endpoint is `local_wan22_i2v`, owned by provider
`comfy-wan22`. The production default remains Grok. The provider uses the
pinned Python runtime, a 30-minute generation budget, input SHA-256, output
SHA-256, and installed-model read-back.

Before a film uses the lane in bulk:

1. `aifilm comfy probe` must report the intended profile ready.
2. Run one approved pilot.
3. Decode and review the returned clip.
4. Register the approved clip and retain the generation receipt.

`official --turbo` is the fast pilot lane. `adult-motion` is an explicit,
attested quality lane that currently uses the same verified official Wan 2.2
high/low experts at 20 steps. It does not auto-load renamed merged weights or
act-specific LoRAs merely because files exist. Those assets require traceable
provenance, a successful load canary and human A/B approval before promotion.
