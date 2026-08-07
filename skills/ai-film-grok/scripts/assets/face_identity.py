#!/usr/bin/env python3
"""Pixel-level face identity fingerprints for cast masters and stills.

No heavyweight ML deps: Pillow-only aHash + dHash + skin/face-region color
histogram. Good enough to catch "different person / severe face morph" between
cast master and keyframes; not a forensic biometrics system.

Receipt: ``receipts/face-identity.json``
  {
    "schema_version": 1,
    "kind": "face-identity",
    "verified": true|false,
    "enrolled": { "<char_id>": { "source", "sha256", "fingerprint", ... } },
    "checks": [ { "path", "char_id", "ok", "distance", "threshold", ... } ],
    ...
  }

post_audit reads ``verified``; use ``aifilm face-identity audit`` before final.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from util import sha256_file as _sha256_file, soft_json
from util import utc_now

RECEIPT_NAME = "face-identity.json"
SCHEMA_VERSION = 1

# Hamming distance on 64-bit aHash/dHash (0=identical, 64=opposite).
# After Gaussian blur, same-person pose/light variance often lands ~8–20;
# different person / env plate usually >> 24 or hist blows up.
DEFAULT_AHASH_MAX = 22
DEFAULT_DHASH_MAX = 24
# Histogram L1 distance after L1-normalize (0..2); face-region only
DEFAULT_HIST_MAX = 0.72


def _open_rgb(path: Path):
    from PIL import Image

    img = Image.open(path).convert("RGB")
    return img


def face_region_box(width: int, height: int) -> tuple[int, int, int, int]:
    """Heuristic face box for 9:16 portraits and mid shots.

    Upper-center band where cast masters and MCU hero stills put the face.
    """
    # Horizontal: center 70%
    x0 = int(width * 0.15)
    x1 = int(width * 0.85)
    # Vertical: top 12% to 52% for full-body-ish; for CU face fills more —
    # use top 8%–58% which still works for MCU
    y0 = int(height * 0.08)
    y1 = int(height * 0.58)
    if y1 <= y0 + 8:
        y0, y1 = 0, height // 2
    if x1 <= x0 + 8:
        x0, x1 = 0, width
    return x0, y0, x1, y1


def _pixels_gray(img, size: tuple[int, int]) -> list[int]:
    from PIL import Image

    small = img.convert("L").resize(size, Image.Resampling.LANCZOS)
    # Pillow 10+: getdata deprecated → prefer tobytes path
    raw = small.tobytes()
    return list(raw)


def _ahash_bits(img, hash_size: int = 8) -> int:
    """Average hash → 64-bit int."""
    pixels = _pixels_gray(img, (hash_size, hash_size))
    avg = sum(pixels) / max(len(pixels), 1)
    bits = 0
    for i, p in enumerate(pixels):
        if p >= avg:
            bits |= 1 << i
    return bits


def _dhash_bits(img, hash_size: int = 8) -> int:
    """Difference hash → 64-bit int."""
    pixels = _pixels_gray(img, (hash_size + 1, hash_size))
    bits = 0
    bit = 0
    for row in range(hash_size):
        row_start = row * (hash_size + 1)
        for col in range(hash_size):
            left = pixels[row_start + col]
            right = pixels[row_start + col + 1]
            if left > right:
                bits |= 1 << bit
            bit += 1
    return bits


def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _color_hist(img, bins: int = 8) -> list[float]:
    """Normalized RGB histogram (3 * bins)."""
    from PIL import Image

    small = img.resize((64, 64), Image.Resampling.BILINEAR)
    hist = small.histogram()  # 256*3
    # collapse each channel to `bins`
    out: list[float] = []
    for ch in range(3):
        base = ch * 256
        step = 256 // bins
        for i in range(bins):
            s = sum(hist[base + i * step : base + (i + 1) * step])
            out.append(float(s))
    total = sum(out) or 1.0
    return [v / total for v in out]


def _hist_l1(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    return sum(abs(a[i] - b[i]) for i in range(n))


def compute_fingerprint(path: Path, *, use_face_region: bool = True) -> dict[str, Any]:
    """Compute face-region fingerprint for one image.

    Blur before hash so micro-expression / neon grade shifts do not dominate;
    color hist still catches gross identity / wardrobe-head swaps.
    """
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    from PIL import ImageFilter

    img = _open_rgb(path)
    w, h = img.size
    box = face_region_box(w, h) if use_face_region else (0, 0, w, h)
    face = img.crop(box)
    # Strong blur → structure/identity, not pore/edge noise
    face_blur = face.filter(ImageFilter.GaussianBlur(radius=2.5))
    ahash = _ahash_bits(face_blur)
    dhash = _dhash_bits(face_blur)
    hist = _color_hist(face_blur)
    # Second crop (tighter forehead–chin) — keep best match path in compare via dual hashes
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    tight = (
        x0 + int(bw * 0.12),
        y0 + int(bh * 0.10),
        x1 - int(bw * 0.12),
        y1 - int(bh * 0.15),
    )
    face2 = img.crop(tight).filter(ImageFilter.GaussianBlur(radius=2.5))
    ahash2 = _ahash_bits(face2)
    dhash2 = _dhash_bits(face2)
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "width": w,
        "height": h,
        "face_box": list(box),
        "ahash": ahash,
        "dhash": dhash,
        "ahash_alt": ahash2,
        "dhash_alt": dhash2,
        "ahash_hex": f"{ahash:016x}",
        "dhash_hex": f"{dhash:016x}",
        "hist": hist,
        "algorithm": "ahash+dhash+rgbhist@face-region+blur",
        "algorithm_version": 2,
    }


def compare_fingerprints(
    enrolled: dict[str, Any],
    probe: dict[str, Any],
    *,
    ahash_max: int = DEFAULT_AHASH_MAX,
    dhash_max: int = DEFAULT_DHASH_MAX,
    hist_max: float = DEFAULT_HIST_MAX,
) -> dict[str, Any]:
    """Compare probe to enrolled cast fingerprint."""
    # Min distance across primary + alt face crops (pose-tolerant)
    ah_candidates = [
        _hamming(int(enrolled["ahash"]), int(probe["ahash"])),
    ]
    dh_candidates = [
        _hamming(int(enrolled["dhash"]), int(probe["dhash"])),
    ]
    if enrolled.get("ahash_alt") is not None and probe.get("ahash_alt") is not None:
        ah_candidates.append(_hamming(int(enrolled["ahash_alt"]), int(probe["ahash_alt"])))
        ah_candidates.append(_hamming(int(enrolled["ahash"]), int(probe["ahash_alt"])))
        ah_candidates.append(_hamming(int(enrolled["ahash_alt"]), int(probe["ahash"])))
    if enrolled.get("dhash_alt") is not None and probe.get("dhash_alt") is not None:
        dh_candidates.append(_hamming(int(enrolled["dhash_alt"]), int(probe["dhash_alt"])))
        dh_candidates.append(_hamming(int(enrolled["dhash"]), int(probe["dhash_alt"])))
        dh_candidates.append(_hamming(int(enrolled["dhash_alt"]), int(probe["dhash"])))
    ah = min(ah_candidates)
    dh = min(dh_candidates)
    hist = _hist_l1(list(enrolled.get("hist") or []), list(probe.get("hist") or []))
    # Normalized score
    score = (ah / max(ahash_max, 1)) + (dh / max(dhash_max, 1)) + (hist / max(hist_max, 1e-6))
    ahash_ok = ah <= ahash_max
    dhash_ok = dh <= dhash_max
    hist_ok = hist <= hist_max
    channels_ok = sum([ahash_ok, dhash_ok, hist_ok])
    # Pass: hist must be reasonable (not env plate vs face) AND at least one structure hash ok.
    # score is advisory; extreme score (>5) still fails (total garbage match).
    ok = hist_ok and (ahash_ok or dhash_ok) and score <= 5.0
    # Same file always pass
    if enrolled.get("sha256") and enrolled.get("sha256") == probe.get("sha256"):
        ok = True
        score = 0.0
    return {
        "ok": ok,
        "ahash_distance": ah,
        "dhash_distance": dh,
        "hist_distance": round(hist, 4),
        "score": round(score, 4),
        "channels_ok": channels_ok,
        "ahash_ok": ahash_ok,
        "dhash_ok": dhash_ok,
        "hist_ok": hist_ok,
        "thresholds": {
            "ahash_max": ahash_max,
            "dhash_max": dhash_max,
            "hist_max": hist_max,
        },
    }


def load_receipt(root: Path) -> dict[str, Any]:
    path = Path(root).expanduser().resolve() / "receipts" / RECEIPT_NAME
    if not path.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "face-identity",
            "verified": False,
            "enrolled": {},
            "checks": [],
        }
    data = soft_json(path)
    if not data:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "face-identity",
            "verified": False,
            "enrolled": {},
            "checks": [],
        }
    data.setdefault("enrolled", {})
    data.setdefault("checks", [])
    data.setdefault("verified", False)
    return data


def save_receipt(root: Path, data: dict[str, Any]) -> Path:
    root = Path(root).expanduser().resolve()
    path = root / "receipts" / RECEIPT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    data["schema_version"] = SCHEMA_VERSION
    data["kind"] = "face-identity"
    data["updated_at"] = utc_now()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def enroll(
    root: Path,
    char_id: str,
    source: Path,
    *,
    label: str = "",
    append: bool = True,
) -> dict[str, Any]:
    """Enroll cast master (or face-lock plate) as identity anchor.

    Multiple anchors per char_id are kept (append=True): cast master + face-lock
    crops + lookbook stills. Verify uses the *best* matching anchor.
    """
    root = Path(root).expanduser().resolve()
    source = Path(source).expanduser().resolve()
    fp = compute_fingerprint(source)
    receipt = load_receipt(root)
    enrolled = receipt.get("enrolled") if isinstance(receipt.get("enrolled"), dict) else {}
    entry = enrolled.get(str(char_id)) if isinstance(enrolled.get(str(char_id)), dict) else {}
    anchors = list(entry.get("anchors") or []) if append else []
    # de-dupe by sha256
    anchors = [a for a in anchors if isinstance(a, dict) and a.get("sha256") != fp["sha256"]]
    anchors.append(
        {
            "source": str(source),
            "relative": _rel_to_root(root, source),
            "sha256": fp["sha256"],
            "fingerprint": fp,
            "enrolled_at": utc_now(),
        }
    )
    # primary = first / cast-master preferred
    primary = anchors[0]
    enrolled[str(char_id)] = {
        "char_id": str(char_id),
        "label": label or entry.get("label") or str(char_id),
        "source": primary["source"],
        "relative": primary.get("relative"),
        "sha256": primary["sha256"],
        "fingerprint": primary["fingerprint"],  # legacy single-fp field
        "anchors": anchors,
        "n_anchors": len(anchors),
        "enrolled_at": utc_now(),
    }
    receipt["enrolled"] = enrolled
    receipt["verified"] = False
    receipt["last_action"] = "enroll"
    path = save_receipt(root, receipt)
    return {
        "ok": True,
        "char_id": char_id,
        "source": str(source),
        "n_anchors": len(anchors),
        "receipt": str(path),
        "fingerprint": fp,
    }


def verify_image(
    root: Path,
    image: Path,
    char_id: str,
    *,
    ahash_max: int = DEFAULT_AHASH_MAX,
    dhash_max: int = DEFAULT_DHASH_MAX,
    hist_max: float = DEFAULT_HIST_MAX,
    record: bool = True,
) -> dict[str, Any]:
    """Verify one still against enrolled cast."""
    root = Path(root).expanduser().resolve()
    image = Path(image).expanduser().resolve()
    receipt = load_receipt(root)
    enrolled_map = receipt.get("enrolled") if isinstance(receipt.get("enrolled"), dict) else {}
    entry = enrolled_map.get(str(char_id))
    anchors = []
    if isinstance(entry, dict):
        if isinstance(entry.get("anchors"), list) and entry["anchors"]:
            anchors = [a for a in entry["anchors"] if isinstance(a, dict) and a.get("fingerprint")]
        elif isinstance(entry.get("fingerprint"), dict):
            anchors = [{"source": entry.get("source"), "fingerprint": entry["fingerprint"]}]
    if not anchors:
        return {
            "ok": False,
            "error": f"char_id {char_id!r} not enrolled — run face-identity enroll",
            "char_id": char_id,
            "path": str(image),
        }
    probe = compute_fingerprint(image)
    best: dict[str, Any] | None = None
    best_src = None
    for anc in anchors:
        cmp_ = compare_fingerprints(
            anc["fingerprint"],
            probe,
            ahash_max=ahash_max,
            dhash_max=dhash_max,
            hist_max=hist_max,
        )
        # NOTE: score can be 0.0 — never use `x or 99` (0 is falsy)
        sc = float(cmp_["score"]) if cmp_.get("score") is not None else 99.0
        best_sc = (
            float(best["score"]) if best is not None and best.get("score") is not None else 99.0
        )
        if best is None or sc < best_sc:
            best = cmp_
            best_src = anc.get("source")
    assert best is not None
    result = {
        "ok": bool(best["ok"]),
        "char_id": char_id,
        "path": str(image),
        "relative": _rel_to_root(root, image),
        "enrolled_source": best_src or entry.get("source"),
        "n_anchors_tried": len(anchors),
        **best,
        "at": utc_now(),
    }
    if record:
        checks = list(receipt.get("checks") or [])
        # replace same path+char
        checks = [
            c
            for c in checks
            if not (
                isinstance(c, dict) and c.get("path") == str(image) and c.get("char_id") == char_id
            )
        ]
        checks.append(result)
        receipt["checks"] = checks[-200:]  # cap
        receipt["last_action"] = "verify"
        # verified only if all recent unique paths ok — leave to audit
        save_receipt(root, receipt)
    return result


def enroll_from_bible(root: Path) -> dict[str, Any]:
    """Enroll every cast_masters entry + face-lock crops on disk."""
    root = Path(root).expanduser().resolve()
    bible_path = root / "style-bible.json"
    if not bible_path.is_file():
        return {"ok": False, "error": "style-bible.json missing", "enrolled": []}
    bible = soft_json(bible_path)
    cast = bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
    done = []
    errors = []
    for char_id, rel in cast.items():
        if not rel:
            continue
        path = Path(str(rel))
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            # try basename under canonical/cast
            alt = root / "canonical" / "cast" / Path(str(rel)).name
            path = alt if alt.is_file() else path
        if not path.is_file():
            errors.append({"char_id": char_id, "error": f"missing {rel}"})
            continue
        r = enroll(root, str(char_id), path, label=str(char_id), append=True)
        done.append({"char_id": char_id, "source": r["source"]})
        # auto face-lock crops: {char_id}-face-lock-*.png or face-lock-*.png for hero
        cast_dir = root / "canonical" / "cast"
        if cast_dir.is_dir():
            patterns = [
                f"{char_id}-face-lock-*.png",
                f"{char_id}-face-lock-*.jpg",
                "face-lock-*.png" if char_id in {"hero", "lushiran"} else "",
            ]
            for pat in patterns:
                if not pat:
                    continue
                for crop in sorted(cast_dir.glob(pat)):
                    enroll(root, str(char_id), crop, label=f"{char_id}:{crop.stem}", append=True)
                    done.append({"char_id": char_id, "source": str(crop), "kind": "face-lock"})
    return {"ok": not errors, "enrolled": done, "errors": errors}


def audit_keyframes(
    root: Path,
    *,
    char_id: str | None = None,
    strict: bool = False,
    ahash_max: int = DEFAULT_AHASH_MAX,
    dhash_max: int = DEFAULT_DHASH_MAX,
    hist_max: float = DEFAULT_HIST_MAX,
) -> dict[str, Any]:
    """Enroll from bible if needed, verify keyframes/, set verified flag.

    Mapping heuristic: if char_id given, all keyframes vs that cast; else try
    cast_locks / dsl from film-spec per shot id when available, fallback first enrolled.
    """
    root = Path(root).expanduser().resolve()
    receipt = load_receipt(root)
    if not receipt.get("enrolled"):
        enroll_from_bible(root)
        receipt = load_receipt(root)
    enrolled = receipt.get("enrolled") if isinstance(receipt.get("enrolled"), dict) else {}
    if not enrolled:
        return {
            "ok": False,
            "verified": False,
            "error": "no enrolled cast — enroll cast masters first",
            "checks": [],
        }

    # Build shot → cast map from film-spec if present
    shot_cast: dict[str, str] = {}
    spec_path = root / "film-spec.json"
    if spec_path.is_file():
        try:
            spec = soft_json(spec_path)
            for sc in spec.get("scenes") or []:
                if not isinstance(sc, dict):
                    continue
                for sh in sc.get("shots") or []:
                    if not isinstance(sh, dict):
                        continue
                    sid = str(sh.get("id") or "")
                    dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
                    cast = dsl.get("cast") if isinstance(dsl.get("cast"), list) else []
                    # first human cast with enrollment
                    for c in cast:
                        if str(c) in enrolled:
                            shot_cast[sid] = str(c)
                            break
                    if sid and sid not in shot_cast and char_id and char_id in enrolled:
                        shot_cast[sid] = char_id
        except Exception:  # noqa: BLE001
            pass

    default_char = char_id if char_id and char_id in enrolled else next(iter(enrolled.keys()))
    kf_dir = root / "keyframes"
    images: list[Path] = []
    if kf_dir.is_dir():
        for p in sorted(kf_dir.iterdir()):
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and not p.name.startswith(
                ("_", ".")
            ):
                # skip seed/last dumps for primary audit? include main stem only
                if "-seed" in p.stem or p.stem.startswith("_last"):
                    continue
                images.append(p)

    checks: list[dict[str, Any]] = []
    for img in images:
        stem = img.stem
        cid = shot_cast.get(stem) or default_char
        # env shots with no cast in map still checked against default — skip pure env names
        if "env" in stem.lower() and stem not in shot_cast:
            continue
        # if film-spec says empty cast, skip
        # Skip when film-spec maps empty cast explicitly.
        if spec_path.is_file() and stem not in shot_cast and _shot_empty_cast(root, stem):
            continue
        r = verify_image(
            root,
            img,
            cid,
            ahash_max=ahash_max,
            dhash_max=dhash_max,
            hist_max=hist_max,
            record=False,
        )
        checks.append(r)

    fails = [c for c in checks if not c.get("ok")]
    verified = bool(checks) and not fails and bool(enrolled)
    if not checks and enrolled:
        # enrolled only, no keyframes yet — partial verified for enroll stage
        verified = True

    receipt = load_receipt(root)
    receipt["checks"] = checks
    receipt["verified"] = verified
    receipt["last_action"] = "audit"
    receipt["audit"] = {
        "at": utc_now(),
        "n_checks": len(checks),
        "n_fail": len(fails),
        "n_enrolled": len(enrolled),
        "strict": strict,
        "fail_paths": [c.get("path") for c in fails],
    }
    path = save_receipt(root, receipt)

    out = {
        "ok": verified if strict else (len(fails) == 0 or not strict),
        "verified": verified,
        "receipt": str(path),
        "n_enrolled": len(enrolled),
        "n_checks": len(checks),
        "n_fail": len(fails),
        "fails": fails,
        "checks": checks,
    }
    # Non-strict audits record evidence without blocking the pipeline; strict
    # audits use the verified result as their exit status.
    out["ok"] = verified if strict else True
    return out


def _shot_empty_cast(root: Path, shot_id: str) -> bool:
    spec_path = root / "film-spec.json"
    if not spec_path.is_file():
        return False
    try:
        spec = soft_json(spec_path)
        for sc in spec.get("scenes") or []:
            for sh in sc.get("shots") or []:
                if str(sh.get("id")) != shot_id:
                    continue
                dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
                cast = dsl.get("cast")
                if isinstance(cast, list) and len(cast) == 0:
                    return True
                role = str(sh.get("shot_role") or "").lower()
                if role == "env":
                    return True
                return False
    except Exception:  # noqa: BLE001
        return False
    return False


def post_audit_face_status(root: Path) -> dict[str, Any]:
    """Used by post_audit: return warning/hard items about face identity."""
    root = Path(root).expanduser().resolve()
    warnings: list[dict[str, str]] = []
    hard: list[dict[str, str]] = []
    bible_path = root / "style-bible.json"
    cast_masters: dict[str, Any] = {}
    if bible_path.is_file():
        try:
            bible = soft_json(bible_path)
            cm = bible.get("cast_masters")
            if isinstance(cm, dict):
                cast_masters = cm
        except Exception:  # noqa: BLE001
            pass
    if not cast_masters:
        return {"warnings": warnings, "hard": hard, "verified": None}

    receipt_path = root / "receipts" / RECEIPT_NAME
    if not receipt_path.is_file():
        warnings.append(
            {
                "code": "FACE_IDENTITY_DRIFT",
                "message": (
                    f"cast_masters has {len(cast_masters)} character(s) but no "
                    f"receipts/{RECEIPT_NAME} — run: aifilm face-identity enroll-bible "
                    f"&& aifilm face-identity audit --root …"
                ),
            }
        )
        return {"warnings": warnings, "hard": hard, "verified": False}

    receipt = load_receipt(root)
    enrolled = receipt.get("enrolled") if isinstance(receipt.get("enrolled"), dict) else {}
    verified = bool(receipt.get("verified"))
    if not enrolled:
        warnings.append(
            {
                "code": "FACE_IDENTITY_DRIFT",
                "message": "face-identity.json has no enrolled casts — run face-identity enroll-bible",
            }
        )
    elif not verified:
        n_fail = int((receipt.get("audit") or {}).get("n_fail") or 0)
        warnings.append(
            {
                "code": "FACE_IDENTITY_DRIFT",
                "message": (
                    "face-identity not verified"
                    + (f" ({n_fail} keyframe(s) failed pixel match)" if n_fail else "")
                    + " — run aifilm face-identity audit --root …"
                ),
            }
        )
    # enrolled missing some cast_masters
    missing = [c for c in cast_masters if c not in enrolled and c != "hero"]
    # if hero is only alias skip
    for c in cast_masters:
        if c not in enrolled:
            # allow hero alias of another
            if c == "hero" and any(k != "hero" for k in enrolled):
                continue
            if c not in enrolled:
                missing.append(c)
    missing = sorted(set(missing))
    if missing:
        warnings.append(
            {
                "code": "FACE_IDENTITY_ENROLL_GAP",
                "message": f"cast_masters not enrolled: {', '.join(missing)}",
            }
        )
    return {
        "warnings": warnings,
        "hard": hard,
        "verified": verified,
        "n_enrolled": len(enrolled),
        "n_fail": int((receipt.get("audit") or {}).get("n_fail") or 0),
    }


def _rel_to_root(root: Path, path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except Exception:  # noqa: BLE001
        return str(path)
