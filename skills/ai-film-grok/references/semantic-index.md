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

The endpoint must be a loopback, RFC1918, or IPv6 ULA numeric IP and end in
`/v1`. Link-local/metadata addresses, redirects, ambient HTTP(S) proxies,
public hosts, credentials embedded in the URL, non-whitelisted models,
malformed vectors, and stale sources fail closed.

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

Only an explicit allowlist of narrative fields is embedded; unknown metadata,
credential-shaped fields or values (including password/token assignments), URLs,
and absolute paths are excluded. Query output includes only a relative source
path, source SHA-256, text hash, candidate text, and similarity score; it never
returns the stored vectors. The stored candidate text must still match its
recorded SHA-256 when loaded. If any indexed source has changed during a build or query,
`query` stops and requires a rebuild rather than searching stale production data.

Use results to locate context or compare authoring intent. They are not visual
identity proof, duplicate-media proof, or human approval.
