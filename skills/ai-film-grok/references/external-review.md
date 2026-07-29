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

## Adult technical review

For a `heat_scale: max` project, pass `--sanitized` and provide a sanitized
audio file (WAV/MP3/M4A/FLAC/OGG), never an MP4/video file. A director contract
may be hash-bound in the local report but its contents are never sent to Gemini.
Use only that technical audio, subtitles, and a declared safe-frame index. The index is an in-root JSON array
or `{ "frames": [...] }`, contains at most five in-root PNG/JPEG/WebP paths,
and every frame is uploaded only when `--sanitized` was explicitly declared.
Never upload raw explicit video, character reference material, or unredacted
project documents to this sidecar.
