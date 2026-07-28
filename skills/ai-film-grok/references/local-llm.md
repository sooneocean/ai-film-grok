# Private Local LLM Draft Adapter

`aifilm local-llm` is an opt-in, private-network adapter for draft generation.
It is deliberately **not** an I2V provider, a story-truth writer, or an approval gate.

## Required configuration

Set these only in the local shell or gitignored `config.env`:

```sh
export AIFILM_LOCAL_LLM_BASE_URL='http://192.168.88.52:1234/v1'
# Optional when LM Studio authentication is enabled:
export AIFILM_LOCAL_LLM_TOKEN='...'
```

The URL must use a numeric private/loopback IP and end in `/v1`. Public hosts,
embedded credentials, and arbitrary paths are rejected.

## Commands

```sh
aifilm local-llm probe
aifilm local-llm draft --prompt 'Draft two safe candidate shots for a courier in rain.'
```

`probe` only calls `/models`; it never loads a model. `draft` calls the fixed,
benchmark-approved `openai/gpt-oss-20b` model and returns a checksum-bound,
`candidate_only` receipt on stdout. A human must explicitly copy approved ideas
into `drama-graph.json` or another authoring artifact.

## Failure behavior

Any transport, model-list, empty-output, or timeout failure ends in an explicit
error. The existing deterministic planning path remains the fallback; this
adapter never retries through another model and never changes I2V routing.
