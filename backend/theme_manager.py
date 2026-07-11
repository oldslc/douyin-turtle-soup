"""主题管理器 — 3 个内置主题 + SQLite 持久化 + HTML 注入

设计:
  - BUILTIN_THEMES: 硬编码 3 个主题的完整 CSS 变量映射
  - ThemeManager: 实例方法操作 SQLite settings 表
  - apply_to_html: 在 <style>:root{} 块中插入 CSS 变量
"""
import sqlite3
import sys
import time
from pathlib import Path
from threading import Lock


# 3 个内置主题的完整 CSS 变量映射
BUILTIN_THEMES = {
    "dark": {
        "id": "dark",
        "name": "经典暗夜",
        "accent": "#00d4ff",
        "vars": {
            "--bg": "#050714",
            "--bg-grad": "linear-gradient(180deg,#0a0e26 0%,#1a0e3a 50%,#260e26 100%)",
            "--card": "rgba(12,16,38,0.88)",
            "--card-border": "rgba(255,255,255,0.08)",
            "--primary": "#00d4ff",
            "--gold": "#fbbf24",
            "--green": "#22c55e",
            "--red": "#ef4444",
            "--yellow": "#eab308",
            "--pink": "#f472b6",
            "--purple": "#a855f7",
            "--text": "#f1f5f9",
            "--text-dim": "#94a3b8",
            "--text-dimmer": "#475569",
            "--bg-image": "url('/static/themes/dark/bg.jpg')",
        },
    },
    "starry": {
        "id": "starry",
        "name": "星空紫",
        "accent": "#a855f7",
        "vars": {
            "--bg": "#0a0418",
            "--bg-grad": "linear-gradient(180deg,#1a0a2e 0%,#2d0a4a 50%,#1a0a2e 100%)",
            "--card": "rgba(30,15,55,0.88)",
            "--card-border": "rgba(168,85,247,0.15)",
            "--primary": "#a855f7",
            "--gold": "#fbbf24",
            "--green": "#22c55e",
            "--red": "#ef4444",
            "--yellow": "#eab308",
            "--pink": "#f472b6",
            "--purple": "#7c3aed",
            "--text": "#f1f5f9",
            "--text-dim": "#c4b5fd",
            "--text-dimmer": "#6d28d9",
            "--bg-image": "url('/static/themes/starry/bg.jpg')",
        },
    },
    "festival": {
        "id": "festival",
        "name": "春节红",
        "accent": "#ef4444",
        "vars": {
            "--bg": "#1a0505",
            "--bg-grad": "linear-gradient(180deg,#3d0a0a 0%,#5a0a0a 50%,#3d0a0a 100%)",
            "--card": "rgba(50,10,10,0.88)",
            "--card-border": "rgba(251,191,36,0.2)",
            "--primary": "#ef4444",
            "--gold": "#fbbf24",
            "--green": "#22c55e",
            "--red": "#dc2626",
            "--yellow": "#fbbf24",
            "--pink": "#f472b6",
            "--purple": "#a855f7",
            "--text": "#fef3c7",
            "--text-dim": "#fbbf24",
            "--text-dimmer": "#92400e",
            "--bg-image": "url('/static/themes/festival/bg.jpg')",
        },
    },
    "ocean": {
        "id": "ocean",
        "name": "深海蓝",
        "accent": "#0ea5e9",
        "vars": {
            "--bg": "#020617",
            "--bg-grad": "linear-gradient(180deg,#0c1e3a 0%,#062044 50%,#021426 100%)",
            "--card": "rgba(12,30,58,0.88)",
            "--card-border": "rgba(14,165,233,0.12)",
            "--primary": "#0ea5e9",
            "--gold": "#fbbf24",
            "--green": "#10b981",
            "--red": "#f43f5e",
            "--yellow": "#eab308",
            "--pink": "#f472b6",
            "--purple": "#8b5cf6",
            "--text": "#e0f2fe",
            "--text-dim": "#7dd3fc",
            "--text-dimmer": "#0c4a6e",
            "--bg-image": "url('/static/themes/ocean/bg.jpg')",
        },
    },
    "forest": {
        "id": "forest",
        "name": "森林绿",
        "accent": "#22c55e",
        "vars": {
            "--bg": "#041a0a",
            "--bg-grad": "linear-gradient(180deg,#0a2e14 0%,#06401a 50%,#042a10 100%)",
            "--card": "rgba(10,30,15,0.88)",
            "--card-border": "rgba(34,197,94,0.15)",
            "--primary": "#22c55e",
            "--gold": "#f59e0b",
            "--green": "#16a34a",
            "--red": "#ef4444",
            "--yellow": "#eab308",
            "--pink": "#f472b6",
            "--purple": "#a855f7",
            "--text": "#ecfdf5",
            "--text-dim": "#6ee7b7",
            "--text-dimmer": "#065f46",
            "--bg-image": "url('/static/themes/forest/bg.jpg')",
        },
    },
    "sakura": {
        "id": "sakura",
        "name": "樱花粉",
        "accent": "#f472b6",
        "vars": {
            "--bg": "#1a0a12",
            "--bg-grad": "linear-gradient(180deg,#2e1020 0%,#4a1530 50%,#2e1020 100%)",
            "--card": "rgba(40,12,25,0.88)",
            "--card-border": "rgba(244,114,182,0.15)",
            "--primary": "#f472b6",
            "--gold": "#fbbf24",
            "--green": "#34d399",
            "--red": "#fb7185",
            "--yellow": "#fde68a",
            "--pink": "#ec4899",
            "--purple": "#c084fc",
            "--text": "#fdf2f8",
            "--text-dim": "#f9a8d4",
            "--text-dimmer": "#831843",
            "--bg-image": "url('/static/themes/sakura/bg.jpg')",
        },
    },
    "aurora": {
        "id": "aurora",
        "name": "极光",
        "accent": "#2dd4bf",
        "vars": {
            "--bg": "#021a1a",
            "--bg-grad": "linear-gradient(180deg,#062e2e 0%,#1a0a3a 50%,#062e2e 100%)",
            "--card": "rgba(6,40,40,0.88)",
            "--card-border": "rgba(45,212,191,0.12)",
            "--primary": "#2dd4bf",
            "--gold": "#fbbf24",
            "--green": "#34d399",
            "--red": "#fb7185",
            "--yellow": "#fde68a",
            "--pink": "#e879f9",
            "--purple": "#a78bfa",
            "--text": "#ccfbf1",
            "--text-dim": "#5eead4",
            "--text-dimmer": "#115e59",
            "--bg-image": "url('/static/themes/aurora/bg.jpg')",
        },
    },
    "cyberpunk": {
        "id": "cyberpunk",
        "name": "赛博朋克",
        "accent": "#e879f9",
        "vars": {
            "--bg": "#0a0010",
            "--bg-grad": "linear-gradient(180deg,#140626 0%,#2a0a3d 50%,#0a0018 100%)",
            "--card": "rgba(20,6,38,0.9)",
            "--card-border": "rgba(232,121,249,0.18)",
            "--primary": "#e879f9",
            "--gold": "#facc15",
            "--green": "#22d3ee",
            "--red": "#f43f5e",
            "--yellow": "#fef08a",
            "--pink": "#f472b6",
            "--purple": "#c084fc",
            "--text": "#f5f3ff",
            "--text-dim": "#d8b4fe",
            "--text-dimmer": "#6b21a8",
            "--bg-image": "url('/static/themes/cyberpunk/bg.jpg')",
        },
    },
    "sunset": {
        "id": "sunset",
        "name": "落日橙",
        "accent": "#f97316",
        "vars": {
            "--bg": "#1a0802",
            "--bg-grad": "linear-gradient(180deg,#3a1406 0%,#5a1a0a 50%,#3a0e04 100%)",
            "--card": "rgba(50,12,4,0.88)",
            "--card-border": "rgba(249,115,22,0.15)",
            "--primary": "#f97316",
            "--gold": "#f59e0b",
            "--green": "#22c55e",
            "--red": "#ef4444",
            "--yellow": "#fbbf24",
            "--pink": "#f472b6",
            "--purple": "#a855f7",
            "--text": "#fff7ed",
            "--text-dim": "#fdba74",
            "--text-dimmer": "#9a3412",
            "--bg-image": "url('/static/themes/sunset/bg.jpg')",
        },
    },
    "lavender": {
        "id": "lavender",
        "name": "薰衣草",
        "accent": "#818cf8",
        "vars": {
            "--bg": "#0a0a1a",
            "--bg-grad": "linear-gradient(180deg,#14143a 0%,#2a1a4a 50%,#14143a 100%)",
            "--card": "rgba(16,14,40,0.88)",
            "--card-border": "rgba(129,140,248,0.12)",
            "--primary": "#818cf8",
            "--gold": "#fbbf24",
            "--green": "#34d399",
            "--red": "#f87171",
            "--yellow": "#fde68a",
            "--pink": "#f0abfc",
            "--purple": "#a78bfa",
            "--text": "#eef2ff",
            "--text-dim": "#a5b4fc",
            "--text-dimmer": "#3730a3",
            "--bg-image": "url('/static/themes/lavender/bg.jpg')",
        },
    },
    "gold": {
        "id": "gold",
        "name": "鎏金",
        "accent": "#f59e0b",
        "vars": {
            "--bg": "#080808",
            "--bg-grad": "linear-gradient(180deg,#1a1200 0%,#0d0d0d 50%,#1a0e00 100%)",
            "--card": "rgba(20,15,5,0.88)",
            "--card-border": "rgba(245,158,11,0.15)",
            "--primary": "#f59e0b",
            "--gold": "#fbbf24",
            "--green": "#10b981",
            "--red": "#ef4444",
            "--yellow": "#fde68a",
            "--pink": "#f472b6",
            "--purple": "#a78bfa",
            "--text": "#fffbe6",
            "--text-dim": "#d4a843",
            "--text-dimmer": "#78350f",
            "--bg-image": "url('/static/themes/gold/bg.jpg')",
        },
    },
    "neon": {
        "id": "neon",
        "name": "霓虹",
        "accent": "#22d3ee",
        "vars": {
            "--bg": "#050505",
            "--bg-grad": "linear-gradient(180deg,#0a0a1a 0%,#1a0a0a 50%,#0a0a1a 100%)",
            "--card": "rgba(10,10,20,0.9)",
            "--card-border": "rgba(34,211,238,0.15)",
            "--primary": "#22d3ee",
            "--gold": "#facc15",
            "--green": "#4ade80",
            "--red": "#f87171",
            "--yellow": "#fde047",
            "--pink": "#f472b6",
            "--purple": "#c084fc",
            "--text": "#ffffff",
            "--text-dim": "#67e8f9",
            "--text-dimmer": "#164e63",
            "--bg-image": "url('/static/themes/neon/bg.jpg')",
        },
    },
    "mocha": {
        "id": "mocha",
        "name": "摩卡",
        "accent": "#d97706",
        "vars": {
            "--bg": "#0d0805",
            "--bg-grad": "linear-gradient(180deg,#1a120a 0%,#2a1a0e 50%,#1a0e08 100%)",
            "--card": "rgba(26,16,10,0.88)",
            "--card-border": "rgba(217,119,6,0.15)",
            "--primary": "#d97706",
            "--gold": "#f59e0b",
            "--green": "#65a30d",
            "--red": "#dc2626",
            "--yellow": "#fbbf24",
            "--pink": "#f9a8d4",
            "--purple": "#9333ea",
            "--text": "#fef3c7",
            "--text-dim": "#b8860b",
            "--text-dimmer": "#78350f",
            "--bg-image": "url('/static/themes/mocha/bg.jpg')",
        },
    },
    "pearl": {
        "id": "pearl",
        "name": "珍珠",
        "accent": "#94a3b8",
        "vars": {
            "--bg": "#0f1118",
            "--bg-grad": "linear-gradient(180deg,#1a1e2e 0%,#0f1520 50%,#1a1e2e 100%)",
            "--card": "rgba(20,24,36,0.88)",
            "--card-border": "rgba(148,163,184,0.12)",
            "--primary": "#94a3b8",
            "--gold": "#fbbf24",
            "--green": "#34d399",
            "--red": "#f87171",
            "--yellow": "#fde68a",
            "--pink": "#f9a8d4",
            "--purple": "#a78bfa",
            "--text": "#f8fafc",
            "--text-dim": "#cbd5e1",
            "--text-dimmer": "#475569",
            "--bg-image": "url('/static/themes/pearl/bg.jpg')",
        },
    },
    "peach": {
        "id": "peach",
        "name": "蜜桃",
        "accent": "#fb923c",
        "vars": {
            "--bg": "#120805",
            "--bg-grad": "linear-gradient(180deg,#2a140a 0%,#3a1a10 50%,#2a0e08 100%)",
            "--card": "rgba(40,14,10,0.88)",
            "--card-border": "rgba(251,146,60,0.15)",
            "--primary": "#fb923c",
            "--gold": "#fbbf24",
            "--green": "#34d399",
            "--red": "#f43f5e",
            "--yellow": "#fde68a",
            "--pink": "#fda4af",
            "--purple": "#c084fc",
            "--text": "#fff7ed",
            "--text-dim": "#fdba74",
            "--text-dimmer": "#9a3412",
            "--bg-image": "url('/static/themes/peach/bg.jpg')",
        },
    },
}

VALID_IDS = set(BUILTIN_THEMES.keys())


class ThemeManager:
    """主题管理器单例。

    Args:
        db_path: SQLite 数据库路径。None 时使用默认 backend/data/v6.db。
    """

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            if getattr(sys, "frozen", False):
                if getattr(sys, '_MEIPASS', None):
                    base = Path(sys._MEIPASS)
                else:
                    base = Path(sys.executable).resolve().parent
            else:
                base = Path(__file__).resolve().parent
            db_path = str(base / "data" / "v6.db")
        self.db_path = db_path
        self._lock = Lock()
        # 确保 data 目录存在 + 表已建
        self._ensure_db()

    def _ensure_db(self):
        """确保父目录存在 + settings 表已建（幂等，每次操作前调用）"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at REAL
        )""")
        conn.commit()
        conn.close()

    def get_active(self) -> str:
        """返回当前活动主题 id，越权值回退到 dark。"""
        with self._lock:
            try:
                self._ensure_db()
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                row = conn.execute(
                    "SELECT value FROM settings WHERE key='active_theme'"
                ).fetchone()
                conn.close()
            except Exception:
                return "dark"
        if not row or row[0] not in VALID_IDS:
            return "dark"
        return row[0]

    def set_active(self, theme_id: str) -> None:
        """写入活动主题。无效 id 静默忽略（白名单在 get_active 处生效）。"""
        if theme_id not in VALID_IDS:
            return
        with self._lock:
            self._ensure_db()
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute(
                "INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES(?,?,?)",
                ("active_theme", theme_id, time.time()),
            )
            conn.commit()
            conn.close()

    def get_theme_dict(self, theme_id: str) -> dict:
        """返回某主题的完整 CSS 变量字典。"""
        return BUILTIN_THEMES[theme_id]["vars"]

    def list_themes(self) -> list[dict]:
        """返回 [{\"id\", \"name\", \"accent\", \"preview\"}, ...]"""
        return [
            {"id": t["id"], "name": t["name"], "accent": t["accent"],
             "preview": t["vars"]["--bg-grad"]}
            for t in BUILTIN_THEMES.values()
        ]

    def apply_to_html(self, html: str, theme_id: str) -> str:
        """在 HTML <style>:root{} 块中注入 CSS 变量。

        策略: 找到第一个 `<style>` 标签后的 `:root{...}` 块，替换为新的。
        若未找到或 theme_id 无效，返回原 HTML。
        """
        if theme_id not in VALID_IDS:
            return html
        vars_dict = BUILTIN_THEMES[theme_id]["vars"]
        # 生成 :root CSS
        css_lines = [f"  {k}: {v};" for k, v in vars_dict.items()]
        css_block = ":root {\n" + "\n".join(css_lines) + "\n}"
        # 替换第一个 :root{...} 块（支持多行）
        import re
        pattern = r":root\s*\{[^}]*\}"
        new_html, n = re.subn(pattern, css_block, html, count=1)
        if n == 0:
            # 没找到 :root 块，在第一个 </style> 前插入
            new_html = html.replace("</style>", f"{css_block}\n</style>", 1)
        return new_html


# 模块级单例
theme_manager = ThemeManager()
