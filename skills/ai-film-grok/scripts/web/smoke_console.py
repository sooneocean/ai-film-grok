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
#   <root>/skills/ai-film-grok/scripts/web/smoke_console.py
# so FOUR parents up is the git root.
ROOT = Path(__file__).resolve().parents[4]
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


def start_studio_server(studio_dir: Path):
    """Boot a studio-mode (导演总控台) review server for the studio smoke phase."""
    proc = subprocess.Popen(
        [str(LAUNCHER), "review-ui", "serve", "--studio", str(studio_dir), "--port", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(100):
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"studio server exited early: {proc.stderr.read()[-2000:]}"
                )
            continue
        line = line.strip()
        if line.startswith("{"):
            info = json.loads(line)
            if info.get("ok"):
                return proc, info
    raise RuntimeError("never received studio server URL JSON")


def setup_studio_dir() -> Path:
    """Create a temp studio dir with two film roots for the studio-mode e2e."""
    studio = Path(tempfile.mkdtemp(prefix="aifilm-studio-smoke-"))
    # film-a: 甜宠, producing (has approved clips)
    fa = studio / "film-a"
    fa.mkdir()
    (fa / "manifest.json").write_text(
        json.dumps(
            {
                "title": "雨夜书店",
                "theme": "甜宠",
                "aspect_ratio": "16:9",
                "style_locked": True,
                "clips": {f"shot_{i:03d}": {"status": "approved"} for i in range(8)},
                "gates": {f"gate_{i}": True for i in range(5)},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # film-b: 悬疑, draft (no approved clips)
    fb = studio / "film-b"
    fb.mkdir()
    (fb / "manifest.json").write_text(
        json.dumps(
            {
                "title": "雾港谜案",
                "theme": "悬疑",
                "aspect_ratio": "9:16",
                "style_locked": False,
                "clips": {f"shot_{i:03d}": {"status": "draft"} for i in range(4)},
                "gates": {f"gate_{i}": False for i in range(3)},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return studio


def run_studio_phase(failures):
    """Studio-mode (导演总控台) live e2e: lists films, switches active film,
    rejects path traversal. Drives a real --studio server on loopback."""
    studio_dir = setup_studio_dir()
    proc = None
    port = None
    token = None
    try:
        proc, info = start_studio_server(studio_dir)
        parsed = urlparse(info["url"])
        port = parsed.port
        token = info["token"]
        print(f"[smoke] studio server up: {info['url']}")

        def check(name, cond, extra=""):
            status = "PASS" if cond else "FAIL"
            print(f"[{status}] {name} {extra}")
            if not cond:
                failures.append(name)

        def sreq(method, path, *, body=None):
            return req(HTTPConnection("127.0.0.1", port), method, path, token=token, body=body)

        # studio console HTML must ship the 总控台 tab + studio JS
        st, body = sreq("GET", "/console")
        text = body.decode("utf-8", "ignore") if body else ""
        check("studio console: 总控台 tab present", st == 200 and 'id="tab-studio"' in text, f"status={st}")
        check("studio console: studio JS wired", st == 200 and "function loadStudio" in text, f"status={st}")

        # /api/studio lists films
        st, body = sreq("GET", "/api/studio")
        d = json.loads(body) if st == 200 else {}
        check(
            "GET /api/studio",
            st == 200 and d.get("film_count", 0) >= 1,
            f"status={st} count={d.get('film_count')}",
        )

        # console-state carries studio_mode
        st, body = sreq("GET", "/api/console-state")
        ds = json.loads(body) if st == 200 else {}
        check("GET /api/console-state studio_mode", st == 200 and ds.get("studio_mode") is True, f"status={st}")

        # select switches active film (200) and persists
        st, _ = sreq("POST", "/api/studio/select", body={"id": "film-b"})
        check("POST /api/studio/select switches active film", st == 200, f"status={st}")
        st, body = sreq("GET", "/api/studio")
        da = json.loads(body) if st == 200 else {}
        check(
            "after select: active_film_id persisted",
            st == 200 and da.get("active_film_id") == "film-b",
            f"status={st} active={da.get('active_film_id')}",
        )

        # traversal guard -> 400
        st, _ = sreq("POST", "/api/studio/select", body={"id": "../escape"})
        check("POST /api/studio/select traversal -> 400", st == 400, f"status={st}")
    finally:
        if proc is not None and port is not None:
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
    shutil.rmtree(studio_dir, ignore_errors=True)


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
        # 11b) Command center shipped with the page (CTO plan T2): the dashboard
        #      must be a real monitor+direct surface, not a read-only overview.
        check(
            "served console: command center present",
            'id="dash-command"' in text
            and 'id="cmd-go"' in text
            and 'id="cmd-advance"' in text
            and "function cmdGo" in text
            and "function cmdAdvance" in text,
        )
        check(
            "served console: director inbox + dailies",
            'id="dash-inbox"' in text and "/api/live" in text and "EventSource" in text and "allSettled" in text and 'data-tab="dailies"' in text and "function loadDailies" in text,
        )
        # 11c) Onboarding tab actually wires its loader (CTO plan T1): the tab
        #      switch must invoke loadOnboarding() so the "起步" screen is alive.
        check(
            "served console: onboarding tab lazy-loads",
            "if (b.dataset.tab === 'onboarding') loadOnboarding()" in text,
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

        # 18) Command-center drive endpoints reachable (CTO plan T2): the
        #     "启动流水线" / "推进审核队列" buttons POST here. A fresh film root
        #     has no completed onboarding / no pending review, so the handlers
        #     return structured 400/403/409 — the assertion is that the wire is
        #     live (NOT 404/405/500), proving the buttons are wired end-to-end.
        st, body = req(conn, "GET", "/api/onboarding", token=token)
        ob_rev = (json.loads(body).get("revision", 0) if st == 200 else 0)
        st, _ = req(
            conn,
            "POST",
            "/api/onboarding/go",
            token=token,
            body={"expected_revision": ob_rev},
        )
        check(
            "POST /api/onboarding/go reachable (cmd-go wire)",
            st in (200, 400, 403, 409),
            f"status={st}",
        )
        st, _ = req(
            conn,
            "POST",
            "/api/advance",
            token=token,
            body={"expected_ledger_revision": r3},
        )
        check(
            "POST /api/advance reachable (cmd-advance wire)",
            st in (200, 409),
            f"status={st}",
        )
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
    run_studio_phase(failures)
    if failures:
        print(f"\n[smoke] FAILED checks: {failures}")
        return 1
    print("\n[smoke] ALL CHECKS PASSED ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
