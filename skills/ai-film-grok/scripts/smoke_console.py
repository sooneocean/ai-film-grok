#!/usr/bin/env python3
"""Live smoke for the localhost review console via the real `aifilm` CLI.

Repo-relative: resolves the git root from this file's location so it works from
any checkout (dev tree or plugin mirror). Self-contained stdlib harness — it
spawns `scripts/aifilm review-ui serve` (→ post.review_ui through the shim) on a
real loopback socket, then drives the full flow with real HTTP requests:

  console page, gates panel, asset listing (+ bad kind → 400), console-state
  (+ recent_selections), onboarding, hash-bound select (200 then stale 409),
  blocking gate (403), cross-origin (403), bad token (401), media-lib path-escape
  (404).

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
