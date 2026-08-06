# Private ComfyUI LAN control

`comfy_lan` is a verified local GPU fallback lane. It follows FRW LTX, Grok,
and a model-identified FRW Wan route in the default action chain. It never
silently bypasses those gates or routes to ComfyUI API nodes unless the
operator passes the external-provider approval flag.

## Configure

```bash
export AIFILM_COMFYUI_BASE_URL="http://127.0.0.1:18188"
export AIFILM_COMFY_BROKER_TOKEN="..." # keep this only in an owner-only secret store
```

The production route is an authenticated Broker on Windows loopback port
`8189`, reached only through `ssh -L 18188:127.0.0.1:8189`. ComfyUI itself
must listen on `127.0.0.1:8188`; do not restore LAN binding. The Broker exposes
only read paths, image upload, and registered-armory submission. It rejects
`/interrupt`, `/free`, and queue deletion, so one controller cannot globally
stop a job by accident.

Only `http(s)://localhost` or a literal private/loopback IP is accepted.
Credentials, URL paths, public IPs, redirects and hostnames are rejected.
Never expose either service through Windows Firewall or router port forwarding.

## Read-only control

```bash
aifilm comfy probe
aifilm comfy inventory
aifilm comfy capacity
aifilm comfy queue
```

`inventory` reads bounded system, GPU, feature, model-count and queue data. It
does not request `/object_info` for every installed node and does not print
prompt payloads.

`capacity` is the fail-closed admission check for a heavy workflow. Submission
requires an idle queue, at least 12 GiB free system memory and at least 24 GiB
free GPU memory. Missing telemetry also blocks submission. These floors are
checked again inside the shared `submit()` primitive, so CLI and provider
callers cannot bypass the tower. A short cross-process lock makes the capacity
read and `/prompt` submission atomic among callers on this orchestrator.
Unrelated ComfyUI UI/API clients do not share that local lock, so the node must
still remain operationally reserved during a managed bulk run. Wait for an
owned job to finish or explicitly use `free-memory --confirm` after the queue
is idle; never interrupt an unknown running prompt.

If the loopback tunnel or ComfyUI health probe fails, use the bounded recovery
path:

```bash
aifilm comfy recover --confirm
```

It performs no mutation when the local health probe is already green. If the
remote service is healthy, it repairs only the SSH tunnel. It runs the pinned
remote stop/start scripts only when both the local and remote ComfyUI probes
fail, then verifies local health again. Unknown local-port ownership, unsafe
SSH targets, loose key permissions and failed read-back stop the recovery.
The receipt never contains the SSH target, key path, command output or prompt.

### Tunnel port map (IRON · 2026-07-29)

| Local | Remote | Service | Healthy when |
|---|---|---|---|
| **18188** | **8188** | ComfyUI | `/system_stats` → 200 + Comfy JSON |
| 18790 | 8790 | lipsync / audio node | token auth (not Comfy) |

**Wrong:** `-L 18188:127.0.0.1:8189` → `{"detail":"unauthorized"}` 401.
That is **not** Comfy downtime. Kill the bad ssh and recreate
`-L 18188:127.0.0.1:8188`. Env defaults: `AIFILM_COMFY_REMOTE_PORT=8188`.
Full lesson: [`lessons-2026-07-29-comfy-tunnel-8188-not-8189.md`](lessons-2026-07-29-comfy-tunnel-8188-not-8189.md).

When another bulk owns the GPU, submit on the first idle tick — do **not**
spend the window on a second queue assert + `free-memory` before
`run-workflow` (race → `COMFY_QUEUE_BUSY`). Never cancel an unknown running
prompt without operator `go`.

For demand-driven model selection, use
[`comfy-weapon-armory.md`](comfy-weapon-armory.md). It routes only to retained
real-pilot weapons and live-checks their required model folders.

## Run an API workflow

Export with **File → Export Workflow (API)**, then:

```bash
aifilm comfy upload --file assets/start-frame.png

aifilm comfy run-workflow \
  --workflow workflows/<approved-experimental-workflow>.json \
  --overrides workflows/<approved-overrides>.json \
  --timeout 1800 \
  --receipt receipts/comfy-run.json
```

The optional overrides file is a typed node-input mapping, for example
`{"6":{"text":"camera pushes in"},"3":{"seed":42}}`. Overrides may change
existing inputs but cannot add nodes, change node classes or invent inputs.

The default gate checks every referenced node through
`/object_info/{class_type}`. Missing metadata, external API nodes and untrusted
custom-node modules are rejected; only Comfy core modules are accepted without
an override. A workflow that intentionally invokes an external provider or an
operator-reviewed custom node requires:

```bash
--allow-external-api-nodes
```

That flag is approval for the submitted workflow only; it does not change the
global provider default.

Completion uses the matching `client_id` on `/ws`, with `/history/{prompt_id}`
as the authoritative read-back. The receipt records a canonical workflow
SHA-256 without logging the workflow prompt. Returned artifacts can be fetched explicitly:

```bash
aifilm comfy download \
  --filename clip.mp4 \
  --subfolder video \
  --type output \
  --out clips/clip.mp4
```

## Mutating controls

Direct queue mutation and model unloading are unavailable through the Broker:

```bash
aifilm comfy cancel --prompt-id PROMPT_ID --confirm
aifilm comfy free-memory --confirm
```

`cancel` and `free-memory` will be rejected while the Broker is active. This is
intentional: ComfyUI `/interrupt` and `/free` are global operations.

## Retired local Wan 2.2 I2V

`local_wan22_i2v` / `comfy-wan22` and its workflow templates are retired.
They cannot be selected for pilot or production. Keep existing receipts only
for audit; current motion routing is FRW LTX 2.3 → FRW API I2V → Grok Video
1.5, with a current-film canary required for every route.
