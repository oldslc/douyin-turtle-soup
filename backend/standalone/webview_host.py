"""
PyWebView 原生窗口封装

替换 `webbrowser.open` + `serve_forever`，提供：
  1. 原生 Windows 窗口（WebView2）
  2. WebView2 缺失时自动回退到浏览器
  3. 关闭窗口 → 停止 http.server，进程退出
"""
import sys
import threading
import webbrowser
from http.server import HTTPServer


def run_webview(url: str, title: str, width=1280, height=800, server: HTTPServer | None = None):
    """
    尝试 PyWebView 原生窗口，失败则回退到浏览器。

    参数:
        url: 加载的本地 URL（如 http://localhost:3090）
        title: 窗口标题
        width/height: 窗口尺寸
        server: 可选，传入后窗口关闭时自动 shutdown
    """
    # 先启动 HTTP 服务器线程（确保服务就绪）
    if server:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

    try:
        import webview
        webview.create_window(title, url, width=width, height=height, resizable=True)
        webview.start(private_mode=True, debug=False)
        # 窗口关闭 → 停止服务器
        if server:
            server.shutdown()
            print(f"[{title}] 窗口已关闭，服务停止")
    except Exception as e:
        print(f"[WebView] 原生窗口不可用 ({e.__class__.__name__}: {e})")
        print(f"[WebView] 回退到浏览器模式")
        webbrowser.open(url)
        if server:
            server.serve_forever()
