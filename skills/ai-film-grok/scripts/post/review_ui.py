"""Loopback-only WebUI for review_control; uses no third-party web framework.

Security invariant (S8 · console quality review):
  This server is **loopback-only** by design (bind 127.0.0.1 + token + Origin
  check on mutating POSTs).  If it is ever exposed beyond localhost, add CSRF,
  SameSite cookies, and rate limiting before opening the bind address.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
import threading
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

from final_review_input import review_input_template, write_review_input
from review_control import (
    ReviewControlConflict,
    ReviewControlError,
    advance_to_next_review,
    autopilot_status,
    load_settings,
    record_action,
    review_queue,
    update_settings,
)
from util import exclusive_file_lock, write_json
from web_core import WebConsoleConflict, WebConsoleError, WebConsoleForbidden
from web_routes import error_body

MAX_BODY = 128 * 1024
MAX_UPLOAD = 20 * 1024 * 1024
MEDIA_SUFFIXES = frozenset(
    {".mp4", ".mov", ".m4v", ".webm", ".wav", ".mp3", ".m4a", ".png", ".jpg", ".jpeg", ".webp"}
)

_PAGE = r"""<!doctype html><meta charset=utf-8><title>AI Film 审核控制台</title><style>
body{font:15px system-ui;margin:2rem;background:#111827;color:#e5e7eb;max-width:1100px}.panel,.item{border:1px solid #374151;padding:1rem;margin:.7rem 0;border-radius:.4rem}.approved{border-color:#15803d}.stale,.blocked,.notice-error{border-color:#dc2626}.notice-success{border-color:#15803d}button{margin:.2rem;padding:.4rem}textarea{width:100%;min-height:4rem}code{word-break:break-all;white-space:pre-wrap}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.5rem}.media{max-width:360px;max-height:280px;margin:.5rem .5rem .2rem 0;background:#000}label{display:block}.muted{color:#9ca3af}
 </style><h1>AI Film 审核控制台</h1><p id=summary>载入中…</p><p id=notice class="panel muted" role=status aria-live=polite>等待操作。</p><section class=panel><b>自动推进</b><p class=muted id=runtime></p><p class=muted id=autopilot-status>尚无自动驾驶记录。</p><button id=advance>自动推进至下一审核关</button></section><section class=panel><b>预算与审核者</b><div class=grid id=budgets></div><label>审核者 <input id=reviewer maxlength=80></label><label><input id=autopilot-enabled type=checkbox> 启用预算自动驾驶</label><label>允许 provider（逗号分隔）<input id=autopilot-providers></label><label>抽检间隔 <input id=autopilot-sample type=number min=1 value=5></label><label><input id=telegram-notify type=checkbox> Telegram 停机提醒</label><button id=save-settings>保存设置</button></section><section class=panel id=final-review-form hidden><b>终片完整审核</b><p class=muted>完整播放后逐项填入时间码、证据与 1–5 分；这里只写审核输入，不会自动批准成片。</p><label><input id=watched-full type=checkbox> 已完整观看</label><label>审核说明<textarea id=final-notes></textarea></label><div id=final-dimensions></div><button id=save-final-review>保存终片审核输入</button></section><div id=items></div><script>
const token=new URLSearchParams(location.search).get('token');if(token)history.replaceState(null,'',location.pathname);const h=token?{'X-Review-Token':token}:{};const reviewActions=new Set(['approve','reject','reshoot','needs_changes']);let rev=0,settingsRev=0,renderedStages=new Set(),finalTemplate=null,reviewStartedAt=Date.now();
async function api(p,o={}){o.headers={...h,...(o.headers||{})};let r=await fetch(p,o),j=await r.json();if(!r.ok)throw Error(j.error||r.status);return j}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}function mediaUrl(p){return '/media/'+p.split('/').map(encodeURIComponent).join('/')}
function notice(message,isError=false){let node=document.getElementById('notice');node.textContent=message;node.className=`panel ${isError?'notice-error':'notice-success'}`}
function media(p){let u=mediaUrl(p),e=esc(p);if(/\.(mp4|mov|m4v|webm)$/i.test(p))return `<video class=media controls preload=metadata src="${u}"></video>`;if(/\.(wav|mp3|m4a)$/i.test(p))return `<audio controls preload=metadata src="${u}"></audio>`;return `<img class=media alt="${e}" src="${u}">`}
function budget(d){return Object.entries(d.envelopes).map(([k,v])=>`<label>${esc(k)} <input id="b-${k}" type=number min=0 step=1 value="${v}"><small class=muted> 已用 ${d.spent[k]??'未知'} / 剩余 ${d.remaining[k]??'未知'}</small></label>`).join('')}
function history(actions){if(!actions.length)return '<p class=muted>尚无审核记录。</p>';return `<details><summary>最近审核记录（${actions.length}）</summary><ul>${actions.map(a=>`<li><b>${esc(a.action)}</b> · ${esc(a.issue)} · ${esc(a.recorded_at)}${a.timestamp_sec===null?'':` · ${a.timestamp_sec} 秒`}<br>${esc(a.note)}</li>`).join('')}</ul></details>`}
function cloudCards(rows,stage){if(!rows.length)return '';let ready=rows.filter(c=>c.status==='reviewable');let choose=ready.length?`<label>批准候选 <select id="c-${esc(stage)}"><option value="">请选择已通过终端校验的候选</option>${ready.map(c=>`<option value="${esc(c.id)}">${esc(c.provider)} / ${esc(c.model)} · ${esc(c.id)}</option>`).join('')}</select></label>`:'';return `<section class=panel><b>云端候选</b>${rows.map(c=>{let qa=c.technical_qa||{},detail=c.error_code?`错误：${esc(c.error_code)}`:`decode=${esc(qa.decode_ok)} · ${esc(qa.duration_sec??'?')} 秒`;return `<article><b>${esc(c.provider)} / ${esc(c.model)}</b> · ${esc(c.status)}<br><small>${detail}</small>${c.media_path?media(c.media_path):''}<br><small>task: ${esc(c.task_id)} · receipt: ${esc(c.receipt_path||'pending')}</small></article>`}).join('')}${choose}</section>`}
async function load(){let d=await api('/api/status');rev=d.queue.ledger_revision;settingsRev=d.settings.revision;renderedStages=new Set(d.queue.items.map(x=>x.id));document.getElementById('summary').textContent=`审批账本 revision ${rev} · 审核者 ${d.settings.reviewer}${d.queue.cloud.next_reviewable_shot?` · 下一镜 ${d.queue.cloud.next_reviewable_shot}`:''}`;document.getElementById('runtime').textContent=`运行任务 ${d.queue.runtime.running} · 未知任务 ${d.queue.runtime.unknown} · 队列 ${JSON.stringify(d.queue.runtime.job_counts)}`;let a=d.autopilot,p=d.settings.autopilot;document.getElementById('autopilot-status').textContent=a?`自动驾驶：${a.stop_reason} · 已执行 ${a.executed?.length??0} 项 · ${a.checked_at??''}`:'尚无自动驾驶记录。';document.getElementById('reviewer').value=d.settings.reviewer;document.getElementById('autopilot-enabled').checked=p.enabled;document.getElementById('autopilot-providers').value=p.allowed_providers.join(',');document.getElementById('autopilot-sample').value=p.sample_every;document.getElementById('telegram-notify').checked=p.telegram_notify;document.getElementById('budgets').innerHTML=budget(d.queue.budget);document.getElementById('items').innerHTML=d.queue.items.map(x=>`<section class="item ${x.state}" data-stage="${x.id}"><b>${esc(x.title)}</b> — ${x.state}<br><code>${esc(JSON.stringify(x.input_hashes))}</code><div>${x.media.map(media).join('')}</div>${cloudCards(x.cloud_candidates||[],x.id)}${history(x.recent_actions)}<textarea id="n-${x.id}" placeholder="审核意见（必填）"></textarea><input id="t-${x.id}" type=number min=0 step=.1 placeholder="视频时间码（秒，可选）"><select id="i-${x.id}"><option value="other">other</option><option value="motion">motion</option><option value="identity">identity</option><option value="technical">technical</option><option value="audio">audio</option><option value="budget">budget</option></select><br>${['approve','reject','reshoot','needs_changes'].map(a=>`<button data-review-action="${a}">${a}</button>`).join(' ')}</section>`).join('')}
async function act(stage,action){let note=document.getElementById('n-'+stage).value,timestamp_sec=document.getElementById('t-'+stage).value,candidate=document.getElementById('c-'+stage);try{await api('/api/action',{method:'POST',headers:{'Content-Type':'application/json',Origin:location.origin},body:JSON.stringify({stage,action,note,issue:document.getElementById('i-'+stage).value,timestamp_sec:timestamp_sec?Number(timestamp_sec):null,candidate_id:candidate&&candidate.value?candidate.value:null,expected_ledger_revision:rev})});notice(`已记录 ${action}：${stage}`);await load()}catch(e){notice(e.message,true)}}
async function saveSettings(){let budget_envelopes={};for(let k of ['still','motion','audio','post'])budget_envelopes[k]=Number(document.getElementById('b-'+k).value);let autopilot={enabled:document.getElementById('autopilot-enabled').checked,allowed_providers:document.getElementById('autopilot-providers').value.split(',').map(x=>x.trim()).filter(Boolean),sample_every:Number(document.getElementById('autopilot-sample').value),telegram_notify:document.getElementById('telegram-notify').checked};try{await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json',Origin:location.origin},body:JSON.stringify({reviewer:document.getElementById('reviewer').value,budget_envelopes,autopilot,expected_revision:settingsRev})});notice('审核者、预算与自动驾驶策略已保存。');await load()}catch(e){notice(e.message,true)}}
async function advance(){try{await api('/api/advance',{method:'POST',headers:{'Content-Type':'application/json',Origin:location.origin},body:JSON.stringify({expected_ledger_revision:rev})});notice('本地步骤已执行，审核队列已刷新。');await load()}catch(e){notice(e.message,true)}}
async function loadFinal(){try{finalTemplate=await api('/api/final-review-template');let box=document.getElementById('final-review-form');box.hidden=false;document.getElementById('final-dimensions').innerHTML=finalTemplate.dimensions.map((d,i)=>`<fieldset><legend>${esc(d)}</legend><select id="fs-${d}"><option value=pass>pass</option><option value=fail>fail</option></select><input id="fg-${d}" type=number min=1 max=5 value=4 aria-label="${esc(d)} grade"><input id="ft-${d}" type=number min=0 step=.1 value="${i}" aria-label="${esc(d)} timestamp"><input id="fn-${d}" value="checked ${esc(d)}" aria-label="${esc(d)} evidence"></fieldset>`).join('')}catch(e){document.getElementById('final-review-form').hidden=true}}
async function saveFinal(){let scorecard={},grades={},screening_evidence={};for(let d of finalTemplate.dimensions){scorecard[d]=document.getElementById('fs-'+d).value;grades[d]=Number(document.getElementById('fg-'+d).value);screening_evidence[d]={timestamp_sec:Number(document.getElementById('ft-'+d).value),note:document.getElementById('fn-'+d).value}}let body={schema_version:1,kind:'final-review-input',approve:true,reviewer:document.getElementById('reviewer').value,notes:document.getElementById('final-notes').value,watched_full:document.getElementById('watched-full').checked,final_output_sha256:finalTemplate.final_output_sha256,human_minutes:Math.max(.1,(Date.now()-reviewStartedAt)/60000),scorecard,grades,screening_evidence,fail_reasons:{},reshoot_shots:[]};try{let result=await api('/api/final-review-input',{method:'POST',headers:{'Content-Type':'application/json',Origin:location.origin},body:JSON.stringify(body)});notice(`审核输入已保存：${result.path}`)}catch(e){notice(e.message,true)}}
document.getElementById('advance').addEventListener('click',advance);document.getElementById('save-settings').addEventListener('click',saveSettings);document.getElementById('save-final-review').addEventListener('click',saveFinal);document.getElementById('items').addEventListener('click',event=>{let button=event.target.closest('button[data-review-action]');if(button){let stage=button.closest('[data-stage]').dataset.stage,action=button.dataset.reviewAction;if(renderedStages.has(stage)&&reviewActions.has(action))act(stage,action)}});load();loadFinal()
</script>"""


class ReviewUIError(ValueError):
    pass


def _session_path(root: Path) -> Path:
    return root / "receipts" / "review-ui-session.json"


def create_invite(root: Path | str, *, ttl_seconds: int = 600) -> dict[str, str]:
    """Create one Telegram-safe bootstrap secret, never a reusable API token."""
    base = Path(root).expanduser().resolve()
    path = _session_path(base)
    if ttl_seconds < 60 or ttl_seconds > 3600:
        raise ReviewUIError("invite TTL must be 60-3600 seconds")
    with exclusive_file_lock(path):
        session = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        if not isinstance(session, dict) or session.get("root") != str(base):
            raise ReviewUIError("no active review UI session")
        secret = secrets.token_urlsafe(32)
        session["invite_sha256"] = sha256_file_from_text(secret)
        session["invite_expires_at"] = (
            datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        ).isoformat()
        session["invite_used"] = False
        write_json(path, session)
        os.chmod(path, 0o600)
    return {
        "url": f"http://127.0.0.1:{session['port']}/?invite={secret}",
        "expires_at": session["invite_expires_at"],
    }


def sha256_file_from_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _consume_invite(root: Path, invite: str) -> bool:
    path = _session_path(root)
    with exclusive_file_lock(path):
        session = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        if (
            not isinstance(session, dict)
            or session.get("root") != str(root)
            or session.get("invite_used") is True
        ):
            return False
        if not secrets.compare_digest(
            str(session.get("invite_sha256") or ""), sha256_file_from_text(invite)
        ):
            return False
        try:
            expires = datetime.fromisoformat(
                str(session.get("invite_expires_at") or "").replace("Z", "+00:00")
            )
        except ValueError:
            return False
        if expires.tzinfo is None or expires.astimezone(UTC) <= datetime.now(UTC):
            return False
        session["invite_used"] = True
        write_json(path, session)
        os.chmod(path, 0o600)
        return True


def _safe_media(root: Path, relative: str) -> Path:
    base = root.resolve()
    candidate = (base / relative).resolve()
    if (
        not candidate.is_file()
        or candidate.is_symlink()
        or candidate.suffix.lower() not in MEDIA_SUFFIXES
        or base not in candidate.parents
    ):
        raise ReviewUIError("media path is outside the film workspace")
    return candidate


def make_handler(root: Path, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AIFilmReviewUI/1"

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            # Unify error shape with FastAPI gateway: always expose both keys.
            if status >= 400 and "error" in payload and "detail" not in payload:
                payload = {**error_body(str(payload["error"])), **payload}
            elif status >= 400 and "detail" in payload and "error" not in payload:
                payload = {**error_body(str(payload["detail"])), **payload}
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            header = self.headers.get("X-Review-Token", "")
            cookie = self.headers.get("Cookie", "")
            cookie_token = next(
                (
                    part.split("=", 1)[1]
                    for part in cookie.split(";")
                    if part.strip().startswith("AIFILM_REVIEW=")
                ),
                "",
            )
            # Query token for EventSource (cannot set custom headers)
            try:
                from urllib.parse import parse_qs, urlparse

                qtok = (parse_qs(urlparse(self.path).query).get("token") or [""])[0]
            except Exception:
                qtok = ""
            return (
                secrets.compare_digest(header, token)
                or secrets.compare_digest(cookie_token, token)
                or (bool(qtok) and secrets.compare_digest(qtok, token))
            )

        def _payload(self, max_size: int = MAX_BODY) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > max_size:
                raise ReviewUIError("invalid request body size")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ReviewUIError("request body must be a JSON object")
            return value

        def _send_html(self, data: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            # Phase E: loopback console CSP (inline scripts required by console.html)
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                "media-src 'self' blob:; connect-src 'self'; frame-ancestors 'self'; "
                "base-uri 'self'; form-action 'self'",
            )
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.end_headers()
            self.wfile.write(data)

        def _send_console(self) -> None:
            console = Path(__file__).resolve().parent.parent / "web" / "console.html"
            if not console.is_file():
                self._json(HTTPStatus.NOT_FOUND, {"error": "console not found"})
                return
            try:
                data = console.read_bytes()
            except OSError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "console unreadable"})
                return
            self._send_html(data)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            # Studio mode: the "active film" is the per-request root. When not in
            # studio mode, self.server.active_film is unset and we fall back to the
            # serve-time root (keeps single-root tests / CLI working unchanged).
            base_root = root
            film_root = getattr(self.server, "active_film", None) or root
            # B1 single shell: / and /console serve workbench; /review is验片专页.
            if parsed.path in ("/", "/console", "/studio"):
                invite = (parse_qs(parsed.query).get("invite") or [""])[0]
                if invite and parsed.path == "/":
                    if not _consume_invite(base_root, invite):
                        self._json(
                            HTTPStatus.UNAUTHORIZED, {"error": "invalid or expired review invite"}
                        )
                        return
                    self.send_response(HTTPStatus.SEE_OTHER)
                    self.send_header("Location", "/console")
                    self.send_header(
                        "Set-Cookie", f"AIFILM_REVIEW={token}; HttpOnly; SameSite=Strict; Path=/"
                    )
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    return
                self._send_console()
                return
            if parsed.path == "/review":
                self._send_html(_PAGE.encode("utf-8"))
                return
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid session token"})
                return
            if parsed.path == "/api/status":
                self._json(
                    200,
                    {
                        "queue": review_queue(film_root),
                        "settings": load_settings(film_root),
                        "autopilot": autopilot_status(film_root),
                    },
                )
                return
            if parsed.path == "/api/final-review-template":
                try:
                    self._json(200, review_input_template(film_root))
                except ValueError as exc:
                    self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            if parsed.path == "/api/gates":
                try:
                    import gate_panel

                    self._json(200, gate_panel.collect_gates(film_root))
                except Exception as exc:  # noqa: BLE001
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            if parsed.path == "/api/assets":
                kind = (parse_qs(parsed.query).get("kind") or ["bgm"])[0]
                try:
                    import asset_picker

                    self._json(200, asset_picker.list_assets(film_root, kind))
                except WebConsoleError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if parsed.path == "/api/console-state":
                try:
                    import asset_picker

                    state = asset_picker.console_state(film_root)
                    # Studio mode: tell the console whether it may show the
                    # 总控台 (director command center) tab and which film is active.
                    sd = getattr(self.server, "studio_dir", None)
                    state["studio_mode"] = sd is not None
                    state["studio_dir"] = str(sd) if sd else None
                    active = getattr(self.server, "active_film", None)
                    state["active_film_id"] = active.name if active else None
                    self._json(200, state)
                except Exception as exc:  # noqa: BLE001
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            if parsed.path == "/api/live":
                try:
                    from console_projection import project_director_live

                    self._json(200, project_director_live(film_root, include_token=False))
                except Exception as exc:  # noqa: BLE001
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            if parsed.path == "/api/events":
                try:
                    from console_projection import project_events_tail

                    qs = parse_qs(parsed.query)
                    since = (qs.get("since") or [None])[0]
                    try:
                        limit = int((qs.get("limit") or ["40"])[0])
                    except ValueError:
                        limit = 40
                    self._json(200, project_events_tail(film_root, since=since, limit=limit))
                except Exception as exc:  # noqa: BLE001
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            if parsed.path == "/api/stream":
                # SSE live feed (Phase E). Auth via header/cookie/?token=
                try:
                    from web.sse_stream import format_keepalive, iter_director_sse
                except Exception as exc:  # noqa: BLE001
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                    return
                qs = parse_qs(parsed.query)
                try:
                    interval = float((qs.get("interval") or ["1.5"])[0])
                except ValueError:
                    interval = 1.5
                try:
                    max_events = (qs.get("max") or [None])[0]
                    max_events = int(max_events) if max_events is not None else None
                except ValueError:
                    max_events = None
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                try:
                    for chunk in iter_director_sse(
                        film_root, interval_sec=interval, max_events=max_events
                    ):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
                return
            if parsed.path == "/api/takes":
                try:
                    from web import takes_api
                    from web_core import WebConsoleError

                    shot = (parse_qs(parsed.query).get("shot") or [None])[0]
                    if shot:
                        self._json(200, takes_api.get_takes(film_root, shot))
                    else:
                        self._json(200, takes_api.list_take_shots(film_root))
                except WebConsoleError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                except Exception as exc:  # noqa: BLE001
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            if parsed.path == "/api/shot-card":
                try:
                    from web import shot_card_api
                    from web_core import WebConsoleError

                    qs = parse_qs(parsed.query)
                    shot = (qs.get("shot") or [None])[0]
                    if shot:
                        self._json(200, shot_card_api.get_shot_card(film_root, shot))
                    else:
                        try:
                            limit = int((qs.get("limit") or ["80"])[0])
                        except ValueError:
                            limit = 80
                        self._json(200, shot_card_api.list_shot_cards(film_root, limit=limit))
                except WebConsoleError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                except Exception as exc:  # noqa: BLE001
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            if parsed.path == "/api/onboarding":
                try:
                    import onboarding

                    self._json(200, onboarding.get_state(film_root))
                except Exception as exc:  # noqa: BLE001
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            if parsed.path.startswith("/media/"):
                try:
                    self._media(_safe_media(film_root, unquote(parsed.path.removeprefix("/media/"))))
                except ReviewUIError as exc:
                    self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            if parsed.path.startswith("/media-lib/"):
                try:
                    from bgm_library import default_library_root

                    lib_root = default_library_root()
                    self._media(
                        _safe_media(lib_root, unquote(parsed.path.removeprefix("/media-lib/")))
                    )
                except ReviewUIError as exc:
                    self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            if parsed.path == "/api/file":
                rel = (parse_qs(parsed.query).get("path") or [""])[0]
                if not rel or rel.startswith("/") or "/../" in rel:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid file path"})
                    return
                try:
                    self._media(_safe_media(film_root, unquote(rel)))
                except ReviewUIError as exc:
                    self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                    return
            # ---- director 总控台 (studio registry) ----
            if parsed.path == "/api/studio":
                try:
                    import studio as studio_mod

                    sd = self.server.studio_dir
                    if sd is None:
                        self._json(200, studio_mod.single_film_view(self.server.active_film))
                    else:
                        payload = studio_mod.build_studio(sd, active_id=self.server.active_film.name)
                        payload["studio_mode"] = True
                        self._json(200, payload)
                except Exception as exc:  # noqa: BLE001
                    self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            if parsed.path.startswith("/api/studio/"):
                self._studio_detail(parsed.path.removeprefix("/api/studio/").strip("/"))
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

        # ---- director 总控台 helpers (studio registry) ----

        def _validate_film_id(self, fid: str):
            """Return the resolved film-root Path, or (status, error) tuple.

            Guards against path traversal: the id must be a bare directory name
            inside the studio dir that actually contains a manifest.json.
            """
            from core.constants import MANIFEST_NAME

            sd = self.server.studio_dir
            if sd is None:
                return (HTTPStatus.BAD_REQUEST, "not in studio mode")
            if not fid or "/" in fid or "\\" in fid or fid in (".", ".."):
                return (HTTPStatus.BAD_REQUEST, "invalid film id")
            cand = (Path(sd) / fid).resolve()
            base = Path(sd).resolve()
            if cand != base and base not in cand.parents:
                return (HTTPStatus.BAD_REQUEST, "film id out of studio dir")
            if not (cand / MANIFEST_NAME).is_file():
                return (HTTPStatus.NOT_FOUND, "film not found in studio")
            return cand

        def _studio_detail(self, fid: str) -> None:
            import studio as studio_mod

            result = self._validate_film_id(fid)
            if isinstance(result, tuple):
                self._json(result[0], {"error": result[1]})
                return
            try:
                self._json(200, studio_mod.summarize_film(result))
            except Exception as exc:  # noqa: BLE001
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def do_POST(self) -> None:
            # Studio mode: route write ops to the active film (see do_GET).
            film_root = getattr(self.server, "active_film", None) or root
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid session token"})
                return
            origin = self.headers.get("Origin", "")
            if origin != f"http://127.0.0.1:{self.server.server_port}":
                self._json(HTTPStatus.FORBIDDEN, {"error": "cross-origin request rejected"})
                return
            try:
                body = self._payload(max_size=MAX_UPLOAD if self.path == "/api/upload" else MAX_BODY)
                if self.path == "/api/action":
                    report = record_action(film_root, **body)
                elif self.path == "/api/settings":
                    report = update_settings(film_root, **body)
                elif self.path == "/api/advance":
                    report = advance_to_next_review(film_root, **body)
                elif self.path == "/api/final-review-input":
                    report = write_review_input(film_root, body)
                elif self.path == "/api/select":
                    import asset_picker

                    report = asset_picker.select_asset(film_root, **body)
                elif self.path == "/api/onboarding/step":
                    import onboarding

                    report = onboarding.submit_step(
                        film_root,
                        body.get("step"),
                        body.get("payload", {}),
                        expected_revision=body.get("expected_revision"),
                    )
                elif self.path == "/api/onboarding/go":
                    import onboarding

                    report = onboarding.go(film_root, expected_revision=body.get("expected_revision"))
                elif self.path == "/api/upload":
                    import onboarding

                    report = onboarding.handle_upload(
                        film_root, filename=body.get("filename", ""), data_url=body.get("data_url", "")
                    )
                elif self.path == "/api/onboarding/brief":
                    import onboarding

                    report = onboarding.submit_brief(
                        film_root,
                        story_text=body.get("story_text", ""),
                        image_paths=body.get("image_paths"),
                        hints=body.get("hints"),
                        expected_revision=body.get("expected_revision"),
                    )
                elif self.path == "/api/onboarding/decompose":
                    import onboarding

                    report = onboarding.decompose(
                        film_root,
                        expected_revision=body.get("expected_revision"),
                        brief=body.get("brief"),
                    )
                elif self.path == "/api/onboarding/plan":
                    import onboarding

                    report = onboarding.save_plan(
                        film_root,
                        body.get("plan", {}),
                        expected_revision=body.get("expected_revision"),
                    )
                elif self.path == "/api/studio/select":
                    import studio as studio_mod

                    result = self._validate_film_id((body.get("id") or "").strip())
                    if isinstance(result, tuple):
                        self._json(result[0], {"error": result[1]})
                        return
                    self.server.active_film = result
                    try:
                        summary = studio_mod.summarize_film(result)
                    except Exception as exc:  # noqa: BLE001
                        self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                        return
                    self._json(
                        200,
                        {"ok": True, "active_film_id": summary["id"], "summary": summary},
                    )
                    return
                elif self.path == "/api/takes/review":
                    from web import takes_api

                    report = takes_api.review_take(
                        film_root,
                        shot_id=str(body.get("shot_id") or ""),
                        take_id=body.get("take_id"),
                        director_status=body.get("director_status"),
                        performance=body.get("performance"),
                        continuity=body.get("continuity"),
                        camera=body.get("camera"),
                        artifacts=body.get("artifacts"),
                        note=body.get("note"),
                        expected_revision=body.get("expected_revision"),
                    )
                elif self.path == "/api/stop":
                    report = {"ok": True, "stopping": True}
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                self._json(200, report)
            except WebConsoleForbidden as exc:
                self._json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
            except (ReviewControlConflict, WebConsoleConflict) as exc:
                self._json(HTTPStatus.CONFLICT, {"error": str(exc)})
            except (
                ReviewControlError,
                ReviewUIError,
                WebConsoleError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    return Handler


def serve(
    root: Path | str | None = None,
    *,
    studio: Path | str | None = None,
    port: int = 0,
) -> dict[str, Any]:
    if studio is not None:
        base = Path(studio).expanduser().resolve()
        if not base.is_dir():
            raise ReviewUIError("studio dir must be an existing directory")
        import studio as studio_mod

        films = studio_mod.discover_films(base)
        if not films:
            raise ReviewUIError("studio dir contains no film roots (subdirs with manifest.json)")
    else:
        if not root:
            raise ReviewUIError("either --root or --studio is required")
        base = Path(root).expanduser().resolve()
        if not base.is_dir():
            raise ReviewUIError("film root must be an existing directory")
        films = None
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(base, token))
    # Studio mode lives on the server instance: which film is "active" for all
    # per-film endpoints, and whether we are in multi-film director mode.
    server.studio_dir = Path(studio).expanduser().resolve() if studio is not None else None
    server.active_film = films[0] if films else base
    session = {
        "kind": "review-ui-session",
        "pid": os.getpid(),
        "port": server.server_port,
        "token": token,
        "root": str(base),
        "studio_mode": studio is not None,
    }
    write_json(_session_path(base), session)
    os.chmod(_session_path(base), 0o600)
    print(
        json.dumps(
            {
                "ok": True,
                "url": f"http://127.0.0.1:{server.server_port}/console?token={token}",
                "root": str(base),
                "studio_mode": studio is not None,
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
    serve_p.add_argument("--root", required=False, default=None)
    serve_p.add_argument(
        "--studio",
        required=False,
        default=None,
        help="Studio directory: serve ALL film roots in director 总控台 (multi-film) mode",
    )
    serve_p.add_argument("--port", type=int, default=0)
    status_p = sub.add_parser("status")
    status_p.add_argument("--root", required=False, default=None)
    status_p.add_argument("--studio", required=False, default=None)
    invite_p = sub.add_parser("invite", help="Create a one-time Telegram-safe review link")
    invite_p.add_argument("--root", required=True)
    invite_p.add_argument("--ttl-seconds", type=int, default=600)
    stop_p = sub.add_parser("stop")
    stop_p.add_argument("--root", required=False, default=None)
    stop_p.add_argument("--studio", required=False, default=None)


def run_review_ui(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.review_ui_action == "serve":
        if args.studio:
            return serve(studio=args.studio, port=args.port), 0
        if args.root:
            return serve(args.root, port=args.port), 0
        raise ReviewUIError("--root or --studio is required")
    if args.review_ui_action == "status":
        if args.studio:
            import studio as studio_mod

            return {
                "ok": True,
                "studio": studio_mod.build_studio(Path(args.studio).expanduser().resolve()),
            }, 0
        return {
            "ok": True,
            "queue": review_queue(args.root),
            "settings": load_settings(args.root),
        }, 0
    if args.review_ui_action == "invite":
        return {"ok": True, **create_invite(args.root, ttl_seconds=args.ttl_seconds)}, 0
    if args.review_ui_action == "stop":
        return stop(args.studio or args.root), 0
    raise ReviewUIError("unknown review-ui action")
