import asyncio
import hashlib
import json
import time
import traceback
from pathlib import Path

import aiohttp
from aiohttp import web

from .command_router import router
from .key_manager import KeyManager

# ── 常量 ──────────────────────────────────────────────────────────────

_WEB_PORT = 4159
_IMAGE_TTL = 600  # 临时图片保留时间（秒）

_STATIC_DIR = Path(__file__).parent / "static"
_TEMP_DIR = _STATIC_DIR / "temp"
_RESOURCES_DIR = Path(__file__).parent.parent / "resources"

_CLIENT_CSS = """
<style>
.fish-list{grid-template-columns:repeat(auto-fill,minmax(85px,1fr))!important}
.item,.upgrade-item{cursor:pointer!important;transition:all .15s!important}
.item:hover,.upgrade-item:hover:not(.max){transform:scale(1.03)!important;box-shadow:0 2px 8px rgba(0,0,0,.15)!important}
</style>
"""

_CLIENT_JS = """
<script>
(function(){
function sendCmd(c){window.parent.postMessage({type:'shop_cmd',command:c},'*')}
document.querySelectorAll('.upgrade-item:not(.max)').forEach(function(el){
el.addEventListener('click',function(){
var c=el.querySelector('.item-cmd');
if(c)sendCmd(c.textContent.replace(/命令:\\s*/,'').trim())
})})
document.querySelectorAll('.item').forEach(function(el){
el.addEventListener('click',function(){
var n=el.querySelector('.item-name');
var name=n?n.textContent.trim():'';
var q=prompt('购买 '+name+' 数量:','1');
if(q&&parseInt(q)>0)sendCmd('鱼店购买 '+name+' '+q)
})})
})()
</script>
"""


# ── HTML 增强 ─────────────────────────────────────────────────────────


def _inject_client_enhancements(html: str) -> str:
    """向商店 HTML 注入 CSS（宽度适配、可点击样式）和 JS（商店点击交互）。"""
    idx = html.rfind("</head>")
    if idx != -1:
        html = html[:idx] + _CLIENT_CSS + html[idx:]
    else:
        html = _CLIENT_CSS + html

    idx2 = html.rfind("</body>")
    if idx2 != -1:
        html = html[:idx2] + _CLIENT_JS + html[idx2:]
    else:
        html = html + _CLIENT_JS

    return html


# ── WebSocket 服务器 ──────────────────────────────────────────────────


class WebSocketServer:
    def __init__(self):
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._task: asyncio.Task | None = None
        self._setup_routes()

    # ── 路由注册 ──

    def _setup_routes(self):
        from .api import get_achievements, get_collection, get_scenes, get_state

        # API / WS / 显式页面入口必须注册在静态路由之前，
        # 否则 prefix="/" 的静态资源会先匹配（目录只显示列表、API 直接 404）
        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_get("/api/image/{filename}", self._image_handler)
        self._app.router.add_get("/api/scenes", get_scenes)
        self._app.router.add_get("/api/scenes/", get_scenes)
        self._app.router.add_get("/api/player/{user_id}/state", get_state)
        self._app.router.add_get("/api/player/{user_id}/achievements", get_achievements)
        self._app.router.add_get("/api/player/{user_id}/collection", get_collection)
        # 目录 URL 默认不会自动打开 index.html，这里强制落到编辑器页面
        self._app.router.add_get(
            "/_lab/track-editor", self._track_editor_index
        )
        self._app.router.add_get(
            "/_lab/track-editor/", self._track_editor_index
        )
        self._app.router.add_static("/api/resource/", _RESOURCES_DIR)
        self._app.router.add_static("/", _STATIC_DIR, show_index=True)

    async def _track_editor_index(self, request: web.Request) -> web.FileResponse:
        path = _STATIC_DIR / "_lab" / "track-editor" / "index.html"
        return web.FileResponse(path)

    # ── WebSocket 处理 ──

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        user_id: str | None = None
        nickname: str = ""

        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue

            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                await ws.send_json({"type": "auth_error", "message": "无效的JSON格式"})
                continue

            cmd_type = data.get("type", "")
            secret = data.get("secret", "")
            command = data.get("command", "")

            if cmd_type == "auth":
                try:
                    result = await self._handle_auth(ws, secret)
                except Exception:
                    traceback.print_exc()
                    await ws.send_json(
                        {
                            "type": "auth_error",
                            "message": "认证时发生内部错误，请查看后台日志",
                        }
                    )
                    return ws
                if result is None:
                    return ws
                user_id, nickname = result
                continue

            if user_id is None:
                await ws.send_json({"type": "auth_error", "message": "请先认证"})
                continue

            if command:
                await self._handle_command(ws, user_id, nickname, command)

        return ws

    async def _handle_auth(
        self, ws: web.WebSocketResponse, secret: str
    ) -> tuple[str, str] | None:
        """处理认证消息。返回 (user_id, nickname) 或 None（表示连接已关闭）。"""
        if not secret:
            await ws.send_json({"type": "auth_error", "message": "请先设置密钥"})
            return None

        user_id = await KeyManager().authenticate(secret)
        if user_id is None:
            await ws.send_json(
                {
                    "type": "auth_error",
                    "message": "密钥无效，请在QQ私聊中使用【注册网页端 密钥】注册",
                }
            )
            return None

        from ..services import get_user

        user = await get_user(user_id)
        nickname = user.nickname if user else ""
        await ws.send_json({"type": "auth_ok", "nickname": nickname})
        return user_id, nickname

    async def _handle_command(
        self, ws: web.WebSocketResponse, user_id: str, nickname: str, command: str
    ):
        """处理指令消息并返回结果。"""
        try:
            raw = await router.route_command(user_id, nickname, command)
        except Exception:
            traceback.print_exc()
            await ws.send_json(
                {
                    "type": "error",
                    "content": "处理指令时发生内部错误，请查看后台日志",
                }
            )
            return

        messages = []
        for item in raw:
            if item["type"] == "html":
                from .command_router import _rewrite_resource_urls

                html = _rewrite_resource_urls(item["content"])
                html = _inject_client_enhancements(html)
                messages.append({"type": "html", "content": html})
            elif item["type"] == "image":
                url = self._save_temp_image(item["data"])
                messages.append({"type": "image_url", "url": url})
            else:
                messages.append(item)

        await ws.send_json({"type": "reply", "messages": messages})

    # ── 临时图片管理 ──

    def _save_temp_image(self, image_data: bytes) -> str:
        _TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self._cleanup_temp()

        h = hashlib.md5(image_data, usedforsecurity=False).hexdigest()
        filename = f"{h}_{int(time.time())}.png"
        filepath = _TEMP_DIR / filename
        filepath.write_bytes(image_data)
        return f"/api/image/{filename}"

    def _cleanup_temp(self):
        if not _TEMP_DIR.exists():
            return
        now = time.time()
        for f in _TEMP_DIR.iterdir():
            if f.is_file() and (now - f.stat().st_mtime) > _IMAGE_TTL:
                try:
                    f.unlink()
                except OSError:
                    pass

    # ── 静态文件 ──

    async def _image_handler(self, request: web.Request) -> web.Response:
        filename = request.match_info["filename"]
        filepath = _TEMP_DIR / filename
        if not filepath.exists():
            return web.Response(status=404, text="Image not found")
        return web.FileResponse(filepath)

    # ── 生命周期 ──

    async def start(self):
        if self._runner is not None:
            return
        _STATIC_DIR.mkdir(parents=True, exist_ok=True)
        _TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", _WEB_PORT)
        await site.start()

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None


# ── 模块级单例 ──

_ws_server = WebSocketServer()


def get_ws_server() -> WebSocketServer:
    return _ws_server
