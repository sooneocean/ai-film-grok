# VibeVoice-ASR review sidecar

`aifilm vibevoice-asr` is a local, opt-in, candidate-only audio review. It never
replaces the dialogue manifest, subtitle truth, human final review, or any
provider routing decision.

Configure an already-installed local adapter with a JSON argv template. The
adapter receives the in-workspace verified audio path and must write the
normalized transcript JSON to the requested output path:

```bash
export AIFILM_VIBEVOICE_ASR_ARGV='["/trusted/python", "/trusted/vibevoice_adapter.py", "--audio", "{audio}", "--out", "{out}"]'
aifilm vibevoice-asr probe
aifilm vibevoice-asr run --root artifacts/film --audio audio/final-mix.wav --subtitles subtitles/final.srt
```

The adapter output schema is:

```json
{"segments":[{"speaker":"nar","start":0.0,"end":1.2,"text":"台词","words":[{"word":"台词","start":0.0,"end":1.2}]}]}
```

The resulting `receipts/vibevoice-asr-review.json` binds the source checksum and
emits only candidate subtitle/timing mismatches. Treat every mismatch as a cue
to listen, not evidence that the authored subtitle is wrong. No model is
downloaded or started by `probe`; installing a model or allowing a new runtime
remains a separately scoped pilot.
