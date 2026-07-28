# Private Semantic Index

`aifilm semantic-index` is an opt-in retrieval helper for a private
OpenAI-compatible embedding endpoint. It returns source-bound **candidates**;
it cannot edit `drama-graph.json`, select a provider, or approve any gate.

## Configure

Set these only in the local shell or gitignored `config.env`:

```sh
export AIFILM_LOCAL_EMBEDDING_BASE_URL='http://192.168.88.52:1234/v1'
# Optional if the endpoint requires it:
export AIFILM_LOCAL_EMBEDDING_TOKEN='...'
```

The endpoint must be a numeric private/loopback IP and end in `/v1`. Redirects,
public hosts, credentials embedded in the URL, non-whitelisted models, malformed
vectors, and stale sources fail closed.

## Commands

```sh
aifilm semantic-index build --root '<film>'
aifilm semantic-index query --root '<film>' --query '谁穿红夹克在雨中送包裹？'
```

`build` writes the derived, checksum-bound index to
`<film>/receipts/semantic-index.json`. It indexes only these local JSON sources:

- `drama-graph.json`
- `film-spec.json`
- `reference-analysis/shot-grammar.json`
- approved `receipts/shot-review-*.json`

Credential-like JSON keys and values are excluded. Query output includes only a
relative source path, source SHA-256, text hash, candidate text, and similarity
score; it never returns the stored vectors. If any indexed source has changed,
`query` stops and requires a rebuild rather than searching stale production data.

Use results to locate context or compare authoring intent. They are not visual
identity proof, duplicate-media proof, or human approval.
