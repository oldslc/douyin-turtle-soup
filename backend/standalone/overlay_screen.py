"""
投屏端 — 独立 EXE
启动一个轻量 HTTP 服务器，打开浏览器显示投屏画面。
WebSocket 和 API 请求自动转发到主游戏服务器。
"""
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── 授权检查（EXE 启动时先弹授权窗口） ──
import license as lic
from auth_window import run_auth

# ── PyWebView 原生窗口 ──
from webview_host import run_webview

# ── 配置（可通过命令行参数覆盖） ──
BACKEND_URL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BACKEND_URL", "http://localhost:3010")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.environ.get("PORT", "3091"))

# ── 加载投屏 HTML ──
# PyInstaller EXE: 数据文件在 _MEIPASS；直接运行时在 ../overlay.py (parent dir)
_BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_OVERLAY_PY = os.path.join(_BASE, "overlay.py")
with open(_OVERLAY_PY, encoding="utf-8") as f:
    _src = f.read()
_g = {}
exec(_src, _g)
OVERLAY_HTML = _g["OVERLAY_HTML"]

# ── 注入前端配置 ──
_WS_URL = BACKEND_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
_inject = (
    "<script>"
    f"window.SERVER_URL={json.dumps(BACKEND_URL)};"
    f"window.WS_URL={json.dumps(_WS_URL)};"
    "(function(){"
    "var f=window.fetch;"
    "window.fetch=function(u,o){"
    "if(typeof u==='string'&&u.startsWith('/'))u=SERVER_URL+u;"
    "return f.call(window,u,o);"
    "};"
    "})();"
    "</script>"
)
_HTML = OVERLAY_HTML.replace("</head>", _inject + "</head>")
# 替换 WebSocket URL
_HTML = _HTML.replace(
    "(location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws'",
    "window.WS_URL",
)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(_HTML.encode("utf-8"))

    def log_message(self, fmt, *args):
        print(f"[Overlay Screen] {args[0]} {args[1]} {args[2]}")


if __name__ == "__main__":
    # ── 授权检查 ──
    auth = run_auth()
    if not auth:
        sys.exit(0)

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print("=" * 50)
    print(f"  海龟汤 · 投屏端")
    print(f"  {url}")
    print(f"  后端: {BACKEND_URL}")
    if auth.get("source") == "trial":
        remain = lic.format_remaining(auth.get("remaining_seconds", 0))
        print(f"  授权: 试用模式（剩余 {remain}）")
    elif auth.get("source") == "license":
        if auth.get("is_permanent"):
            print(f"  授权: 永久授权")
        else:
            print(f"  授权: 授权码（剩余 {auth.get('remaining_days', 0)} 天）")
    print("=" * 50)
    run_webview(url, "海龟汤 · 投屏端", server=server)
