# Professional Director System

The director system compiles creative intent into independent, hash-bound department contracts.

Canonical truth is split by ownership: `drama-graph.json` for story and performance intent, `style-bible.json` v3 for visual departments, `audio-bible.json` for sound and music, `post-bible.json` for editorial and finishing, and `production-book.json` for dependencies, rigor, stages, approvals, and stale propagation. `film-spec.json` and Shot Packages are derived execution projections.

All lockable nodes use `draft → review → locked → stale`. A lock is valid only when the approval ledger identifies a human/user authorization and binds the exact current input hashes. Model scores remain advisory.

Department work is assigned by a read-only handoff receipt, never by an implicit assumption: `aifilm department handoff --root <film-root> --to post` exposes the exact locked visual and audio hashes that editorial may consume. If either input is draft, stale, missing, or tampered, the receipt fails and post must not start. The receipt does not lock, unlock, or rewrite any bible; it preserves each department's ownership boundary.

Professional stage order is Concept, Script, Department/Look, Shot/Animatic, Pilot, Bulk, Dailies, Selects/Rough Cut, Picture Lock, Post Locks, and Master Lock. Paid generation and external operations always stop for human approval.

The no-spend golden suite covers a 45-second 9:16 drama contract, adult Genre Pack isolation, ten injected continuity/audio/approval failures, and the final Master gate. A verified delivery still requires a real moving MP4, audio stream, visible subtitles, `ffprobe` read-back, full decoding, and a human full-film approval bound to the current final hash.
