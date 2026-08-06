# Stable Audio Open ambience candidates

Stable Audio Open 1.0 is an optional private-5090 route for text-conditioned
ambience and transition candidates. It is not a production-ready source.

## Trust boundary

- Exact model: `stabilityai/stable-audio-open-1.0`
- Exact declared license: `Stability AI Community License`
- Local model snapshot only; the render adapter receives a local `--model-root`
- The selected checkpoint and adapter are each bound by SHA-256
- Node readiness requires the separate `stable_audio_probe.py` report to match
  the configured model, license, checkpoint hash, and adapter hash
- Probe execution is serialized and cached for five minutes
- Every result remains `pending_human_review` and
  `production_eligible=false`

The formal timeline and scene-stem gates reject pending or non-production
ambience even if its path or type is renamed.

## Node configuration

Copy `stable_audio_adapter.py` and `node/stable_audio_probe.py` to the private
audio node, then configure the `AIFILM_AUDIO_NODE_AMBIENT_*` variables shown in
`config.env.example`. Hash the actual local checkpoint and deployed adapter;
never use a mutable repository name as the render source.

Installing the model, accepting its license, or running a billable/external
canary remains a separate explicit approval. A green health probe proves local
identity only, not aesthetic quality or production rights.
