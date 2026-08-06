# H3 I2V vs FLF A/B scaffold (Phase 0)

5090 was **busy** (queue/VRAM) at ship time — this is the offline recipe.

## Inputs
- `first.png` — approved still
- `last.png` — end pose (different pose/wardrobe; never copy of first)

## Commands (when capacity ready)
```bash
ROOT="<film>"
SID=s_ab
# single-frame
aifilm h3 run --root "$ROOT" --shot-id "$SID" --mode i2v --still first.png --register --no-queue
# first-last
aifilm h3 run --root "$ROOT" --shot-id "$SID" --mode flf --still first.png --last-frame last.png --register --no-queue
```

## Metrics
- deliver endframe L1 vs last.png (lower = better land)
- mid-frame identity L1 vs first.png
- mean_absdiff
- human 30s dailies

## Exit
Write receipt `h3-flf-ab-YYYYMMDD.json` under this folder with both take shas.
