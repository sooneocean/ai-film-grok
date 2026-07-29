# Serial Narrative Workflow

`serial` is optional. Set `film-spec.json.serial` to `{ "enabled": true, "series_id": "..." }`, then keep one `series-bible.json` beside it. It records adult and consent confirmation, original-or-licensed character provenance, adult character confirmation, relationship/motivation/contrast, season arc, release cadence, and the episode ledger. It is planning metadata only: it never publishes or schedules a platform post.

Each serial episode needs `episode_contract`: an evidence-backed opening promise in the first `min(30 seconds, episode duration)`, one primary event and beat-level `event_relation`, a next-episode question/payoff, marketing copy tied to actual conflict and relationship, and a novelty signature. A matching older signature creates a human-review warning, not a claim about originality or infringement.

Run `aifilm serial validate --root <film>` before concept or script lock. Those locks reject incomplete serial contracts and write `receipts/serial-quality.json`; `director check` reports the same blockers. This contract does not weaken Adult MAX, visual identity, pilot, or delivery gates.
