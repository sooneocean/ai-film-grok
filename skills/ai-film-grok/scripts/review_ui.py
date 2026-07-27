"""Loopback-only WebUI for review_control; uses no third-party web framework."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from review_control import (
    ReviewControlConflict,
    ReviewControlError,
    advance_to_next_review,
    load_settings,
    record_action,
    review_queue,
    update_settings,
)
from util import write_json

MAX_BODY = 128 * 1024
MEDIA_SUFFIXES = frozenset(
    {".mp4", ".mov", ".m4v", ".webm", ".wav", ".mp3", ".m4a", ".png", ".jpg", ".jpeg", ".webp"}
)

_PAGE = r"""<!doctype html><meta charset=utf-8><title>AI Film 审核控制台</title><style>
body{font:15px system-ui;margin:2rem;background:#111827;color:#e5e7eb;max-width:1100px}.panel,.item{border:1px solid #374151;padding:1rem;margin:.7rem 0;border-radius:.4rem}.approved{border-color:#15803d}.stale,.blocked{border-color:#dc2626}button{margin:.2rem;padding:.4rem}textarea{width:100%;min-height:4rem}code{word-break:break-all;white-space:pre-wrap}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.5rem}.media{max-width:360px;max-height:280px;margin:.5rem .5rem .2rem 0;background:#000}label{display:block}.muted{color:#9ca3af}
 </style><h1>AI Film 审核控制台</h1><p id=summary>载入中…</p><section class=panel><b>自动推进</b><p class=muted id=runtime></p><button id=advance>自动推进至下一审核关</button></section><section class=panel><b>预算与审核者</b><div class=grid id=budgets></div><label>审核者 <input id=reviewer maxlength=80></label><button id=save-settings>保存设置</button></section><div id=items></div><script>
const token=new URLSearchParams(location.search).get('token');const h={'X-Review-Token':token};const reviewActions=new Set(['approve','reject','reshoot','needs_changes']);let rev=0,settingsRev=0,renderedStages=new Set();
async function api(p,o={}){o.headers={...h,...(o.headers||{})};let r=await fetch(p,o),j=await r.json();if(!r.ok)throw Error(j.error||r.status);return j}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}function mediaUrl(p){return '/media/'+p.split('/').map(encodeURIComponent).join('/')}
function media(p){let u=mediaUrl(p),e=esc(p);if(/\.(mp4|mov|m4v|webm)$/i.test(p))return `<video class=media controls preload=metadata src="${u}"></video>`;if(/\.(wav|mp3|m4a)$/i.test(p))return `<audio controls preload=metadata src="${u}"></audio>`;return `<img class=media alt="${e}" src="${u}">`}
function budget(d){return Object.entries(d.envelopes).map(([k,v])=>`<label>${esc(k)} <input id="b-${k}" type=number min=0 step=1 value="${v}"><small class=muted> 已用 ${d.spent[k]??'未知'} / 剩余 ${d.remaining[k]??'未知'}</small></label>`).join('')}
async function load(){let d=await api('/api/status');rev=d.queue.ledger_revision;settingsRev=d.settings.revision;renderedStages=new Set(d.queue.items.map(x=>x.id));document.getElementById('summary').textContent=`审批账本 revision ${rev} · 审核者 ${d.settings.reviewer}`;document.getElementById('runtime').textContent=`运行任务 ${d.queue.runtime.running} · 未知任务 ${d.queue.runtime.unknown} · 队列 ${JSON.stringify(d.queue.runtime.job_counts)}`;document.getElementById('reviewer').value=d.settings.reviewer;document.getElementById('budgets').innerHTML=budget(d.queue.budget);document.getElementById('items').innerHTML=d.queue.items.map(x=>`<section class="item ${x.state}" data-stage="${x.id}"><b>${esc(x.title)}</b> — ${x.state}<br><code>${esc(JSON.stringify(x.input_hashes))}</code><div>${x.media.map(media).join('')}</div><textarea id="n-${x.id}" placeholder="审核意见（必填）"></textarea><input id="t-${x.id}" type=number min=0 step=.1 placeholder="视频时间码（秒，可选）"><select id="i-${x.id}"><option value="other">other</option><option value="motion">motion</option><option value="identity">identity</option><option value="technical">technical</option><option value="audio">audio</option><option value="budget">budget</option></select><br>${['approve','reject','reshoot','needs_changes'].map(a=>`<button data-review-action="${a}">${a}</button>`).join(' ')}</section>`).join('')}
async function act(stage,action){let note=document.getElementById('n-'+stage).value,timestamp_sec=document.getElementById('t-'+stage).value;try{await api('/api/action',{method:'POST',headers:{'Content-Type':'application/json',Origin:location.origin},body:JSON.stringify({stage,action,note,issue:document.getElementById('i-'+stage).value,timestamp_sec:timestamp_sec?Number(timestamp_sec):null,expected_ledger_revision:rev})});await load()}catch(e){alert(e.message)}}
async function saveSettings(){let budget_envelopes={};for(let k of ['still','motion','audio','post'])budget_envelopes[k]=Number(document.getElementById('b-'+k).value);try{await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json',Origin:location.origin},body:JSON.stringify({reviewer:document.getElementById('reviewer').value,budget_envelopes,expected_revision:settingsRev})});await load()}catch(e){alert(e.message)}}
async function advance(){try{await api('/api/advance',{method:'POST',headers:{'Content-Type':'application/json',Origin:location.origin},body:JSON.stringify({expected_ledger_revision:rev})});await load()}catch(e){alert(e.message)}}
document.getElementById('advance').addEventListener('click',advance);document.getElementById('save-settings').addEventListener('click',saveSettings);document.getElementById('items').addEventListener('click',event=>{let button=event.target.closest('button[data-review-action]');if(button){let stage=button.closest('[data-stage]').dataset.stage,action=button.dataset.reviewAction;if(renderedStages.has(stage)&&reviewActions.has(action))act(stage,action)}});load()
</script>"""


class ReviewUIError(ValueError):
    pass


def _session_path(root: Path) -> Path:
    return root / "receipts" / "review-ui-session.json"


def _safe_media(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if (
        not candidate.is_file()
        or candidate.is_symlink()
        or candidate.suffix.lower() not in MEDIA_SUFFIXES
        or root not in candidate.parents
    ):
        raise ReviewUIError("media path is outside the film workspace")
    return candidate


def make_handler(root: Path, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AIFilmReviewUI/1"

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-Review-Token", ""), token)

        def _payload(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_BODY:
                raise ReviewUIError("invalid request body size")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ReviewUIError("request body must be a JSON object")
            return value

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                data = _PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)
                return
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid session token"})
                return
            if parsed.path == "/api/status":
                self._json(200, {"queue": review_queue(root), "settings": load_settings(root)})
                return
            if parsed.path.startswith("/media/"):
                try:
                    self._media(_safe_media(root, unquote(parsed.path.removeprefix("/media/"))))
                except ReviewUIError as exc:
                    self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def _media(self, path: Path) -> None:
            size = path.stat().st_size
            start, end = 0, size - 1
            status = 200
            raw = self.headers.get("Range")
            if raw:
                try:
                    unit, value = raw.split("=", 1)
                    left, right = value.split("-", 1)
                    if unit != "bytes":
                        raise ValueError
                    start = int(left) if left else max(0, size - int(right))
                    end = int(right) if right else size - 1
                    if start < 0 or end < start or start >= size:
                        raise ValueError
                    end = min(end, size - 1)
                    status = HTTPStatus.PARTIAL_CONTENT
                except ValueError:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
            self.send_response(status)
            self.send_header(
                "Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            )
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as handle:
                handle.seek(start)
                self.wfile.write(handle.read(end - start + 1))

        def do_POST(self) -> None:
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid session token"})
                return
            origin = self.headers.get("Origin", "")
            if origin != f"http://127.0.0.1:{self.server.server_port}":
                self._json(HTTPStatus.FORBIDDEN, {"error": "cross-origin request rejected"})
                return
            try:
                body = self._payload()
                if self.path == "/api/action":
                    report = record_action(root, **body)
                elif self.path == "/api/settings":
                    report = update_settings(root, **body)
                elif self.path == "/api/advance":
                    report = advance_to_next_review(root, **body)
                elif self.path == "/api/stop":
                    report = {"ok": True, "stopping": True}
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                self._json(200, report)
            except ReviewControlConflict as exc:
                self._json(HTTPStatus.CONFLICT, {"error": str(exc)})
            except (
                ReviewControlError,
                ReviewUIError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    return Handler


def serve(root: Path | str, *, port: int = 0) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise ReviewUIError("film root must be an existing directory")
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(base, token))
    session = {
        "kind": "review-ui-session",
        "pid": os.getpid(),
        "port": server.server_port,
        "token": token,
        "root": str(base),
    }
    write_json(_session_path(base), session)
    os.chmod(_session_path(base), 0o600)
    print(
        json.dumps(
            {
                "ok": True,
                "url": f"http://127.0.0.1:{server.server_port}/?token={token}",
                "root": str(base),
                "token": token,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        _session_path(base).unlink(missing_ok=True)
    return session


def stop(root: Path | str) -> dict[str, Any]:
    path = _session_path(Path(root).expanduser().resolve())
    if path.is_symlink():
        raise ReviewUIError("review UI session path must not be a symlink")
    session = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    base = Path(root).expanduser().resolve()
    if (
        not isinstance(session, dict)
        or session.get("root") != str(base)
        or not isinstance(session.get("port"), int)
        or not isinstance(session.get("token"), str)
    ):
        raise ReviewUIError("no active review UI session")
    request = Request(
        f"http://127.0.0.1:{session['port']}/api/stop",
        data=b"{}",
        method="POST",
        headers={
            "X-Review-Token": session["token"],
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{session['port']}",
        },
    )
    try:
        with urlopen(request, timeout=2) as response:  # noqa: S310 -- fixed loopback URL
            if response.status != HTTPStatus.OK:
                raise ReviewUIError("review UI refused to stop")
    except OSError as exc:
        raise ReviewUIError("review UI is not reachable") from exc
    return {"ok": True, "stopping_port": session["port"]}


def add_review_ui_parsers(subparsers: Any) -> None:
    parser = subparsers.add_parser("review-ui", help="Loopback review WebUI: serve|status|stop")
    sub = parser.add_subparsers(dest="review_ui_action", required=True)
    serve_p = sub.add_parser("serve")
    serve_p.add_argument("--root", required=True)
    serve_p.add_argument("--port", type=int, default=0)
    status_p = sub.add_parser("status")
    status_p.add_argument("--root", required=True)
    stop_p = sub.add_parser("stop")
    stop_p.add_argument("--root", required=True)


def run_review_ui(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.review_ui_action == "serve":
        return serve(args.root, port=args.port), 0
    if args.review_ui_action == "status":
        return {
            "ok": True,
            "queue": review_queue(args.root),
            "settings": load_settings(args.root),
        }, 0
    if args.review_ui_action == "stop":
        return stop(args.root), 0
    raise ReviewUIError("unknown review-ui action")
