# film-spec health evaluation (2026-08-05)

## Verdict

**In-repo contract green for all shipped `templates/film-spec*.json` under `validate_film_spec`.**
H3 skeleton templates were incomplete (missing `director_intent` + scenes); expanded onto adult-max IRON arc keeping H3 weapon-lane metadata.

**Historical Desktop / aifilm-work roots content-stale** (retired seedance, dramatic_meaning, framing) — deferred.

**write-spec stricter than validate**: cinematic audit fail-closes incomplete creative contracts. Complete `valid_spec` + init tree passes write-spec (double-run evidence in goal scratch).

## Fixed
- `templates/film-spec.h3-primary.example.json`
- `templates/film-spec.hybrid-h3.example.json`
- `tests/test_director_intent.py` all film-spec*.json validate

## Deferred
- Desktop roots seedance / ARC_NODE_ORPHAN
- 5090 canary stubs (vo_pacing)
- Softening cinematic audit for scaffolds (intentional)

## Re-verify
```bash
PY=$($SKILL/scripts/runtime-python)
cd $SKILL && env -u PYTHONPATH $PY -m pytest tests/test_director_intent.py -q
```
