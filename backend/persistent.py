"""SQLite 持久化层 — 用户积分 / 段位历史 / 签到 / 礼物别名 / 触发器 / 礼物日志

采用 WAL 模式，与原版 CCcat 一致。所有写操作带 try/except，启动失败时
上层可回退到内存模式。
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

DEFAULT_ALIASES = [
    # alias, gifts(逗号分隔真实礼物名), effect, enabled
    ("点赞", "点赞,点赞动画", "like", 1),
    ("粉丝灯牌", "粉丝灯牌,灯牌,粉丝团", "fan_light", 1),
    ("人气票", "人气票,人气,助力", "popularity", 1),
    ("啤酒", "啤酒,啤酒瓶,啤酒杯,干杯", "beer", 1),
    ("棒棒糖", "棒棒糖,糖,大棒棒糖", "lollipop", 1),
    ("墨镜", "墨镜,墨镜侠,酷酷墨镜", "sunglasses", 1),
    # 合并示例：玫瑰类礼物统一触发 popularity
    ("玫瑰", "玫瑰花,玫瑰雨,玫瑰棒棒糖,红玫瑰", "popularity", 1),
]

DEFAULT_TRIGGERS = [
    # type, target, effect, value, enabled
    ("gift", "啤酒", "beer", "", 1),
    ("gift", "棒棒糖", "lollipop", "", 1),
    ("gift", "墨镜", "sunglasses", "", 1),
    ("gift", "人气票", "popularity", "", 1),
    ("gift", "粉丝灯牌", "fan_light", "", 1),
    ("gift", "点赞", "like", "", 1),
    ("gift", "*", "like", "100", 1),       # 任意礼物 +100 赞（占位）
    ("follow", "*", "bonus_score", "50", 1),  # 关注 +50 分
]


class PersistentDB:
    """线程安全的 SQLite 持久化封装。"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # check_same_thread=False：FastAPI 在事件loop线程中使用
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.init_tables()
        self._seed_defaults()

    # ── 建表 ──
    def init_tables(self):
        with self._lock:
            cur = self.conn.cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    name TEXT PRIMARY KEY,
                    score INTEGER DEFAULT 0,
                    combo INTEGER DEFAULT 0,
                    max_combo INTEGER DEFAULT 0,
                    last_seen REAL,
                    achievements TEXT,
                    total_gifts INTEGER DEFAULT 0,
                    total_coins INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS tier_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    from_tier TEXT,
                    to_tier TEXT,
                    score INTEGER,
                    timestamp REAL
                );
                CREATE TABLE IF NOT EXISTS checkins (
                    name TEXT PRIMARY KEY,
                    last_day TEXT,
                    streak INTEGER DEFAULT 0,
                    total_days INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS gift_aliases (
                    alias TEXT PRIMARY KEY,
                    gifts TEXT,
                    effect TEXT,
                    enabled INTEGER DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS triggers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT,
                    target TEXT,
                    effect TEXT,
                    value TEXT,
                    enabled INTEGER DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS gift_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    gift_name TEXT,
                    amount INTEGER,
                    timestamp REAL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            self.conn.commit()

    def _seed_defaults(self):
        """首次启动时插入默认别名与触发器。"""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM gift_aliases")
            if cur.fetchone()[0] == 0:
                cur.executemany(
                    "INSERT OR IGNORE INTO gift_aliases(alias,gifts,effect,enabled) VALUES(?,?,?,?)",
                    DEFAULT_ALIASES,
                )
            cur.execute("SELECT COUNT(*) FROM triggers")
            if cur.fetchone()[0] == 0:
                cur.executemany(
                    "INSERT INTO triggers(type,target,effect,value,enabled) VALUES(?,?,?,?,?)",
                    DEFAULT_TRIGGERS,
                )
            self.conn.commit()

    # ── 用户 ──
    def get_user(self, name: str) -> dict | None:
        with self._lock:
            cur = self.conn.execute("SELECT * FROM users WHERE name=?", (name,))
            row = cur.fetchone()
            return dict(row) if row else None

    def upsert_user(self, data: dict):
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO users(name,score,combo,max_combo,last_seen,achievements,total_gifts,total_coins)
                VALUES(:name,:score,:combo,:max_combo,:last_seen,:achievements,:total_gifts,:total_coins)
                ON CONFLICT(name) DO UPDATE SET
                    score=excluded.score,
                    combo=excluded.combo,
                    max_combo=excluded.max_combo,
                    last_seen=excluded.last_seen,
                    achievements=excluded.achievements,
                    total_coins=excluded.total_coins,
                    total_gifts=excluded.total_gifts
                """,
                {
                    "name": data.get("name"),
                    "score": data.get("score", 0),
                    "combo": data.get("combo", 0),
                    "max_combo": data.get("max_combo", 0),
                    "last_seen": data.get("last_seen", time.time()),
                    "achievements": data.get("achievements"),
                    "total_coins": data.get("total_coins", 0),
                    "total_gifts": data.get("total_gifts", 0),
                },
            )
            self.conn.commit()

    def get_top_users(self, limit: int = 10) -> list[dict]:
        with self._lock:
            cur = self.conn.execute(
                "SELECT * FROM users ORDER BY score DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in cur.fetchall()]

    def record_tier_history(self, name: str, from_tier: str, to_tier: str, score: int):
        with self._lock:
            self.conn.execute(
                "INSERT INTO tier_history(name,from_tier,to_tier,score,timestamp) VALUES(?,?,?,?,?)",
                (name, from_tier, to_tier, score, time.time()),
            )
            self.conn.commit()

    # ── 签到 ──
    def get_checkin(self, name: str) -> dict | None:
        with self._lock:
            cur = self.conn.execute("SELECT * FROM checkins WHERE name=?", (name,))
            row = cur.fetchone()
            return dict(row) if row else None

    def upsert_checkin(self, data: dict):
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO checkins(name,last_day,streak,total_days)
                VALUES(:name,:last_day,:streak,:total_days)
                ON CONFLICT(name) DO UPDATE SET
                    last_day=excluded.last_day,
                    streak=excluded.streak,
                    total_days=excluded.total_days
                """,
                {
                    "name": data.get("name"),
                    "last_day": data.get("last_day"),
                    "streak": data.get("streak", 0),
                    "total_days": data.get("total_days", 0),
                },
            )
            self.conn.commit()

    # ── 礼物别名 ──
    def get_aliases(self) -> list[dict]:
        with self._lock:
            cur = self.conn.execute("SELECT * FROM gift_aliases ORDER BY alias")
            return [dict(r) for r in cur.fetchall()]

    def get_enabled_aliases(self) -> list[dict]:
        with self._lock:
            cur = self.conn.execute(
                "SELECT * FROM gift_aliases WHERE enabled=1 ORDER BY alias"
            )
            return [dict(r) for r in cur.fetchall()]

    def upsert_alias(self, alias: str, gifts: str, effect: str, enabled: int = 1):
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO gift_aliases(alias,gifts,effect,enabled) VALUES(?,?,?,?)
                ON CONFLICT(alias) DO UPDATE SET gifts=excluded.gifts,effect=excluded.effect,enabled=excluded.enabled
                """,
                (alias, gifts, effect, enabled),
            )
            self.conn.commit()

    def del_alias(self, alias: str):
        with self._lock:
            self.conn.execute("DELETE FROM gift_aliases WHERE alias=?", (alias,))
            self.conn.commit()

    # ── 触发器 ──
    def get_triggers(self) -> list[dict]:
        with self._lock:
            cur = self.conn.execute("SELECT * FROM triggers ORDER BY id")
            return [dict(r) for r in cur.fetchall()]

    def get_enabled_triggers(self) -> list[dict]:
        with self._lock:
            cur = self.conn.execute("SELECT * FROM triggers WHERE enabled=1 ORDER BY id")
            return [dict(r) for r in cur.fetchall()]

    def add_trigger(self, type_: str, target: str, effect: str, value: str = "", enabled: int = 1) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO triggers(type,target,effect,value,enabled) VALUES(?,?,?,?,?)",
                (type_, target, effect, value, enabled),
            )
            self.conn.commit()
            return cur.lastrowid

    def del_trigger(self, tid: int):
        with self._lock:
            self.conn.execute("DELETE FROM triggers WHERE id=?", (tid,))
            self.conn.commit()

    # ── 礼物日志 ──
    def log_gift(self, name: str, gift_name: str, amount: int):
        with self._lock:
            self.conn.execute(
                "INSERT INTO gift_log(name,gift_name,amount,timestamp) VALUES(?,?,?,?)",
                (name, gift_name, amount, time.time()),
            )
            self.conn.commit()

    def close(self):
        with self._lock:
            self.conn.close()

    # ── 配置键值存储 ──
    def get_setting(self, key: str, default=None):
        with self._lock:
            cur = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = cur.fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str):
        with self._lock:
            self.conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self.conn.commit()