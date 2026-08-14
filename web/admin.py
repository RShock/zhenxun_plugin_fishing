from __future__ import annotations

import hmac
import html
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from tortoise import Tortoise

from zhenxun.configs.config import BotConfig
from zhenxun.services.log import logger


@dataclass(slots=True)
class AdminRequest:
    method: str
    target: str
    headers: dict[str, str]
    body: bytes = b""
    client_host: str = ""

    @property
    def path(self) -> str:
        return urlsplit(self.target).path or "/"

    @property
    def query(self) -> dict[str, str]:
        return {k: v[-1] if v else "" for k, v in parse_qs(urlsplit(self.target).query, keep_blank_values=True).items()}

    @property
    def cookies(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for part in self.headers.get("cookie", "").split(";"):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                result[key] = value
        return result


@dataclass(slots=True)
class AdminResponse:
    status: int
    body: bytes | str = b""
    content_type: str = "text/plain; charset=utf-8"
    headers: dict[str, str] = field(default_factory=dict)

    def body_bytes(self) -> bytes:
        return self.body if isinstance(self.body, bytes) else self.body.encode("utf-8")


_SESSION_TTL = 8 * 60 * 60
_MAX_LOG_VIEW_BYTES = 2 * 1024 * 1024
_MAX_LOG_DOWNLOAD_BYTES = 50 * 1024 * 1024
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_LOG_ROOT = (_PROJECT_ROOT / "log").resolve()
_SESSIONS: dict[str, float] = {}
_READ_SQL = {"select", "show", "describe", "desc", "explain"}
_WRITE_SQL = {"insert", "update", "delete", "replace"}


def _password() -> str:
    return os.getenv("FISHING_ADMIN_PASSWORD", "").strip()


def _enabled() -> bool:
    return os.getenv("FISHING_ADMIN_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _allowed(request: AdminRequest) -> bool:
    raw = os.getenv("FISHING_ADMIN_ALLOWED_IPS", "").strip()
    return not raw or request.client_host in {x.strip() for x in raw.split(",") if x.strip()}


def _base_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'self' 'unsafe-inline'",
    }


def _json(data: Any, status: int = 200, headers: dict[str, str] | None = None) -> AdminResponse:
    return AdminResponse(status, json.dumps(data, ensure_ascii=False, default=str), "application/json; charset=utf-8", headers or {})


def _page(title: str, body: str, status: int = 200) -> AdminResponse:
    document = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{_CSS}</style></head><body><main>{body}</main></body></html>"
    return AdminResponse(status, document, "text/html; charset=utf-8")


def _login(path: str, status: int = 401) -> AdminResponse:
    action = html.escape(path, quote=True)
    return _page("Fishing Admin Login", f"<section class='card narrow'><h1>Fishing Admin</h1><p>Enter the password configured by FISHING_ADMIN_PASSWORD.</p><form method='get' action='{action}'><label>Password<input type='password' name='password' autocomplete='current-password' required autofocus></label><button type='submit'>Sign in</button></form></section>", status)


def _authenticate(request: AdminRequest) -> tuple[bool, str | None, bool]:
    if not _enabled() or not _password() or not _allowed(request):
        return False, None, False
    supplied = request.query.get("password", "")
    if supplied and hmac.compare_digest(supplied, _password()):
        token = secrets.token_urlsafe(32)
        _SESSIONS[token] = time.time() + _SESSION_TTL
        return True, token, True
    token = request.cookies.get("fishing_admin_session", "")
    if token and _SESSIONS.get(token, 0) > time.time():
        return True, None, False
    if token:
        _SESSIONS.pop(token, None)
    return False, None, False


def _finish(request: AdminRequest, response: AdminResponse, token: str | None, used_query: bool) -> AdminResponse:
    response.headers = {**_base_headers(), **response.headers}
    if token:
        response.headers["Set-Cookie"] = f"fishing_admin_session={token}; Path=/fishing-admin; Max-Age={_SESSION_TTL}; HttpOnly; SameSite=Strict"
    if used_query and request.method == "GET" and request.path in {"/fishing-admin", "/fishing-admin/", "/fishing-admin/logs", "/fishing-admin/db"}:
        response.status = 303
        response.body = b""
        response.content_type = "text/plain; charset=utf-8"
        response.headers["Location"] = request.path
    return response


def _safe_log_file(name: str) -> Path | None:
    if not name or Path(name).name != name or Path(name).suffix.lower() != ".log":
        return None
    path = (_LOG_ROOT / name).resolve()
    try:
        path.relative_to(_LOG_ROOT)
    except ValueError:
        return None
    return path if path.is_file() else None


def _log_files() -> list[dict[str, Any]]:
    if not _LOG_ROOT.is_dir():
        return []
    result = []
    for path in sorted(_LOG_ROOT.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            stat = path.stat()
        except OSError:
            continue
        result.append({"name": path.name, "size": stat.st_size, "modified_at": stat.st_mtime})
    return result


def _tail(path: Path, lines: int, keyword: str) -> str:
    with path.open("rb") as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - _MAX_LOG_VIEW_BYTES))
        text = stream.read(_MAX_LOG_VIEW_BYTES).decode("utf-8", errors="replace")
    content = text.splitlines()
    if keyword:
        key = keyword.lower()
        content = [line for line in content if key in line.lower()]
    return "\n".join(content[-max(1, min(lines, 10000)):])


def _body_json(request: AdminRequest) -> dict[str, Any] | None:
    try:
        value = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _sql(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, "sql must be a non-empty string"
    query = value.strip()
    if "\x00" in query or ";" in query.rstrip(";"):
        return None, "multiple SQL statements are not allowed"
    query = query.rstrip(";").strip()
    return query, query.split(None, 1)[0].lower()


async def _tables() -> AdminResponse:
    db = Tortoise.get_connection("default")
    dialect = BotConfig.get_sql_type()
    queries = {
        "mysql": "SELECT table_name AS name, table_comment AS description FROM information_schema.tables WHERE table_schema = DATABASE()",
        "sqlite": "SELECT name, '' AS description FROM sqlite_master WHERE type='table' ORDER BY name",
        "postgres": "SELECT tablename AS name, '' AS description FROM pg_tables WHERE schemaname='public' ORDER BY tablename",
    }
    rows = await db.execute_query_dict(queries.get(dialect, queries["sqlite"]))
    return _json({"dialect": dialect, "tables": rows})


async def _query(request: AdminRequest) -> AdminResponse:
    data = _body_json(request)
    query, first = _sql(data.get("sql") if data else None)
    if not query:
        return _json({"error": first}, 400)
    if first not in _READ_SQL:
        return _json({"error": "read endpoint only accepts SELECT/SHOW/DESCRIBE/EXPLAIN"}, 400)
    params = data.get("params", []) if data else []
    if not isinstance(params, list):
        return _json({"error": "params must be a JSON array"}, 400)
    rows = await Tortoise.get_connection("default").execute_query_dict(query, params)
    return _json({"rows": rows, "count": len(rows)})


async def _execute(request: AdminRequest) -> AdminResponse:
    data = _body_json(request)
    if not data or data.get("confirm") != "EXECUTE":
        return _json({"error": "confirm=EXECUTE is required"}, 400)
    query, first = _sql(data.get("sql"))
    if not query:
        return _json({"error": first}, 400)
    if first not in _WRITE_SQL:
        return _json({"error": "write endpoint only accepts INSERT/UPDATE/DELETE/REPLACE"}, 400)
    params = data.get("params", [])
    if not isinstance(params, list):
        return _json({"error": "params must be a JSON array"}, 400)
    result = await Tortoise.get_connection("default").execute_query(query, params)
    logger.warning(f"Fishing admin database write: {first}", "fishing_admin")
    return _json({"result": result})


_LOG_PAGE = """
<header class='topbar'><div><h1>Bot Logs</h1><p class='muted'>Only <code>log/*.log</code> under the project root is accessible.</p></div><a href='/fishing-admin/db'>Database</a></header>
<section class='card grid'><label>File<select id='file'></select></label><label>Tail lines<input id='lines' type='number' min='1' max='10000' value='300'></label><label>Keyword<input id='keyword'></label><div class='actions'><button id='refresh'>Refresh</button><button id='load'>Load</button><button id='download'>Download</button></div></section>
<section class='card'><pre id='output'>Loading...</pre></section>
<script>
const $=id=>document.getElementById(id); async function files(){const r=await fetch('/fishing-admin/logs/files');if(!r.ok){location.reload();return}const d=await r.json();$('file').innerHTML=d.files.map(x=>`<option value="${encodeURIComponent(x.name)}">${x.name} (${x.size})</option>`).join('');if(d.files.length)load()};async function load(){if(!$('file').value)return;const q=new URLSearchParams({file:decodeURIComponent($('file').value),lines:$('lines').value,keyword:$('keyword').value});const r=await fetch('/fishing-admin/logs/content?'+q);const d=await r.json();$('output').textContent=d.content||d.error||''};$('refresh').onclick=files;$('load').onclick=load;$('download').onclick=()=>{if($('file').value)location.href='/fishing-admin/logs/download?file='+$('file').value};files();
</script>
"""

_DB_PAGE = """
<header class='topbar'><div><h1>Database</h1><p class='muted'>Read queries and explicitly confirmed writes against the default Tortoise connection.</p></div><a href='/fishing-admin/logs'>Logs</a></header>
<section class='card'><button id='tables'>Refresh tables</button><select id='table'></select><span id='status' class='muted'></span></section>
<section class='card'><label>Read SQL<textarea id='read' rows='8' placeholder='SELECT ...'></textarea></label><button id='run-read'>Run query</button><pre id='read-out'></pre></section>
<section class='card danger'><label>Write SQL<textarea id='write' rows='6' placeholder='UPDATE ... WHERE ...'></textarea></label><label>Parameters JSON<input id='params' placeholder='[123, "value"]'></label><label class='confirm'><input id='confirm' type='checkbox'> I understand this changes the server database</label><button id='run-write'>Execute write</button><pre id='write-out'></pre></section>
<script>
const $=id=>document.getElementById(id);const show=(id,x)=>$(id).textContent=typeof x==='string'?x:JSON.stringify(x,null,2);async function tables(){const r=await fetch('/fishing-admin/db/tables');const d=await r.json();if(!r.ok){show('status',d.error);return}$('table').innerHTML=d.tables.map(x=>`<option>${x.name}</option>`).join('');$('status').textContent=d.dialect};$('tables').onclick=tables;$('table').onchange=()=>{$('read').value='SELECT * FROM `'+$('table').value.replace(/`/g,'')+'` LIMIT 100'};$('run-read').onclick=async()=>{const r=await fetch('/fishing-admin/db/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sql:$('read').value})});show('read-out',await r.json())};$('run-write').onclick=async()=>{if(!$('confirm').checked){show('write-out','confirmation required');return}let params=[];try{params=$('params').value?JSON.parse($('params').value):[]}catch(e){show('write-out','invalid parameters JSON');return}const r=await fetch('/fishing-admin/db/execute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sql:$('write').value,params,confirm:'EXECUTE'})});show('write-out',await r.json())};tables();
</script>
"""


async def handle_admin_request(request: AdminRequest) -> AdminResponse | None:
    if not request.path.startswith("/fishing-admin"):
        return None
    authenticated, token, used_query = _authenticate(request)
    if not authenticated:
        if not _allowed(request):
            return _finish(request, _json({"error": "forbidden"}, 403), None, False)
        if not _enabled() or not _password():
            return _finish(request, _json({"error": "admin is disabled"}, 503), None, False)
        return _finish(request, _login(request.path), None, False)

    try:
        path = request.path
        if request.method == "GET" and path in {"/fishing-admin", "/fishing-admin/", "/fishing-admin/logs"}:
            response = _page("Bot Logs", _LOG_PAGE)
        elif request.method == "GET" and path == "/fishing-admin/db":
            response = _page("Database", _DB_PAGE)
        elif request.method == "GET" and path == "/fishing-admin/logs/files":
            response = _json({"files": _log_files()})
        elif request.method == "GET" and path == "/fishing-admin/logs/content":
            target = _safe_log_file(request.query.get("file", ""))
            if not target:
                response = _json({"error": "invalid log file"}, 404)
            else:
                try:
                    lines = int(request.query.get("lines", "300"))
                except ValueError:
                    lines = 300
                response = _json({"file": target.name, "content": _tail(target, lines, request.query.get("keyword", ""))})
        elif request.method == "GET" and path == "/fishing-admin/logs/download":
            target = _safe_log_file(request.query.get("file", ""))
            if not target:
                response = _json({"error": "invalid log file"}, 404)
            elif target.stat().st_size > _MAX_LOG_DOWNLOAD_BYTES:
                response = _json({"error": "log file exceeds 50MB; use tail view"}, 413)
            else:
                response = AdminResponse(200, target.read_bytes(), "text/plain; charset=utf-8", {"Content-Disposition": f'attachment; filename="{target.name}"'})
        elif request.method == "GET" and path == "/fishing-admin/db/tables":
            response = await _tables()
        elif request.method == "POST" and path == "/fishing-admin/db/query":
            response = await _query(request)
        elif request.method == "POST" and path == "/fishing-admin/db/execute":
            response = await _execute(request)
        else:
            response = _json({"error": "not found"}, 404)
    except Exception as exc:
        logger.error(f"Fishing admin request failed: {request.path}", "fishing_admin", e=exc)
        response = _json({"error": f"internal error: {type(exc).__name__}"}, 500)
    return _finish(request, response, token, used_query)


_CSS = """
:root{font-family:system-ui,sans-serif;color:#17202a;background:#f3f5f7}body{margin:0}main{max-width:1280px;margin:auto;padding:24px}.topbar{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}.card{background:white;border-radius:12px;padding:18px;margin:16px 0;box-shadow:0 2px 12px #0001}.narrow{max-width:440px;margin:12vh auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;align-items:end}label{display:flex;flex-direction:column;gap:6px;font-weight:600}input,select,textarea{font:inherit;padding:9px;border:1px solid #ccd3da;border-radius:8px;background:#fff;color:#17202a}textarea{width:100%;box-sizing:border-box;font-family:ui-monospace,monospace}button{border:0;border-radius:8px;padding:10px 14px;background:#2563eb;color:#fff;cursor:pointer;font-weight:600}.actions{display:flex;gap:8px;flex-wrap:wrap}.muted{color:#667085}a{color:#2563eb;text-decoration:none}pre{white-space:pre-wrap;overflow:auto;max-height:65vh;background:#111827;color:#e5e7eb;border-radius:8px;padding:14px;font:13px/1.5 ui-monospace,monospace}.danger{border:2px solid #f59e0b}.confirm{flex-direction:row;align-items:center}.confirm input{width:auto}@media(prefers-color-scheme:dark){:root{color:#e5e7eb;background:#111827}.card{background:#1f2937}input,select,textarea{background:#111827;color:#e5e7eb;border-color:#4b5563}}
"""
