#!/usr/bin/env python3
"""Generate bgm-library/review/index.html from the catalog (no drift).

The old review page was hand-written and already drifted (it listed 2
candidates while 3 waited in pending/). This regenerates it directly from
catalog.json: every asset with status=pending_human_review becomes a card,
plus a warning block for orphan files in pending/ that are not in the
catalog. Approve/reject commands now point at the real in-repo tools
(approve_asset.py / reject_asset.py) instead of a missing `aifilm` CLI.

    python3 tools/gen_review.py            # write review/index.html
    python3 tools/gen_review.py --check     # print what would be rendered
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import load_catalog, load_gaps, LIB
from tts import gap_asset_kind, choose_tts_engine

REVIEW = os.path.join(LIB, "review", "index.html")
PENDING = os.path.join(LIB, "pending")


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    cat = load_catalog()
    A = cat["assets"]
    pending = [a for a, v in A.items() if v.get("status") == "pending_human_review"]

    # orphan detection: files in pending/ not represented as pending in catalog
    files = set(os.listdir(PENDING)) if os.path.isdir(PENDING) else set()
    represented = {v["path"].split("/")[-1] for v in A.values()
                   if v.get("path", "").startswith("pending/")}
    orphans = sorted(files - represented)

    if args.check:
        print(f"pending_human_review assets: {len(pending)}")
        for a in pending:
            print("  -", a)
        print(f"orphan pending/ files: {len(orphans)}")
        for o in orphans:
            print("  -", o)
        # TTS pipeline status
        gaps = load_gaps()
        tts_open = [g for g in gaps if gap_asset_kind(g) == "tts"]
        eng = choose_tts_engine()
        print(f"tts gaps: {len(tts_open)} · active tts engine: {eng[0] if eng else None}")
        return

    cards = []
    for aid in pending:
        a = A[aid]
        rec = a.get("recipe", {})
        t = a.get("technical", {})
        src = "../" + a["path"]
        cmd_app = (f"python3 tools/approve_asset.py --asset-id {aid} --reviewer dex "
                   f"--instrumental-confirmed --license-note \"...\"")
        cmd_rej = (f"python3 tools/reject_asset.py --asset-id {aid} --reviewer dex "
                   f"--reason \"...\"")
        meta = (f"{esc(a.get('mood',''))} · energy {a.get('energy','')} · "
                f"{esc(a.get('stem_profile',''))} · seed {a.get('seed','')}")
        tech = (f"duration {t.get('duration_sec','')}s · peak {t.get('peak','')} · "
                f"RMS {t.get('rms','')} · silence {t.get('silence_ratio','')} · "
                f"loopable {a.get('recipe',{}).get('loopable','')}")
        recipe_json = esc(json.dumps(rec, ensure_ascii=False, indent=2))
        cards.append(f"""<article>
<h2>{esc(aid)}</h2>
<p>{esc(meta)}</p>
<p>{esc(tech)}</p>
<audio controls preload="none" src="{esc(src)}"></audio>
<details><summary>标准化配方</summary><pre>{recipe_json}</pre></details>
<pre>{esc(cmd_app)}</pre>
<pre>{esc(cmd_rej)}</pre>
</article>""")

    orphan_block = ""
    if orphans:
        items = "".join(f"<li>{esc(o)}</li>" for o in orphans)
        orphan_block = (f"<article style='border-color:#a32d2d'><h2>⚠ 孤儿文件（pending/ 未入 catalog）</h2>"
                        f"<ul>{items}</ul>"
                        f"<p>这些文件不在 catalog 的 pending_human_review 中，需 ingest 或删除。</p></article>")

    # TTS (voice) pipeline status — separate lane from BGM
    gaps = load_gaps()
    tts_open = [g for g in gaps if gap_asset_kind(g) == "tts"]
    eng = choose_tts_engine()
    tts_items = "".join(
        f"<li>{esc(g.get('gap_id','')[:12])}… · {esc(g.get('mood',''))} · "
        f"{esc(g.get('text','') or g.get('prompt_hint',''))[:60]}</li>"
        for g in tts_open[:20])
    tts_block = (f"<article style='border-color:#2d6fa3'><h2>🗣 TTS 语音管线（独立车道）</h2>"
                 f"<p>活跃评估引擎：<b>{esc(eng[0] if eng else '无')}</b> · "
                 f"待路由 tts 缺口：{len(tts_open)}</p>"
                 + (f"<ul>{tts_items}</ul>" if tts_items else
                    "<p>暂无 tts 缺口。</p>") +
                 f"<p>TTS 缺口由评估引擎样本池提供服务，不经过声音生成后端，"
                 f"因此不会出现在下方 BGM 候选列表中。</p></article>")

    html = f"""<!doctype html><html lang='zh'><meta charset='utf-8'>
<title>ACE-Step BGM Review</title>
<style>body{{max-width:960px;margin:auto;font:16px system-ui;background:#111;color:#eee}}
article{{padding:18px;border-bottom:1px solid #444}}audio{{width:100%}}pre{{white-space:pre-wrap}}</style>
<h1>ACE-Step BGM 候选（{len(pending)}）</h1>
{orphan_block}
{tts_block}
{''.join(cards)}
</html>"""

    if os.path.exists(REVIEW):
        shutil.copy(REVIEW, REVIEW + ".bak")
    with open(REVIEW, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {REVIEW}: {len(pending)} candidates, {len(orphans)} orphans")


if __name__ == "__main__":
    main()
