# Vendor pin · MiniMax-H3 h3-prompt-writing

**Do not hand-edit** files under `h3-prompt-writing/`. Re-sync from upstream.

Upstream skill: https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills/h3-prompt-writing  
HF guides (authoritative formats):

- base: https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md  
- ref: https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md  

Plugin serializer: `scripts/media/h3_official_prompt.py`  
Optimize plan: `docs/plans/2026-08-07-h3-official-prompt-optimize-todoplan.md`

Pinned for ai-film-grok official prompt dialect compiler
(`scripts/media/h3_official_prompt.py`). Only the prompt-writing skill is
vendored — not the eight style skills.

Refresh:
```bash
curl -fsSL https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/skills/h3-prompt-writing/SKILL.md \
  -o skills/ai-film-grok/references/vendor/minimax-h3/h3-prompt-writing/SKILL.md
```

Date pin: 2026-08-07 · O0 import.
