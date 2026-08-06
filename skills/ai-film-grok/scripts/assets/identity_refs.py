#!/usr/bin/env python3
"""Canonical identity reference resolution (M5)."""
from __future__ import annotations

from pathlib import Path

from util import read_json, sha256_file

MAX_AUTO_REFS = 3

def _root(path):
    return Path(path).expanduser().resolve()

def _file_entry(path, *, source=None, role=None):
    if path is None: return None
    p = Path(path).expanduser().resolve()
    if not p.is_file(): return None
    e = {"path": str(p), "source": source, "sha256": sha256_file(p)}
    if role: e["role"] = role
    return e

def _rel_file(root, raw):
    if not raw: return None
    p = Path(str(raw)).expanduser()
    if not p.is_absolute(): p = root / p
    return p.resolve() if p.is_file() else None

def _char_ids(shot):
    ids = []
    for key in ("cast_ids", "character_ids", "chars"):
        raw = shot.get(key)
        if isinstance(raw, list): ids.extend(str(x) for x in raw if x)
        elif isinstance(raw, str) and raw.strip(): ids.append(raw.strip())
    for key in ("cast_id", "character_id", "char_id", "speaker_id"):
        raw = shot.get(key)
        if raw: ids.append(str(raw))
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i); out.append(i)
    return out

def resolve_identity_refs(root, shot=None, *, max_refs=MAX_AUTO_REFS, include_legacy=True):
    base = _root(root)
    sh = shot if isinstance(shot, dict) else {}
    refs, seen, warnings = [], set(), []
    def _add(path, *, source, role):
        if path is None or not Path(path).is_file(): return
        key = str(Path(path).resolve())
        if key in seen: return
        entry = _file_entry(path, source=source, role=role)
        if entry:
            seen.add(key); refs.append(entry)
    media = sh.get("media") if isinstance(sh.get("media"), dict) else {}
    for key in ("identity_ref", "cast_ref", "style_ref", "reference_image"):
        p = _rel_file(base, media.get(key) or sh.get(key))
        _add(p, source=f"shot_field:{key}", role="identity" if "style" not in key else "style")
    bible = read_json(base / "style-bible.json") or {}
    chars = bible.get("characters") if isinstance(bible, dict) and isinstance(bible.get("characters"), dict) else {}
    masters = bible.get("cast_masters") if isinstance(bible, dict) and isinstance(bible.get("cast_masters"), dict) else {}
    cids = _char_ids(sh) or list(chars.keys())[:2] or list(masters.keys())[:2]
    for cid in cids:
        for pattern in (f"canonical/cast/{cid}.png", f"canonical/cast/{cid}.jpg", f"canonical/cast/{cid}_ref.png", f"canonical/cast/{cid}_face.png", f"canonical/face-lock/{cid}.png", f"canonical/face-lock/{cid}.jpg", f"face-lock/{cid}.png"):
            _add(base / pattern, source=f"canonical.cast:{cid}", role="identity")
    if isinstance(bible, dict):
        for cid in cids:
            body = chars.get(cid) if isinstance(chars.get(cid), dict) else {}
            for key in ("reference_image", "face_ref", "cast_master", "path", "face_lock"):
                raw = body.get(key) if body else None
                if isinstance(raw, dict): raw = raw.get("path") or raw.get("file")
                _add(_rel_file(base, raw), source=f"bible.characters.{cid}", role="identity")
            mraw = masters.get(cid)
            if isinstance(mraw, dict): mraw = mraw.get("path") or mraw.get("file")
            _add(_rel_file(base, mraw), source=f"bible.cast_masters.{cid}", role="identity")
    if include_legacy:
        for cid in cids:
            for pattern in (f"cast/{cid}.png", f"cast/{cid}_ref.png", f"refs/{cid}.png", f"assets/cast/{cid}.png"):
                cand = base / pattern
                if not cand.is_file(): continue
                before = len(refs)
                _add(cand, source=f"legacy_cast_dir:{cid}", role="identity")
                if len(refs) > before:
                    try: rel = str(cand.relative_to(base))
                    except ValueError: rel = str(cand)
                    warnings.append(f"LEGACY_CAST_PATH:{rel} — prefer canonical/cast or style-bible cast_masters")
    out = refs[: max(0, int(max_refs))]
    if warnings and out:
        out[0] = dict(out[0]); out[0]["identity_warnings"] = warnings[:6]
    resolve_identity_refs._last_warnings = warnings
    return out

def resolve_identity_refs_report(root, shot=None, *, max_refs=MAX_AUTO_REFS):
    refs = resolve_identity_refs(root, shot, max_refs=max_refs)
    warnings = list(getattr(resolve_identity_refs, "_last_warnings", []) or [])
    sources = [str(r.get("source") or "") for r in refs if isinstance(r, dict)]
    return {"refs": refs, "warnings": warnings, "sources": sources,
            "canonical_count": sum(1 for s in sources if s.startswith("canonical.")),
            "legacy_count": sum(1 for s in sources if s.startswith("legacy_cast_dir")), "ok": True}
