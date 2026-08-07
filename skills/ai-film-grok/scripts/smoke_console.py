#!/usr/bin/env python3
"""Live smoke for the localhost review console via the real `aifilm` CLI.

Repo-relative: resolves the git root from this file's location so it works from
any checkout (dev tree or plugin mirror). Self-contained stdlib harness — it
spawns `scripts/aifilm review-ui serve` (→ post.review_ui through the shim) on a
real loopback socket, then drives the full flow with real HTTP requests:

  console page (+ served-UI feature-surface parity), gates panel, asset listing
  (+ bad kind → 400), console-state (+ recent_selections), onboarding,
  hash-bound select (200 then stale 409), blocking gate (403), cross-origin
  (403), bad token (401), media-lib path-escape (404).

  PLUS a real-operation UI-feature e2e that mirrors exactly what console.html
  does in a browser:
    • served-UI artifact parity (film-studio tabs / accent / 6 material tabs /
      dashboard+picker functions present in the bytes the live server returns)
    • dashboard parallel-load shape parity — every kind's items carry the fields
      cardHtml() parses, so a backend field rename can't silently break the UI
    • selection→state cycle for voice / character / prop (mirrors pick()):
      capture ledger_revision → POST select → assert revision bumped → assert
      console-state reflects the selection
    • production-binding flow: locking a character writes back into the canonical
      assets.json (proves the console drives the pipeline, not just a ledger)
    • write-path hardening: bad kind → 400, unknown asset → 400

Exits non-zero on the first assertion failure so it doubles as a local
regression gate (see `make smoke-console`).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlparse

# Repo-relative resolution: this file lives at
#   <root>/skills/ai-film-grok/scripts/smoke_console.py
# so three parents up is the git root.
ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = ROOT / "skills" / "ai-film-grok" / "scripts" / "aifilm"


def setup_film_root() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="aifilm-console-smoke-"))
    (tmp / "receipts").mkdir()
    (tmp / "drama-graph.json").write_text('{"scenes": []}', encoding="utf-8")
    # adult + heat_scale max => gates green (blocking=False)
    (tmp / "film-spec.json").write_text(
        json.dumps(
        {
            "genre": "adult",
            "heat_scale": "max",
            "cast_voices": {"f": "zh-CN-XiaoyiNeural"},
        }
        ),
        encoding="utf-8",
    )
    # Self-contained asset registry so the UI-feature e2e can drive a real
    # character-lock + prop-select cycle without depending on the global
    # pipeline state. Keeps the live gate deterministic across machines.
    (tmp / "assets.json").write_text(
        json.dumps(
            {
                "characters": [{"id": "c1", "name": "Lena", "role": "lead"}],
                "bible": {"props": {"p1": "古铜钥匙"}},
            }
        ),
        encoding="utf-8",
    )
    return tmp


def start_server(film_root: Path):
    proc = subprocess.Popen(
        [str(LAUNCHER), "review-ui", "serve", "--root", str(film_root), "--port", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # Read until we get the JSON line printed by serve()
    for _ in range(100):
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"server exited early: {proc.stderr.read()[-2000:]}"
                )
            continue
        line = line.strip()
        if line.startswith("{"):
            info = json.loads(line)
            if info.get("ok"):
                return proc, info
    raise RuntimeError("never received server URL JSON")


def req(conn, method, path, *, token=None, body=None, origin=None):
    c = HTTPConnection("127.0.0.1", conn.port)
    headers = {}
    if token:
        headers["X-Review-Token"] = token
    if body is not None:
        headers.update(
            {
                "Content-Type": "application/json",
                "Origin": origin or f"http://127.0.0.1:{conn.port}",
            }
        )
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    resp = c.getresponse()
    payload = resp.read()
    c.close()
    if resp.status >= 400:
        print(f"    >> {method} {path} -> {resp.status}: {payload.decode('utf-8', 'ignore')[:200]}")
    return resp.status, payload


def main() -> int:
    film_root = setup_film_root()
    print(f"[smoke] film root: {film_root}")
    proc, info = start_server(film_root)
    parsed = urlparse(info["url"])
    port = parsed.port
    token = info["token"]
    print(f"[smoke] server up: {info['url']}")
    failures = []

    def check(name, cond, extra=""):
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {name} {extra}")
        if not cond:
            failures.append(name)

    try:
        conn = HTTPConnection("127.0.0.1", port)
        # 1) console page (B1 single shell + review tab)
        st, body = req(conn, "GET", "/console", token=token)
        text = body.decode("utf-8") if body else ""
        check(
            "GET /console",
            st == 200 and "选素材" in text and 'data-tab="review"' in text,
            f"status={st}",
        )
        st, body = req(conn, "GET", "/review", token=token)
        check(
            "GET /review",
            st == 200 and "审核控制台" in body.decode("utf-8", "ignore"),
            f"status={st}",
        )
        # 2) gates panel
        st, body = req(conn, "GET", "/api/gates", token=token)
        d = json.loads(body) if st == 200 else {}
        check("GET /api/gates", st == 200 and d.get("kind") == "gate-panel", f"status={st}")
        # 3) assets listing
        st, body = req(conn, "GET", "/api/assets?kind=character", token=token)
        d = json.loads(body) if st == 200 else {}
        check("GET /api/assets?kind=character", st == 200 and "items" in d, f"status={st}")
        # bad kind -> 400
        st, _ = req(conn, "GET", "/api/assets?kind=nope", token=token)
        check("GET /api/assets?kind=nope -> 400", st == 400, f"status={st}")
        # 4) console-state
        st, body = req(conn, "GET", "/api/console-state", token=token)
        d = json.loads(body) if st == 200 else {}
        check(
            "GET /api/console-state",
            st == 200 and d.get("kind") == "console-state" and "recent_selections" in d,
            f"status={st}",
        )
        # 5) onboarding state
        st, _ = req(conn, "GET", "/api/onboarding", token=token)
        check("GET /api/onboarding", st == 200, f"status={st}")
        # 6) select hash-bound: first 200 rev 1, stale 409
        st, body = req(
            conn,
            "POST",
            "/api/select",
            token=token,
            body={"kind": "voice", "asset_id": "f", "expected_revision": 0},
        )
        rev = json.loads(body).get("revision") if st == 200 else None
        check("POST /api/select (voice) 200", st == 200 and rev == 1, f"status={st} rev={rev}")
        st, body = req(
            conn,
            "POST",
            "/api/select",
            token=token,
            body={"kind": "voice", "asset_id": "f", "expected_revision": 0},
        )
        check("POST /api/select stale -> 409", st == 409, f"status={st}")
        # 7) blocking gate: flip heat_scale to normal (adult) => 403
        (film_root / "film-spec.json").write_text(
            json.dumps({"genre": "adult", "heat_scale": "normal"}), encoding="utf-8"
        )
        st, body = req(
            conn,
            "POST",
            "/api/select",
            token=token,
            body={"kind": "voice", "asset_id": "female_lead", "expected_revision": 1},
        )
        check(
            "POST /api/select blocking gate -> 403",
            st == 403 and "硬门禁" in body.decode("utf-8", "ignore"),
            f"status={st}",
        )
        # restore gate-green for the remaining checks
        (film_root / "film-spec.json").write_text(
            json.dumps(
                {
                    "genre": "adult",
                    "heat_scale": "max",
                    "cast_voices": {"f": "zh-CN-XiaoyiNeural"},
                }
            ),
            encoding="utf-8",
        )
        # 8) cross-origin -> 403
        st, _ = req(
            conn,
            "POST",
            "/api/select",
            token=token,
            origin="http://evil.example",
            body={"kind": "voice", "asset_id": "female_lead"},
        )
        check("POST /api/select cross-origin -> 403", st == 403, f"status={st}")
        # 9) bad token -> 401
        st, _ = req(conn, "GET", "/api/gates", token="wrong-token")
        check("GET /api/gates bad token -> 401", st == 401, f"status={st}")
        # 10) media-lib path escape -> 404
        st, _ = req(conn, "GET", "/media-lib/../../etc/passwd", token=token)
        check("GET /media-lib/../.. escape -> 404", st == 404, f"status={st}")

        # ===================================================================== #
        # UI-feature e2e — simulates actual console operation in a browser:
        # open workbench -> dashboard loads all libraries -> user picks assets
        # -> console-state reflects choices -> canonical pipeline files updated.
        # ===================================================================== #

        # 11) Served-UI feature surface — proves the EXACT film-studio artifact
        #     (not a stale AI-slop build) is what the live server returns.
        check(
            "served console: overview/assets/review tabs",
            'data-tab="overview"' in text
            and 'data-tab="assets"' in text
            and 'data-tab="review"' in text,
        )
        check("served console: film-studio accent token present", "--accent:" in text)
        check(
            "served console: 6 material tabs wired",
            all(f'data-kind="{k}"' in text for k in ["bgm", "character", "voice", "shot", "scene", "prop"]),
        )
        check(
            "served console: dashboard + picker functions present",
            "function loadDashboard" in text and "function cardHtml" in text and "function pick" in text,
        )

        # 12) Dashboard parallel-load shape parity (loadDashboard contract).
        #     console.html's cardHtml() reads specific fields per kind; assert the
        #     backend returns exactly those shapes so a field rename can't
        #     silently break the rendered UI.
        required_fields = {
            "bgm": {"asset_id", "mood", "energy", "duration", "bpm", "path"},
            "character": {"asset_id", "name", "role"},
            "voice": {"asset_id", "voice"},
            "shot": {"shot_id", "state", "cloud_candidates"},
            "scene": {"scene_id", "title", "shot_count"},
            "prop": {"prop_id", "description"},
        }
        for kind in required_fields:
            st, body = req(conn, "GET", f"/api/assets?kind={kind}", token=token)
            d = json.loads(body) if st == 200 else {}
            items = d.get("items") if isinstance(d, dict) else None
            shape_ok = st == 200 and d.get("kind") == kind and isinstance(items, list)
            # Non-empty library => every item must carry the fields cardHtml reads.
            if shape_ok and items:
                fields = required_fields[kind]
                sample_ok = all(fields.issubset(it.keys()) for it in items if isinstance(it, dict))
            else:
                sample_ok = True  # empty library is a valid (degraded) state
            check(
                f"GET /api/assets?kind={kind} shape parity",
                shape_ok and sample_ok,
                f"status={st} items={len(items) if isinstance(items, list) else 'n/a'}",
            )

        # Helper: read the live ledger revision + full state.
        def get_state():
            s, b = req(conn, "GET", "/api/console-state", token=token)
            dd = json.loads(b) if s == 200 else {}
            return s, dd.get("ledger_revision", 0), dd

        # 13) Real selection -> state cycle (mirrors console.html pick()):
        #     capture ledger_revision, select, assert revision bumped + state reflects.
        st0, r0, _ = get_state()
        st, body = req(
            conn,
            "POST",
            "/api/select",
            token=token,
            body={"kind": "voice", "asset_id": "male_lead", "expected_revision": r0},
        )
        sel = json.loads(body) if st == 200 else {}
        check(
            "UI-flow: voice select 200 + revision bump",
            st == 200 and sel.get("revision") == r0 + 1,
            f"status={st} rev={sel.get('revision')}",
        )
        st1, r1, state1 = get_state()
        recent_voice = [
            x
            for x in state1.get("recent_selections", [])
            if x.get("kind") == "voice" and x.get("asset_id") == "male_lead"
        ]
        check(
            "UI-flow: console-state reflects voice selection",
            st1 == 200
            and r1 == r0 + 1
            and state1.get("selection_counts", {}).get("voice", 0) >= 1
            and bool(recent_voice),
            f"rev={r1} counts={state1.get('selection_counts')}",
        )

        # 14) Production-binding flow: lock a character -> canonical assets.json updated.
        #     This is the strongest "actually works" signal: a console click must
        #     drive the pipeline's own canonical file, not just a local ledger.
        st, body = req(
            conn,
            "POST",
            "/api/select",
            token=token,
            body={"kind": "character", "asset_id": "c1", "expected_revision": r1},
        )
        sel = json.loads(body) if st == 200 else {}
        canon = sel.get("canonical_binding", {}) if isinstance(sel, dict) else {}
        reg = (
            json.loads((film_root / "assets.json").read_text(encoding="utf-8"))
            if (film_root / "assets.json").is_file()
            else {}
        )
        chars = reg.get("characters") if isinstance(reg, dict) else None
        locked = any(
            isinstance(c, dict) and c.get("id") == "c1" and c.get("selected") is True
            for c in (chars or [])
        )
        check(
            "UI-flow: character lock 200 + canonical assets.json bound",
            st == 200 and canon.get("bound") is True and locked,
            f"status={st} canon={canon.get('bound')} locked={locked}",
        )
        st2, r2, state2 = get_state()
        check(
            "UI-flow: console-state reflects character lock",
            st2 == 200 and state2.get("selection_counts", {}).get("character", 0) >= 1,
            f"rev={r2}",
        )

        # 15) Prop selection (ledger-only kind) keeps the cycle coherent.
        st, body = req(
            conn,
            "POST",
            "/api/select",
            token=token,
            body={"kind": "prop", "asset_id": "p1", "expected_revision": r2},
        )
        check("UI-flow: prop select 200", st == 200, f"status={st}")
        st3, r3, state3 = get_state()
        check(
            "UI-flow: console-state reflects prop selection",
            st3 == 200 and state3.get("selection_counts", {}).get("prop", 0) >= 1,
            f"rev={r3} counts={state3.get('selection_counts')}",
        )

        # 16) BGM (optional, depends on the global approved catalog). Drive a real
        #     bgm select when the library yields approved assets; skip portably
        #     when no global catalog is present (keeps the live gate machine-agnostic).
        st, body = req(conn, "GET", "/api/assets?kind=bgm", token=token)
        bgm_items = (json.loads(body).get("items") if st == 200 else []) or []
        if bgm_items:
            bgm_id = bgm_items[0].get("asset_id")
            st, body = req(
                conn,
                "POST",
                "/api/select",
                token=token,
                body={"kind": "bgm", "asset_id": bgm_id, "expected_revision": r3},
            )
            check("UI-flow: bgm select 200 (global catalog)", st == 200, f"status={st} id={bgm_id}")
        else:
            print("[skip] GET /api/assets?kind=bgm empty (no global approved catalog) — bgm select not driven")

        # 17) Write-path hardening (mirrors the GET bad-kind check on the POST path).
        #     Capture the live revision first so a stale-ledger 409 can't mask the
        #     intended 400 rejection.
        _, rn, _ = get_state()
        st, _ = req(
            conn,
            "POST",
            "/api/select",
            token=token,
            body={"kind": "nope", "asset_id": "x", "expected_revision": rn},
        )
        check("POST /api/select bad kind -> 400", st == 400, f"status={st}")
        st, _ = req(
            conn,
            "POST",
            "/api/select",
            token=token,
            body={"kind": "character", "asset_id": "ghost", "expected_revision": rn},
        )
        check("POST /api/select unknown asset -> 400", st == 400, f"status={st}")
        conn.close()
    finally:
        # stop the server via its own stop endpoint
        try:
            stop = HTTPConnection("127.0.0.1", port)
            req(stop, "POST", "/api/stop", token=token, body={})
            stop.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    shutil.rmtree(film_root, ignore_errors=True)
    if failures:
        print(f"\n[smoke] FAILED checks: {failures}")
        return 1
    print("\n[smoke] ALL CHECKS PASSED ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
