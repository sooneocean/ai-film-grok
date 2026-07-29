# External Review Sidecar

`external-review` is an opt-in, read-only Groq/Gemini sidecar. Its JSON is
always advisory: it cannot approve a shot, alter provider routing, submit media,
or change `review-final`/delivery gates.

## Credentials and boundaries

Set `GROQ_API_KEY` and/or `GEMINI_API_KEY` only in the local process
environment. Never put either value in `config.env`, CLI arguments, reports,
receipts, or source control. Run the no-spend local check first:

```bash
"$AIFILM" external-review probe
```

The probe only checks whether the environment has a credential; it never sends
media, a prompt, a model-list request, or an inference request. Account quotas
and model availability must be checked in each provider console before a live
pilot.

## Offline pilot

Use an already completed film and compare candidate findings with a human issue
list. Do not attach the result to approval UI or delivery state until the human
review finds at least 80 percent of candidates valid.

```bash
"$AIFILM" external-review run \
  --root artifacts/<film> \
  --video artifacts/<film>/final/master.mp4 \
  --subtitles artifacts/<film>/final/subtitles.srt \
  --director-contract artifacts/<film>/director-contract.json
```

The result is `receipts/external-review.json`, bound to the local inputs by
SHA-256. Groq may produce word-timing and safe-frame candidates; Gemini may
produce cross-shot/contract candidates. Failed, rejected, rate-limited, or
unavailable providers are recorded as `unavailable` and never block delivery.

## Where It Adds Coverage

Use this sidecar only after the local media check for the same artifact has
passed. It is useful at three separate points, each with an explicit receipt
purpose:

| Purpose | Input | What it can catch | It cannot replace |
| --- | --- | --- | --- |
| `tts_rehearsal` | rendered line/stem plus VTT/SRT | missing spoken text and cue drift | voice performance approval |
| `animatic` | rendered animatic plus captions | timing and obvious safe-frame candidates | pacing/edit approval |
| `final` | verified final file plus captions/contract | cross-shot, subtitle-intent, and technical-frame candidates | `review-final`, post-audit, or full-film viewing |

Run each one deliberately; the plugin never submits it automatically. When a
credential is injected into the current process and a final has no current
`purpose: final` receipt, `aifilm next` offers the final command before the
human `review-final` step. The recommendation is advisory and disappears once
the receipt is bound to the current final SHA-256.

```bash
# Examples: each result remains candidate-only and nonblocking.
"$AIFILM" external-review run --root artifacts/<film> --video artifacts/<film>/audio/rehearsal.wav --subtitles artifacts/<film>/audio/rehearsal.srt --purpose tts_rehearsal
"$AIFILM" external-review run --root artifacts/<film> --video artifacts/<film>/animatic/master.mp4 --subtitles artifacts/<film>/animatic/subtitles.srt --purpose animatic
```

Gemini authentication uses the `x-goog-api-key` HTTP header. Never put a key in
a URL, a local config file, or an invocation copied into a receipt.

## Adult technical review

For a `heat_scale: max` project, pass `--sanitized` and provide a sanitized
audio file (WAV/MP3/M4A/FLAC/OGG), never an MP4/video file. A director contract
may be hash-bound in the local report but its contents are never sent to Gemini.
Use only that technical audio, subtitles, and a declared safe-frame index. The index is an in-root JSON array
or `{ "frames": [...] }`, contains at most five in-root PNG/JPEG/WebP paths,
and every frame is uploaded only when `--sanitized` was explicitly declared.
Never upload raw explicit video, character reference material, or unredacted
project documents to this sidecar.
