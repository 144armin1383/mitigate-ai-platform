from __future__ import annotations

import argparse
import base64
import datetime as dt
import hmac
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from agent.web.external_runtime_probe import probe_external_runtimes


TASK_TYPES = (
    "inspection",
    "general",
    "wordpress",
    "backend",
    "frontend",
    "api",
    "testing",
    "documentation",
    "infrastructure",
    "deployment",
    "seo",
    "content",
    "security",
    "database",
    "github",
)


PANEL_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>MITIGATE AI Control Panel</title>
<style>
:root{--bg:#0b1020;--panel:#121a2d;--panel2:#182238;--line:#273652;--text:#eaf0ff;--muted:#8fa2c6;--accent:#7c9cff;--ok:#3bd09d;--warn:#f2b84b;--bad:#ff6b7a;--radius:16px}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top right,#17264a 0,#0b1020 38%,#080c17 100%);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}.shell{display:grid;grid-template-columns:260px 1fr;min-height:100vh}.side{border-right:1px solid var(--line);padding:24px 18px;background:rgba(8,12,23,.7);backdrop-filter:blur(12px);position:sticky;top:0;height:100vh}.brand{font-weight:800;letter-spacing:.08em;font-size:18px}.brand small{display:block;font-weight:500;letter-spacing:0;color:var(--muted);margin-top:6px}.nav{margin-top:28px}.nav a{display:block;color:var(--muted);text-decoration:none;padding:11px 12px;border-radius:10px;margin-bottom:6px}.nav a.active,.nav a:hover{background:var(--panel2);color:var(--text)}.health{margin-top:26px;padding:14px;border:1px solid var(--line);border-radius:12px;background:var(--panel)}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;background:var(--warn)}.dot.ok{background:var(--ok)}.main{padding:28px;max-width:1400px;width:100%;margin:0 auto}.top{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:22px}.top h1{font-size:28px;margin:0}.top p{margin:6px 0 0;color:var(--muted)}.grid{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(320px,.8fr);gap:20px}.card{background:rgba(18,26,45,.9);border:1px solid var(--line);border-radius:var(--radius);padding:20px;box-shadow:0 18px 50px rgba(0,0,0,.18)}.card h2{font-size:16px;margin:0 0 16px}.composer textarea{width:100%;min-height:180px;background:#0d1425;border:1px solid var(--line);border-radius:12px;color:var(--text);padding:14px;resize:vertical;font:inherit;outline:none}.composer textarea:focus,.composer select:focus{border-color:var(--accent)}.row{display:flex;gap:12px;align-items:center;margin-top:12px}.row select{background:#0d1425;color:var(--text);border:1px solid var(--line);border-radius:10px;padding:11px 12px;min-width:180px}.btn{border:0;border-radius:10px;padding:11px 16px;font-weight:700;cursor:pointer}.btn.primary{background:var(--accent);color:#071022}.btn.secondary{background:var(--panel2);color:var(--text);border:1px solid var(--line)}.btn:disabled{opacity:.55;cursor:not-allowed}.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.stat{padding:16px;background:#0d1425;border:1px solid var(--line);border-radius:12px}.stat b{font-size:25px;display:block}.stat span{color:var(--muted);font-size:13px}.history{margin-top:20px}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px}table{width:100%;border-collapse:collapse;min-width:760px}th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);font-size:13px}th{color:var(--muted);font-weight:600;background:#0e1627}tr:last-child td{border-bottom:0}tbody tr{cursor:pointer}tbody tr:hover{background:#151f34}.badge{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;font-size:12px;background:#26314a;color:#cbd6ee}.badge.completed{background:rgba(59,208,157,.14);color:#65e7b7}.badge.running,.badge.retrying{background:rgba(242,184,75,.14);color:#ffd378}.badge.failed,.badge.blocked,.badge.cancelled{background:rgba(255,107,122,.14);color:#ff8d99}.detail{white-space:pre-wrap;background:#0d1425;border:1px solid var(--line);border-radius:12px;padding:14px;color:#cbd6ee;max-height:350px;overflow:auto;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace}.toast{position:fixed;right:22px;bottom:22px;background:#17223a;border:1px solid var(--line);padding:12px 16px;border-radius:10px;display:none;max-width:420px}.toast.show{display:block}.provider-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.provider-card{padding:14px;background:#0d1425;border:1px solid var(--line);border-radius:12px}.provider-name{font-weight:750;margin-bottom:7px}.provider-version{font-size:12px;color:var(--muted);margin-top:7px;overflow-wrap:anywhere}.provider-state{font-size:12px;font-weight:700}.provider-state.ok{color:var(--ok)}.provider-state.bad{color:var(--bad)}.provider-actions{display:flex;justify-content:flex-end;margin-top:14px}@media(max-width:900px){.provider-grid{grid-template-columns:1fr}}.muted{color:var(--muted)}@media(max-width:900px){.shell{grid-template-columns:1fr}.side{position:relative;height:auto;border-right:0;border-bottom:1px solid var(--line)}.grid{grid-template-columns:1fr}.main{padding:18px}}
</style>
</head>
<body>
<div class="shell">
  <aside class="side">
    <div class="brand">MITIGATE AI<small>Autonomous Operations</small></div>
    <nav class="nav"><a class="active" href="#control">Agent Control</a><a href="#history">Request History</a><a href="#details">Execution Details</a></nav>
    <div class="health"><div><span id="healthDot" class="dot"></span><strong id="healthText">Checking runtime…</strong></div><div class="muted" id="healthSub" style="margin-top:7px;font-size:12px">127.0.0.1 runtime</div></div>
  </aside>
  <main class="main">
    <div class="top"><div><h1>Agent Control Panel</h1><p>Send work to MITIGATE AI and follow execution from planning to completion.</p></div><button class="btn secondary" id="refreshBtn">Refresh</button></div>
    <section class="grid" id="control">
      <div class="card composer"><h2>New request</h2><textarea id="message" placeholder="Describe what you want the agent to do…"></textarea><div class="row"><select id="taskType"></select><button class="btn primary" id="sendBtn">Send to Agent</button></div><div id="submitInfo" class="muted" style="margin-top:12px;font-size:13px"></div></div>
      <div class="card"><h2>Runtime overview</h2><div class="stats"><div class="stat"><b id="totalCount">0</b><span>Recent requests</span></div><div class="stat"><b id="activeCount">0</b><span>Active</span></div><div class="stat"><b id="doneCount">0</b><span>Completed</span></div><div class="stat"><b id="problemCount">0</b><span>Needs attention</span></div></div><div id="runtimeText" class="muted" style="margin-top:16px;font-size:13px">Loading runtime status…</div></div>
    </section>
    <section class="card history" id="providers">
      <h2>External runtimes</h2>
      <div class="provider-grid" id="providerGrid">
        <div class="muted">Checking OpenHands, OpenClaw and Ruflo…</div>
      </div>
      <div class="provider-actions">
        <button class="btn secondary" id="providerProbeBtn">
          Run runtime diagnostics
        </button>
      </div>
    </section>
    <section class="card history" id="history"><h2>Recent requests</h2><div class="table-wrap"><table><thead><tr><th>Request</th><th>Status</th><th>Mission</th><th>Attempts</th><th>Priority</th></tr></thead><tbody id="requestRows"></tbody></table></div></section>
    <section class="card history" id="details"><h2>Selected request</h2><div id="detailTitle" class="muted" style="margin-bottom:10px">Select a request from the table.</div><div class="detail" id="detailBox">No request selected.</div></section>
  </main>
</div><div class="toast" id="toast"></div>
<script>
const taskTypes = __TASK_TYPES__;
const taskSelect=document.getElementById('taskType');taskTypes.forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;taskSelect.appendChild(o)});taskSelect.value='inspection';
const toast=(msg)=>{const el=document.getElementById('toast');el.textContent=msg;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),3500)};
async function api(path,options={}){const r=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});const t=await r.text();let j={};try{j=JSON.parse(t)}catch{}if(!r.ok)throw new Error(j?.error?.message||j?.error||('HTTP '+r.status));return j}
function badge(s){return `<span class="badge ${s}">${s||'unknown'}</span>`}
async function loadHealth(){try{const h=await api('/api/health');const r=await api('/api/runtime');document.getElementById('healthDot').classList.add('ok');document.getElementById('healthText').textContent='Runtime online';const d=r.data||r;document.getElementById('runtimeText').textContent=`State: ${d.state||'running'} · Worker: ${d.background_worker_running?'running':'unknown'} · Controller: ${d.autonomous_controller_running?'running':'unknown'}`;}catch(e){document.getElementById('healthDot').classList.remove('ok');document.getElementById('healthText').textContent='Runtime unavailable';document.getElementById('runtimeText').textContent=e.message}}

function providerCard(item){
    const ok=!!item.available;
    const state=ok?'Available':'Unavailable';
    const version=item.version||'version unavailable';
    const extra=item.provider==='openhands'
        ?` · LLM: ${item.llm_configured?'configured':'missing'}`
        :(item.functional_probe
            ?` · Diagnostic: ${item.functional_probe}`
            :'');
    return `<div class="provider-card">
      <div class="provider-name">${escapeHtml(item.name||item.provider||'Runtime')}</div>
      <div class="provider-state ${ok?'ok':'bad'}">${state}${escapeHtml(extra)}</div>
      <div class="provider-version">${escapeHtml(version)}</div>
    </div>`;
}

async function loadProviders(deep=false){
    const grid=document.getElementById('providerGrid');
    if(deep)grid.innerHTML='<div class="muted">Running runtime diagnostics…</div>';
    try{
        const j=await api('/api/providers'+(deep?'?deep=1':''));
        const items=j.runtimes||[];
        grid.innerHTML=items.map(providerCard).join('');
        if(!items.length)grid.innerHTML='<div class="muted">No runtime providers reported.</div>';
        if(deep)toast(j.ok?'Runtime diagnostics passed':'One or more runtime diagnostics need attention');
    }catch(e){
        grid.innerHTML=`<div class="muted">${escapeHtml(e.message)}</div>`;
        if(deep)toast('Runtime diagnostics: '+e.message);
    }
}

async function loadRequests(){try{const j=await api('/api/requests?limit=40');const data=j.data||j;const items=data.items||[];document.getElementById('totalCount').textContent=items.length;let active=0,done=0,problem=0;const tbody=document.getElementById('requestRows');tbody.innerHTML='';items.forEach(item=>{const s=item.status||'unknown';if(['pending','running','retrying'].includes(s))active++;if(s==='completed')done++;if(['failed','blocked','cancelled'].includes(s))problem++;const m=item.missions?.[0]?.mission||{};const tr=document.createElement('tr');tr.innerHTML=`<td>${escapeHtml(item.request_id||'')}</td><td>${badge(s)}</td><td>${escapeHtml(m.id||'—')}</td><td>${m.attempts_done??'—'}</td><td>${m.priority??'—'}</td>`;tr.onclick=()=>selectRequest(item.request_id);tbody.appendChild(tr)});document.getElementById('activeCount').textContent=active;document.getElementById('doneCount').textContent=done;document.getElementById('problemCount').textContent=problem;}catch(e){toast('History: '+e.message)}}
function escapeHtml(v){return String(v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
async function selectRequest(id){try{const j=await api('/api/requests/'+encodeURIComponent(id)+'/status');document.getElementById('detailTitle').innerHTML=`<strong>${escapeHtml(id)}</strong> ${badge(j.data?.status||j.status||'unknown')}`;document.getElementById('detailBox').textContent=JSON.stringify(j.data||j,null,2)}catch(e){toast(e.message)}}
async function submit(){const msg=document.getElementById('message').value.trim();if(!msg){toast('Write a request first.');return}const btn=document.getElementById('sendBtn');btn.disabled=true;document.getElementById('submitInfo').textContent='Submitting…';try{const j=await api('/api/requests',{method:'POST',body:JSON.stringify({message:msg,task_type:taskSelect.value})});const d=j.data||j;document.getElementById('submitInfo').textContent=`Accepted · ${d.request_id||''}`;document.getElementById('message').value='';toast('Request accepted by MITIGATE AI');await loadRequests();if(d.request_id)selectRequest(d.request_id)}catch(e){document.getElementById('submitInfo').textContent='Request failed: '+e.message;toast(e.message)}finally{btn.disabled=false}}
document.getElementById('sendBtn').onclick=submit;document.getElementById('refreshBtn').onclick=()=>{loadHealth();loadProviders();loadRequests()};document.getElementById('message').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter')submit()});document.getElementById('providerProbeBtn').onclick=()=>loadProviders(true);loadHealth();loadProviders();loadRequests();setInterval(loadRequests,3000);setInterval(loadHealth,15000);
</script>
</body></html>'''


@dataclass(frozen=True)
class PanelConfig:
    host: str = "127.0.0.1"
    port: int = 8766
    runtime_base_url: str = "http://127.0.0.1:8765"
    project_id: str = "mitigate-ai-platform"
    username: str = "admin"
    password: str = ""
    api_token: str = ""

    def validate(self) -> None:
        if self.host in {"0.0.0.0", "::"}:
            raise ValueError("public_bind_not_allowed")
        if not self.password:
            raise ValueError("missing_panel_password")
        if not self.api_token:
            raise ValueError("missing_api_token")
        if not (1 <= int(self.port) <= 65535):
            raise ValueError("invalid_port")


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request_id() -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"panel-{stamp}-{secrets.token_hex(3)}"


class PanelServer:
    def __init__(self, config: PanelConfig) -> None:
        config.validate()
        self.config = config

    def _upstream(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> tuple[int, bytes, str]:
        url = self.config.runtime_base_url.rstrip("/") + path
        data = None
        headers = {"Authorization": f"Bearer {self.config.api_token}"}
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.status, response.read(), response.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers.get("Content-Type", "application/json")
        except Exception as exc:
            body = json.dumps({"ok": False, "status": 502, "error": {"code": "runtime_unavailable", "message": type(exc).__name__}}).encode("utf-8")
            return 502, body, "application/json"

    def _authorized(self, header: str | None) -> bool:
        if not header or not header.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
            username, password = raw.split(":", 1)
        except Exception:
            return False
        return hmac.compare_digest(username, self.config.username) and hmac.compare_digest(password, self.config.password)

    def handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def _headers(self, code: int, content_type: str, length: int) -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(length))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
                self.send_header("Connection", "close")
                self.end_headers()

            def _write(self, code: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
                self._headers(code, content_type, len(body))
                self.wfile.write(body)
                self.close_connection = True

            def _json(self, code: int, value: dict[str, Any]) -> None:
                self._write(code, json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))

            def _require_auth(self) -> bool:
                if outer._authorized(self.headers.get("Authorization")):
                    return True
                body = b"Authentication required"
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="MITIGATE AI", charset="UTF-8"')
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True
                return False

            def _proxy(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> None:
                code, body, ctype = outer._upstream(path, method=method, payload=payload)
                self._write(code, body, ctype)

            def do_GET(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                if parsed.path == "/healthz":
                    self._json(200, {"ok": True, "status": 200})
                    return
                if not self._require_auth():
                    return
                if parsed.path in {"/", "/index.html"}:
                    html = PANEL_HTML.replace("__TASK_TYPES__", json.dumps(TASK_TYPES)).encode("utf-8")
                    self._write(200, html, "text/html; charset=utf-8")
                    return
                if parsed.path == "/api/health":
                    code, body, ctype = outer._upstream("/health/live")
                    self._write(code, body, ctype)
                    return
                if parsed.path == "/api/runtime":
                    self._proxy("/v1/runtime/status")
                    return
                if parsed.path == "/api/providers":
                    params = urllib.parse.parse_qs(parsed.query)
                    deep = params.get("deep", ["0"])[0] == "1"
                    self._json(
                        200,
                        probe_external_runtimes(deep=deep),
                    )
                    return
                if parsed.path == "/api/requests":
                    query = ("?" + parsed.query) if parsed.query else ""
                    self._proxy("/v1/requests" + query)
                    return
                if parsed.path.startswith("/api/requests/") and parsed.path.endswith("/status"):
                    request_id = parsed.path[len("/api/requests/"):-len("/status")]
                    if not request_id or "/" in request_id:
                        self._json(400, {"ok": False, "error": {"code": "invalid_request_id", "message": "Invalid request id"}})
                        return
                    self._proxy("/v1/requests/" + urllib.parse.quote(request_id, safe="") + "/status")
                    return
                if parsed.path == "/api/executions":
                    query = ("?" + parsed.query) if parsed.query else ""
                    self._proxy("/v1/executions" + query)
                    return
                self._json(404, {"ok": False, "error": {"code": "not_found", "message": "Not found"}})

            def do_POST(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                if not self._require_auth():
                    return
                if parsed.path != "/api/requests":
                    self._json(404, {"ok": False, "error": {"code": "not_found", "message": "Not found"}})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length <= 0 or length > 65536:
                    self._json(400, {"ok": False, "error": {"code": "invalid_request", "message": "Invalid request body"}})
                    return
                try:
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                except Exception:
                    self._json(400, {"ok": False, "error": {"code": "invalid_request", "message": "Malformed JSON"}})
                    return
                message = str(body.get("message") or "").strip() if isinstance(body, dict) else ""
                task_type = str(body.get("task_type") or "general").strip().lower() if isinstance(body, dict) else "general"
                if not message or task_type not in TASK_TYPES:
                    self._json(400, {"ok": False, "error": {"code": "invalid_request", "message": "Message or task type is invalid"}})
                    return
                rid = _request_id()
                payload = {
                    "request_id": rid,
                    "project_id": outer.config.project_id,
                    "conversation_id": "panel-control",
                    "user_message": message,
                    "upload_ids": [],
                    "requested_task_type": task_type,
                    "created_at": _utc_now(),
                }
                self._proxy("/v1/requests", method="POST", payload=payload)

        return Handler

    def serve_forever(self) -> None:
        server = ThreadingHTTPServer((self.config.host, self.config.port), self.handler())
        server.daemon_threads = True
        try:
            server.serve_forever(poll_interval=0.5)
        finally:
            server.server_close()


def build_config_from_env() -> PanelConfig:
    return PanelConfig(
        host=os.environ.get("MITIGATE_AI_PANEL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MITIGATE_AI_PANEL_PORT", "8766")),
        runtime_base_url=os.environ.get("MITIGATE_AI_RUNTIME_BASE_URL", "http://127.0.0.1:8765"),
        project_id=os.environ.get("MITIGATE_PROJECT_ID", "mitigate-ai-platform"),
        username=os.environ.get("MITIGATE_AI_PANEL_USERNAME", "admin"),
        password=os.environ.get("MITIGATE_AI_PANEL_PASSWORD", ""),
        api_token=os.environ.get("MITIGATE_AI_API_TOKEN", ""),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="MITIGATE AI web control panel")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    cfg = build_config_from_env()
    if args.host or args.port:
        cfg = PanelConfig(
            host=args.host or cfg.host,
            port=args.port or cfg.port,
            runtime_base_url=cfg.runtime_base_url,
            project_id=cfg.project_id,
            username=cfg.username,
            password=cfg.password,
            api_token=cfg.api_token,
        )
    cfg.validate()
    PanelServer(cfg).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
