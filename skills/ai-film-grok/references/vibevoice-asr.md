# VibeVoice-ASR review sidecar

`aifilm vibevoice-asr` is a local, opt-in, candidate-only audio review. It never
replaces the dialogue manifest, subtitle truth, human final review, or any
provider routing decision.

The included `scripts/adapters/vibevoice_asr.py` is the official-model adapter.
Run it only in a Python environment where the official VibeVoice checkout and a
local ASR model directory are already installed. Configure it with a JSON argv
template; it receives the in-workspace verified audio path and writes normalized
transcript JSON to the requested output path:

```bash
export AIFILM_VIBEVOICE_ASR_ARGV='["/trusted/vibevoice-venv/bin/python", "/Users/dex/.grok/plugins/ai-film-grok/skills/ai-film-grok/scripts/adapters/vibevoice_asr.py", "--audio", "{audio}", "--out", "{out}", "--model-path", "/trusted/VibeVoice-ASR", "--device", "cuda"]'
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

The 2026-07-29 RTX 5090 canary transcribed a real 3.96-second Japanese dialogue
clip and produced a signed candidate-only receipt. It also demonstrated the
reason for the boundary: authored `なぜ、渡したメモリーカードは空だったの？`
was recognized as `なぜ、私とメモリーカードは、からだったの？`. Use this
weapon to reveal possible pronunciation, speaker, timing and subtitle problems;
never use it to silently rewrite protected dialogue.
