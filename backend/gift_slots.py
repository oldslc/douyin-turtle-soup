"""v6 礼物槽系统 — 9个固定槽位：4效果 + 5难度

主播从全部368+个抖音礼物中自由分配给9个槽位。
每个槽位独立启用/禁用、可随时更换绑定的礼物。"""
import json
import sys
import threading
from pathlib import Path

# ── 9个固定槽位定义 ──
SLOT_DEFINITIONS = [
    # 效果槽（4个）
    {"id": "effect_complete", "group": "effect", "name": "直接通关", "desc": "立即通关当前故事", "default_gift": "梦幻城堡"},
    {"id": "effect_reveal1",   "group": "effect", "name": "揭示一字",  "desc": "随机揭示一个高频实词字", "default_gift": "啤酒"},
    {"id": "effect_reveal_sentence", "group": "effect", "name": "揭示一句", "desc": "揭示完整一句话", "default_gift": "棒棒糖"},
    {"id": "effect_reveal_30p","group": "effect", "name": "揭示30%",  "desc": "立即揭示30%的未揭示内容", "default_gift": "墨镜"},
    # 难度槽（5个）
    {"id": "diff_easy",  "group": "difficulty", "name": "难度-简单", "desc": "下局切换为简单", "default_gift": "鲜花"},
    {"id": "diff_medium","group": "difficulty", "name": "难度-一般", "desc": "下局切换为一般", "default_gift": "玫瑰"},
    {"id": "diff_hard",  "group": "difficulty", "name": "难度-困难", "desc": "下局切换为困难", "default_gift": "跑车"},
    {"id": "diff_hell",  "group": "difficulty", "name": "难度-地狱", "desc": "下局切换为地狱", "default_gift": "嘉年华"},
    {"id": "diff_void",  "group": "difficulty", "name": "难度-无人区", "desc": "下局切换为无人区", "default_gift": "梦幻城堡"},
]

# ── 礼物库（从 gift_icons.json 加载） ──
if getattr(sys, "frozen", False):
    if getattr(sys, '_MEIPASS', None):
        GIFT_LIBRARY_BASE = Path(sys._MEIPASS)
    else:
        GIFT_LIBRARY_BASE = Path(sys.executable).resolve().parent
else:
    GIFT_LIBRARY_BASE = Path(__file__).resolve().parent.parent
GIFT_LIBRARY_PATH = GIFT_LIBRARY_BASE / "gift_icons.json"
# 也尝试从桌面项目加载
ALT_GIFT_LIBRARY_PATH = Path("C:/Users/27871/OneDrive/Desktop/CCcat猜词大挑战/overlay/gift_icons.json")

GIFT_LIBRARY = {}  # {gift_name: {coins, icon}}

def _load_gift_library():
    global GIFT_LIBRARY
    for p in [GIFT_LIBRARY_PATH, ALT_GIFT_LIBRARY_PATH]:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                GIFT_LIBRARY = {k: v for k, v in data.items()}
                print(f"[GiftSlots] 已加载 {len(GIFT_LIBRARY)} 个礼物: {p}")
                return
            except Exception as e:
                print(f"[GiftSlots] 加载礼物库失败 {p}: {e}")
    print("[GiftSlots] 警告: 未找到礼物库文件，使用空库")

_load_gift_library()


class GiftSlotManager:
    """管理9个礼物槽位的状态。线程安全。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._slots = {}  # {slot_id: {gift_name, enabled}}
        self._init_defaults()

    def _init_defaults(self):
        for sd in SLOT_DEFINITIONS:
            self._slots[sd["id"]] = {
                "gift_name": sd["default_gift"],
                "enabled": True,
                "like_mode": False,
                "like_threshold": 500,
            }

    def get_all_slots(self) -> list[dict]:
        """返回所有槽位信息（含定义+当前绑定+点赞模式）。"""
        with self._lock:
            result = []
            for sd in SLOT_DEFINITIONS:
                state = self._slots.get(sd["id"], {})
                gift_name = state.get("gift_name", sd["default_gift"])
                gift_info = GIFT_LIBRARY.get(gift_name, {})
                result.append({
                    "id": sd["id"],
                    "group": sd["group"],
                    "name": sd["name"],
                    "desc": sd["desc"],
                    "gift_name": gift_name,
                    "gift_coins": gift_info.get("coins", 0),
                    "gift_icon": gift_info.get("icon", ""),
                    "enabled": state.get("enabled", True),
                    "like_mode": state.get("like_mode", False),
                    "like_threshold": state.get("like_threshold", 500),
                })
            return result

    def get_slot(self, slot_id: str) -> dict | None:
        for s in self.get_all_slots():
            if s["id"] == slot_id:
                return s
        return None

    def assign_gift(self, slot_id: str, gift_name: str) -> bool:
        """将某个礼物绑定到槽位。"""
        valid_ids = {sd["id"] for sd in SLOT_DEFINITIONS}
        if slot_id not in valid_ids:
            return False
        with self._lock:
            old = self._slots.get(slot_id, {})
            self._slots[slot_id] = {
                "gift_name": gift_name,
                "enabled": old.get("enabled", True),
                "like_mode": old.get("like_mode", False),
                "like_threshold": old.get("like_threshold", 500),
            }
        return True

    def set_enabled(self, slot_id: str, enabled: bool) -> bool:
        valid_ids = {sd["id"] for sd in SLOT_DEFINITIONS}
        if slot_id not in valid_ids:
            return False
        with self._lock:
            if slot_id in self._slots:
                self._slots[slot_id]["enabled"] = enabled
            else:
                self._slots[slot_id] = {"gift_name": "", "enabled": enabled}
        return True

    def set_like_config(self, slot_id: str, like_mode: bool, like_threshold: int = 500) -> bool:
        """设置槽位的点赞模式。"""
        valid_ids = {sd["id"] for sd in SLOT_DEFINITIONS}
        if slot_id not in valid_ids:
            return False
        with self._lock:
            if slot_id not in self._slots:
                sd = next((s for s in SLOT_DEFINITIONS if s["id"] == slot_id), None)
                self._slots[slot_id] = {"gift_name": sd["default_gift"] if sd else "", "enabled": True}
            self._slots[slot_id]["like_mode"] = like_mode
            self._slots[slot_id]["like_threshold"] = max(1, like_threshold)
        return True

    def get_slot_state(self, slot_id: str) -> dict | None:
        """获取某个槽位的运行时状态，供 handle_gift 读取 like 配置。"""
        with self._lock:
            return dict(self._slots.get(slot_id, {})) if slot_id in self._slots else None

    def save_to_db(self, db):
        """将当前所有槽位状态持久化到 SQLite。"""
        import json
        with self._lock:
            raw = json.dumps(self._slots, ensure_ascii=False)
        db.set_setting("gift_slot_states", raw)

    def load_from_db(self, db):
        """从 SQLite 恢复槽位状态。"""
        import json
        raw = db.get_setting("gift_slot_states")
        if raw:
            try:
                data = json.loads(raw)
                with self._lock:
                    for sid, state in data.items():
                        if sid in self._slots:
                            self._slots[sid].update(state)
            except Exception as e:
                print(f"[GiftSlots] 加载失败: {e}")

    def resolve_gift(self, gift_name: str) -> str | None:
        """根据收到的礼物名，返回匹配的槽位ID（效果或难度）。"""
        with self._lock:
            for sd in SLOT_DEFINITIONS:
                state = self._slots.get(sd["id"], {})
                if not state.get("enabled", True):
                    continue
                if state.get("gift_name") == gift_name:
                    return sd["id"]
        return None

    def search_gifts(self, query: str) -> list[dict]:
        """搜索礼物库（主播分配时用），按价值升序排列。"""
        q = query.lower().strip()
        items = list(GIFT_LIBRARY.items())
        if q:
            items = [(k, v) for k, v in items if q in k.lower()]
        items.sort(key=lambda x: x[1].get("coins", 0))
        return [{"name": k, "coins": v.get("coins", 0), "icon": v.get("icon", "")} for k, v in items]


# 全局单例
slot_manager = GiftSlotManager()
