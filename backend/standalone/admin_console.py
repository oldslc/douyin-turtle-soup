"""
控制台 — 独立 EXE
使用 PyWebView 原生窗口显示管理面板（url= 模式加载内嵌 HTTP 服务器）。
支持通过 JS API 动态打开/关闭投屏端（overlay）原生窗口。
所有 API 调用转发到主游戏服务器。
"""
import json
import os
import sys
import threading
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler


# ── 顶层异常处理（防止「闪退」— 崩溃时弹窗或写日志） ──
def _fatal_error_dialog(exc_info):
    """进程级崩溃处理器：优先尝试 Tkinter 弹窗，兜底日志文件。"""
    tb_text = "".join(traceback.format_exception(*exc_info))
    # 日志写到用户目录（EXE 同目录或 APPDATA）
    log_dir = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(log_dir, "crash.log")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(tb_text)
    except Exception:
        pass
    # 尝试 Tkinter 弹窗
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "海龟汤 · 启动失败",
            f"程序启动时发生错误，详细信息已写入：\n{log_path}\n\n"
            f"请将此文件发送给开发者。\n\n{tb_text[:500]}",
        )
        root.destroy()
    except Exception:
        pass
    print(tb_text, file=sys.stderr)

sys.excepthook = _fatal_error_dialog


def _find_webview2_runtime() -> str | None:
    """检测已安装的 WebView2 Runtime 路径（解决注册表键缺失时的 fallback 问题）"""
    candidates = [
        os.environ.get("WEBVIEW2_RUNTIME_PATH"),
        r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application",
        r"C:\Program Files\Microsoft\EdgeWebView\Application",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\EdgeWebView\Application"),
    ]
    for base in candidates:
        if not base or not os.path.isdir(base):
            continue
        versions = sorted(
            (d for d in os.listdir(base)
             if os.path.isdir(os.path.join(base, d)) and d[0].isdigit()),
            key=lambda v: [int(x) for x in v.split(".")],
            reverse=True,
        )
        if versions:
            path = os.path.join(base, versions[0])
            if os.path.isfile(os.path.join(path, "msedgewebview2.exe")):
                return path
    return None

# ── 授权检查（EXE 启动时先弹授权窗口） ──
import license as lic
from auth_window import run_auth

# ── 配置（可通过命令行参数覆盖） ──
BACKEND_URL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BACKEND_URL", "http://localhost:3010")

# 本地 HTTP 服务器端口（在 __main__ 中分配随机端口）
LOCAL_PORT = 0

# ── 加载管理面板 HTML ──
_BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 项目根目录（server.py 所在目录的父目录）
if getattr(sys, 'frozen', False):
    # EXE 路径: backend/standalone/dist/xxx.exe → 上 4 级 = 项目根
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(sys.executable))))
else:
    _PROJECT_ROOT = os.path.dirname(_BASE)  # backend/..

_ADMIN_PY = os.path.join(_BASE, "admin.py")
with open(_ADMIN_PY, encoding="utf-8") as f:
    _src = f.read()
_g = {}
exec(_src, _g)
ADMIN_HTML = _g["ADMIN_HTML"]

# ── 加载投屏 HTML ──
_OVERLAY_PY = os.path.join(_BASE, "overlay.py")
with open(_OVERLAY_PY, encoding="utf-8") as f:
    _src = f.read()
_g = {}
exec(_src, _g)
OVERLAY_HTML = _g["OVERLAY_HTML"]

# ── 注入前端配置（Admin + Overlay） ──
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

_ADMIN_HTML = ADMIN_HTML.replace("</head>", _inject + "</head>")
_ADMIN_HTML = _ADMIN_HTML.replace(
    "(location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws'",
    "window.WS_URL",
)

_OVERLAY_HTML = OVERLAY_HTML.replace("</head>", _inject + "</head>")
_OVERLAY_HTML = _OVERLAY_HTML.replace(
    "(location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws'",
    "window.WS_URL",
)


# ── Overlay JS API ──

class OverlayApi:
    """PyWebView JS API — 从 admin 页面控制 overlay 原生窗口"""
    def __init__(self):
        self._window = None
        self._lock = threading.Lock()

    def open_overlay(self) -> dict:
        """JS 调用：打开或显示 overlay 窗口。返回 dict 自动转为 JSON。"""
        import traceback
        print("[OverlayApi] open_overlay called")
        with self._lock:
            if self._window is not None:
                try:
                    self._window.show()
                    print("[OverlayApi] showing existing overlay")
                    return {"ok": True, "already_open": True}
                except Exception as e:
                    print(f"[OverlayApi] existing window show failed: {e}")
                    self._window = None  # 窗口已被销毁
            import webview
            print("[OverlayApi] creating new overlay window")
            try:
                self._window = webview.create_window(
                    "海龟汤 · 投屏端",
                    url=f"http://127.0.0.1:{LOCAL_PORT}/overlay",
                    width=480, height=854, resizable=True,
                )
                self._window.events.closed += self._on_closed
                print("[OverlayApi] overlay window created successfully")
            except Exception as e:
                print(f"[OverlayApi] create_window FAILED: {e}")
                traceback.print_exc()
                raise
        return {"ok": True}

    def close_overlay(self) -> dict:
        with self._lock:
            if self._window is None:
                return {"ok": True, "already_closed": True}
            self._window.destroy()
            self._window = None
        return {"ok": True}

    def is_overlay_open(self) -> bool:
        return self._window is not None

    def _on_closed(self):
        self._window = None


if __name__ == "__main__":
    # ── 授权检查 ──
    print("[Admin Console] 启动中...", flush=True)
    auth = run_auth()
    if not auth:
        sys.exit(0)

    overlay_api = OverlayApi()

    print("=" * 50)
    print(f"  海龟汤 · 控制台")
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

    # ── 自动启动后端服务器 ──
    import subprocess
    import urllib.request
    import time
    from urllib.parse import urlparse

    # 强制清理旧后端进程，确保加载最新代码
    try:
        _bp = urlparse(BACKEND_URL).port or 3010
        _r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5)
        for _line in _r.stdout.splitlines():
            if f"127.0.0.1:{_bp}" in _line and "LISTENING" in _line:
                _pid = _line.strip().split()[-1]
                subprocess.run(["taskkill", "/f", "/pid", _pid], capture_output=True, timeout=5)
                print(f"  已终止旧后端进程 (PID {_pid})")
                time.sleep(0.5)
                break
    except Exception:
        pass

    _backend_proc = None
    _backend_script = os.path.join(_PROJECT_ROOT, "backend", "server.py")

    def _start_backend(python_exe):
        """启动后端服务器子进程并等待就绪"""
        proc = subprocess.Popen(
            [python_exe, _backend_script],
            cwd=os.path.join(_PROJECT_ROOT, "backend"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("  等待后端就绪...")
        for _ in range(20):
            try:
                urllib.request.urlopen(f"{BACKEND_URL}/api/config", timeout=1)
                print("  后端已就绪")
                return proc
            except Exception:
                time.sleep(0.5)
        print("  [WARN] 后端启动超时（将在后台继续）")
        return proc

    if not getattr(sys, 'frozen', False):
        # 开发模式：使用当前 Python 解释器
        if os.path.isfile(_backend_script):
            try:
                urllib.request.urlopen(f"{BACKEND_URL}/api/config", timeout=2)
                print("  后端已在运行")
            except Exception:
                print("  启动后端服务器...")
                _backend_proc = _start_backend(sys.executable)
    else:
        # EXE 模式：尝试使用系统 Python
        for _py in ['python', 'python3']:
            try:
                subprocess.run([_py, '--version'], capture_output=True, timeout=5)
            except Exception:
                continue
            if os.path.isfile(_backend_script):
                try:
                    urllib.request.urlopen(f"{BACKEND_URL}/api/config", timeout=2)
                    print("  后端已在运行")
                    break
                except Exception:
                    print(f"  启动后端服务器 ({_py})...")
                    _backend_proc = _start_backend(_py)
                    break

    # ── 启动本地 HTTP 服务器（解决 html= 模式的 CORS null origin 问题） ──
    class LocalHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                html = _ADMIN_HTML
            elif self.path == "/overlay":
                html = _OVERLAY_HTML
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        def log_message(self, fmt, *args):
            print(f"  [Local HTTP] {args[0]} {args[1]} {args[2]}")

    LOCAL_PORT = 0
    import socket
    _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _sock.bind(("127.0.0.1", 0))
    LOCAL_PORT = _sock.getsockname()[1]
    _sock.close()

    _local_server = HTTPServer(("127.0.0.1", LOCAL_PORT), LocalHandler)
    _local_thread = threading.Thread(target=_local_server.serve_forever, daemon=True)
    _local_thread.start()
    print(f"  本地服务器: http://127.0.0.1:{LOCAL_PORT}")

    # 创建 admin 窗口（可见，挂载 JS API）
    import webview

    # 确保 WebView2 Runtime 路径正确
    _wv2 = _find_webview2_runtime()
    if _wv2:
        webview.settings['WEBVIEW2_RUNTIME_PATH'] = _wv2
        print(f"  WebView2 Runtime: {_wv2}")
    else:
        print("  [WARN] 未检测到 WebView2 Runtime，将使用 MSHTML（功能受限）")

    # 防止 window.open 触发系统浏览器
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False

    admin_win = webview.create_window(
        "海龟汤 · 控制台",
        url=f"http://127.0.0.1:{LOCAL_PORT}/",
        width=1280, height=800, resizable=True,
        js_api=overlay_api,
    )
    # 启动 PyWebView（阻塞直至所有窗口关闭）
    webview.start(private_mode=True, debug=False)

    _local_server.shutdown()

    if _backend_proc is not None:
        _backend_proc.terminate()
        try:
            _backend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _backend_proc.kill()
        print("  后端已关闭")

    print("[Admin Console] 已退出")
