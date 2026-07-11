"""
CCcat 海龟汤 — 共享状态模块
从 server.py 提取的所有全局对象、实例和工具函数。
路由模块和 server.py 均从此导入。
"""
import asyncio
import os
import re
import sys
import time
import random as rnd
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from persistent import PersistentDB
from gift_slots import slot_manager, GIFT_LIBRARY
from spam_filter import spam_filter
from theme_manager import theme_manager
from tiers import TIERS, get_tier, check_tier_up, SCORE_BY_DIFFICULTY, DIFFICULTY_MULTIPLIER
from data_soups import SOUPS
import tts_engine

# ── 加载 .env ──
_env_path = (Path(sys.executable).resolve().parent / ".env") if getattr(sys, "frozen", False) else (Path(__file__).resolve().parent.parent / ".env")
if _env_path.exists():
    load_dotenv(str(_env_path), encoding="utf-8")
    print(f"[Config] 已加载 .env: {_env_path}")
else:
    _env_fallback = Path(__file__).resolve().parent.parent / ".env" if getattr(sys, "frozen", False) else None
    if _env_fallback and _env_fallback.exists():
        load_dotenv(str(_env_fallback), encoding="utf-8")
        print(f"[Config] 已加载 .env(后备): {_env_fallback}")
    else:
        print(f"[Config] .env 未发现 ({_env_path})，使用默认配置")

# ── 配置 ──
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")

SERVER_PORT = int(os.getenv("SERVER_PORT", "3010"))
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "3015"))

# 兼容 exe (PyInstaller) 和开发模式
if getattr(sys, "frozen", False):
    if getattr(sys, '_MEIPASS', None):
        PROJECT_ROOT = Path(sys._MEIPASS)
    else:
        PROJECT_ROOT = Path(sys.executable).resolve().parent
    if not (PROJECT_ROOT / "meoo_frontend").exists() and (PROJECT_ROOT.parent / "meoo_frontend").exists():
        PROJECT_ROOT = PROJECT_ROOT.parent
    DATA_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DATA_ROOT = PROJECT_ROOT
FRONTEND_DIR = PROJECT_ROOT / "meoo_frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"

# ── 常量 ──
ANTI_STALL_INTERVAL = 180
ANTI_STALL_DANMAKU = 50
ANTI_STALL_DECAY = 0.8
ANTI_STALL_ENABLED = True
AUTO_START_DELAY = 10
ROUND_TIMEOUT = 300  # 每局最长秒数

MOCK_LEADERBOARD = [
    {"name": "抖音用户_8848", "score": 450},
    {"name": "摸鱼小能手", "score": 320},
    {"name": "吃瓜群众01", "score": 210},
    {"name": "夜猫子剧场", "score": 150},
    {"name": "路过打酱油", "score": 80},
]

FUNCTION_WORDS = {
    "的","了","是","在","和","吗","呢","吧","着","过","得","地","个","一","不","没",
    "有","就","都","而","但","又","如果","因为","所以","然后","于是","向","对","从","到",
    "把","被","给","让","每","只","想","会","能","可以","很","太","非常","已经","正在",
    "曾经","将","要","这","那","你","我","他","她","它","们","上","下","里","外","前",
    "后","中","时","还","也","再","才","刚","做","说","看","来","去",
}

# ── 虚拟货币与礼物商店 ──
GIFT_PRICES = {
    "like": 0,
    "fan_light": 20,
    "popularity": 30,
    "beer": 50,
    "lollipop": 80,
    "sunglasses": 200,
}
GIFT_NAME_MAP = {"like":"like","fan_light":"粉丝灯牌","popularity":"人气票","beer":"啤酒","lollipop":"棒棒糖","sunglasses":"墨镜"}

class CoinSystem:
    def __init__(self):
        self.balances = {}
        self.daily_claimed = {}
        self.vip_status = {}
        self.gift_combo = {}
        self.total_spent = {}

    def get_balance(self, user: str) -> int:
        return self.balances.get(user, 100)

    def add_coins(self, user: str, amount: int):
        current = self.balances.get(user, 100)
        self.balances[user] = max(0, current + amount)

    def spend(self, user: str, amount: int) -> bool:
        if self.get_balance(user) >= amount:
            current = self.balances.get(user, 100)
            self.balances[user] = max(0, current - amount)
            self.total_spent[user] = self.total_spent.get(user, 0) + amount
            return True
        return False

    def claim_daily(self, user: str, today: str) -> bool:
        if self.daily_claimed.get(user) == today:
            return False
        self.daily_claimed[user] = today
        self.add_coins(user, 30)
        return True

    def update_combo(self, user: str) -> dict:
        now = time.time()
        c = self.gift_combo.get(user, {"count":0, "last_time":0, "multiplier":1.0})
        if now - c["last_time"] > 30:
            c = {"count":0, "last_time":0, "multiplier":1.0}
        c["count"] += 1
        c["last_time"] = now
        if c["count"] >= 10: c["multiplier"] = 3.0
        elif c["count"] >= 5: c["multiplier"] = 2.0
        elif c["count"] >= 3: c["multiplier"] = 1.5
        else: c["multiplier"] = 1.0
        self.gift_combo[user] = c
        return c

    def get_leaderboard(self, top_n: int = 5) -> list:
        sorted_users = sorted(self.total_spent.items(), key=lambda x: -x[1])
        return [{"user": u, "total_spent": s} for u, s in sorted_users[:top_n]]

    def check_vip(self, user: str) -> bool:
        return self.vip_status.get(user, 0) > time.time()

    def get_state(self, user: str = "default") -> dict:
        return {
            "balance": self.get_balance(user),
            "vip": self.check_vip(user),
            "combo": self.gift_combo.get(user, {"count":0, "multiplier":1.0}),
        }

    def has_gift(self, user: str, gift_type: str) -> bool:
        price = GIFT_PRICES.get(gift_type, 0)
        if price == 0:
            return True
        return self.get_balance(user) >= price

coins = CoinSystem()

# ── SQLite 持久化层 ──
if getattr(sys, "frozen", False):
    DB_PATH = DATA_ROOT / "backend" / "data" / "persistent.db"
else:
    DB_PATH = Path(__file__).resolve().parent / "data" / "persistent.db"
try:
    db = PersistentDB(DB_PATH)
    print(f"[DB] 持久化就绪: {DB_PATH}")
except Exception as _e:
    print(f"[DB] 初始化失败，回退内存模式: {_e}")
    db = None

# 从持久化存储加载游戏时长配置
if db is not None:
    try:
        saved = db.get_setting("round_timeout")
        if saved is not None:
            ROUND_TIMEOUT = int(saved)
            print(f"[Config] 已加载游戏时长: {ROUND_TIMEOUT}秒")
    except Exception:
        pass
# 从持久化存储恢复礼物槽状态
if db is not None:
    try:
        slot_manager.load_from_db(db)
        print("[GiftSlots] 已恢复槽位状态")
    except Exception as e:
        print(f"[GiftSlots] 加载失败: {e}")

# ── OpenAI 客户端（懒加载）──
_client_instance = None
def get_client():
    global _client_instance
    if _client_instance is None:
        _client_instance = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=20.0)
    return _client_instance
def recreate_client():
    global _client_instance
    _client_instance = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=20.0)

# ── 工具函数 ──
async def llm_classify(text: str, answer: str, keywords: list[str]) -> str:
    try:
        resp = get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "判断弹幕与答案的相关性。只回复：是、不是、是也不是"},
                {"role": "user", "content": f"汤底: {answer}\n关键词: {'、'.join(keywords)}\n弹幕: {text}"},
            ],
            max_tokens=10, temperature=0.1,
            reasoning_effort="none",
        )
        r = resp.choices[0].message.content.strip()
        if "是也不是" in r: return "是也不是"
        elif "是" in r: return "是"
        else: return "不是"
    except Exception as e:
        print(f"[LLM] classify error: {e}")
        return "不是"

DIFFICULTY_NAME_MAP = {"easy":"简单","medium":"一般","hard":"困难","hell":"地狱","void":"无人区","auto":"自适应"}
GIFT_TAUNTS = {
    "like": ["就这？再来点！", "不够不够，继续！", "节奏带起来！"],
    "fan_light": ["灯牌点亮，真爱粉！", "感谢你的灯牌！"],
    "popularity": ["人气票走一波！", "感谢人气票，排面拉满！"],
    "beer": ["啤酒一瓶，思路打开！", "干杯！喝完这瓶想答案！"],
    "lollipop": ["棒棒糖真甜！", "甜到心里了！"],
    "sunglasses": ["墨镜大佬来了！", "全场最靓的仔！"],
}
COMBO_TAUNTS = {3: "连击x3！稳！", 5: "连击x5！大神！", 10: "连击x10！！无敌！"}
SLOT_TAUNTS = {
    "effect_complete": ["直接通关！太强了！", "故事结束，恭喜通关！"],
    "effect_reveal1": ["揭示一字，真相更近了！", "关键字浮现！"],
    "effect_reveal_sentence": ["完整一句揭开！", "迷雾散开一些了！"],
    "effect_reveal_30p": ["大量内容揭示！", "真相即将大白！"],
}

async def llm_hint(qa_history: list[dict], answer: str, keywords: list[str]) -> str:
    """生成提示，引导玩家接近答案"""
    fallback = "想想故事里谁最可疑？"
    try:
        recent = qa_history[-5:] if qa_history else []
        history_text = "\n".join(
            f"玩家提问: {q.get('question','')} → AI判定: {q.get('result','')}"
            for q in recent
        ) if recent else "暂无提问记录"
        resp = get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "你是一个海龟汤提示助手。基于玩家已有的提问和答案，给出一个简短提示（不超过30字），引导玩家思考正确答案方向，但不要直接透露答案。"},
                {"role": "user", "content": f"答案: {answer}\n关键词: {'、'.join(keywords)}\n\n最近提问历史:\n{history_text}\n\n请给出提示："},
            ],
            max_tokens=60, temperature=0.7,
            reasoning_effort="none",
        )
        hint = resp.choices[0].message.content.strip().strip('"').strip("'")
        return hint if hint else fallback
    except Exception as e:
        print(f"[LLM] hint error: {e}")
        return fallback

async def llm_gift_solicit(gift_type: str, context: dict) -> str:
    fallbacks = {
        "人气票": "动动小手送个人气票！",
        "啤酒": "送瓶啤酒，揭示一个关键线索！",
        "棒棒糖": "来个棒棒糖，揭开一句话！",
        "墨镜": "送墨镜，直接通关！",
        "粉丝灯牌": "点亮粉丝灯牌！",
    }
    try:
        resp = get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "生成礼物索要话术，不超过20字"},
                {"role": "user", "content": f"礼物: {gift_type}, 进度: {context.get('revealProgress',0)*100:.0f}%"},
            ],
            max_tokens=30, temperature=0.8,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return fallbacks.get(gift_type, "感谢大家的支持！")

# ── Connection Manager ──
class ConnectionManager:
    def __init__(self):
        self.active: dict[str, "WebSocket"] = {}
    async def connect(self, ws, cid: str):
        await ws.accept()
        self.active[cid] = ws
    def disconnect(self, cid: str):
        self.active.pop(cid, None)
    async def broadcast(self, data: dict):
        dead = []
        for cid, ws in self.active.items():
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.active.pop(cid, None)

manager = ConnectionManager()

# ── 揭示引擎 ──
class RevealEngine:
    @staticmethod
    def is_content_word(char: str) -> bool:
        return bool(re.match(r"[一-龥]", char)) and char not in FUNCTION_WORDS
    @staticmethod
    def init_char_states(text: str) -> list[dict]:
        return [{"char": ch, "revealed": not RevealEngine.is_content_word(ch), "isContent": RevealEngine.is_content_word(ch)} for ch in text]
    @staticmethod
    def reveal_char(states: list[dict], target: str) -> list[dict]:
        return [{**s, "revealed": True} if s["char"] == target else s for s in states]
    @staticmethod
    def get_unrevealed(states: list[dict]) -> list[dict]:
        return [s for s in states if s["isContent"] and not s["revealed"]]
    @staticmethod
    def get_unrevealed_clause(states: list[dict], answer: str) -> list[int]:
        clauses = re.split(r"(?<=[，。！？、；：])", answer)
        idx = 0
        for clause in clauses:
            if not clause.strip():
                idx += len(clause)
                continue
            start = idx
            end = idx + len(clause)
            for i in range(start, end):
                if i < len(states) and states[i]["isContent"] and not states[i]["revealed"]:
                    return list(range(start, end))
            idx = end
        return []
    @staticmethod
    def get_progress(states: list[dict]) -> tuple:
        content = [s for s in states if s["isContent"]]
        revealed = sum(1 for s in content if s["revealed"])
        total = len(content)
        return revealed, total, (revealed/total*100) if total > 0 else 0

# ── 游戏房间 ──
class GameRoom:
    def __init__(self):
        self.reset()
    def reset(self):
        self.phase = "lobby"
        self.soup_text = ""
        self.soup_answer = ""
        self.soup_keywords = []
        self.char_states = []
        self.qa_history = []
        self.gift_log = []
        self.like_progress = {}
        self.next_difficulty = ""
        self.guess_count = 0
        self.start_time = 0
        self.anti_last_reveal = 0
        self.anti_since_reveal = 0
        self.anti_triggers = 0
        self.fanlight_used = 0
        self.max_fanlight = 3
        self.current_difficulty = "medium"
        self.current_soup_id = ""
        self.round_timeout = ROUND_TIMEOUT
        self.remaining = 0
        self.round_correct = 0
        self.round_total = 0
        self.round_correct_times = []
        self.adaptive_bias = 0
        self._auto_start_pending = False
    def to_dict(self):
        _, total, pct = RevealEngine.get_progress(self.char_states)
        return {
            "phase": self.phase, "guessCount": self.guess_count,
            "revealProgress": pct/100, "qaCount": len(self.qa_history),
            "startTime": self.start_time, "remaining": self.remaining,
            "roundTimeout": self.round_timeout,
            "difficulty": self.current_difficulty,
            "difficulty_name": DIFFICULTY_NAME_MAP.get(self.current_difficulty, self.current_difficulty),
            "nextDifficulty": self.next_difficulty,
            "soup_text": getattr(self, "soup_text", ""),
            "char_states": self.char_states,
        }

room = GameRoom()

# ── 自适应难度 ──
DIFFICULTY_ORDER = ["easy", "medium", "hard", "hell", "void"]

def compute_adaptive_difficulty() -> str:
    cur_idx = DIFFICULTY_ORDER.index(room.current_difficulty) if room.current_difficulty in DIFFICULTY_ORDER else 1
    if room.round_total < 5:
        return room.current_difficulty
    correct_rate = room.round_correct / max(room.round_total, 1)
    avg_time = (sum(room.round_correct_times) / max(len(room.round_correct_times), 1)) if room.round_correct_times else 999
    bias = 0
    if correct_rate > 0.6 and avg_time < 60:
        bias = +1
    elif correct_rate > 0.5 and avg_time < 120:
        bias = +1
    elif correct_rate < 0.15 or avg_time > 300:
        bias = -1
    elif correct_rate < 0.3 and avg_time > 180:
        bias = -1
    room.adaptive_bias += bias
    net = max(-1, min(1, room.adaptive_bias))
    new_idx = max(0, min(len(DIFFICULTY_ORDER) - 1, cur_idx + net))
    room.adaptive_bias -= net
    new_diff = DIFFICULTY_ORDER[new_idx]
    print(f"[Adaptive] {room.current_difficulty}→{new_diff} (rate={correct_rate:.0%} avg_t={avg_time:.0f}s bias={room.adaptive_bias})")
    return new_diff

# ── 配置热加载 ──
def reload_config():
    global LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, ROUND_TIMEOUT
    env_path = DATA_ROOT / ".env"
    if not env_path.exists():
        return False, ".env 不存在"
    load_dotenv(str(env_path), encoding="utf-8", override=True)
    LLM_API_KEY = os.getenv("LLM_API_KEY", LLM_API_KEY)
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", LLM_BASE_URL)
    LLM_MODEL = os.getenv("LLM_MODEL", LLM_MODEL)
    try:
        ROUND_TIMEOUT = int(os.getenv("ROUND_TIMEOUT", str(ROUND_TIMEOUT)))
    except ValueError:
        pass
    recreate_client()
    return True, "配置已热加载"

# ── 得分 ──
async def add_score(user: str, delta: int, broadcast: bool = True):
    if delta == 0:
        return
    if db is not None:
        u = db.get_user(user) or {"name": user, "score": 0, "combo": 0, "max_combo": 0,
                                  "total_coins": 0, "total_gifts": 0}
        old_score = u.get("score", 0) or 0
        new_score = max(0, old_score + delta)
        u.update({
            "name": user, "score": new_score,
            "last_seen": time.time(),
            "total_coins": (u.get("total_coins", 0) or 0) + max(0, delta),
        })
        db.upsert_user(u)
        tier_up = check_tier_up(old_score, new_score)
        if tier_up:
            db.record_tier_history(user, tier_up["from"]["name"], tier_up["to"]["name"], new_score)
            if broadcast:
                await manager.broadcast({
                    "type": "tier_up", "user": user,
                    "from_tier": tier_up["from"], "to_tier": tier_up["to"],
                    "delta": tier_up["delta"], "score": new_score,
                    "msg": f"🎉 恭喜 {user} 升级到 {tier_up['to']['name']}！",
                })
        if broadcast:
            await manager.broadcast({
                "type": "score_update", "user": user,
                "score": new_score, "tier": get_tier(new_score),
            })
    else:
        if broadcast:
            await manager.broadcast({
                "type": "score_update", "user": user,
                "score": delta, "tier": get_tier(delta),
            })

# ── 自动揭示与提示 ──
async def auto_reveal_and_hint(reason: str = "timeout"):
    cand = [s for s in room.char_states if s["isContent"] and not s["revealed"]]
    if not cand:
        return
    freq = {}
    for ch in room.soup_answer:
        if RevealEngine.is_content_word(ch):
            freq[ch] = freq.get(ch, 0) + 1
    cand.sort(key=lambda s: freq.get(s["char"], 0), reverse=True)
    target = cand[0]["char"]
    room.char_states = RevealEngine.reveal_char(room.char_states, target)
    room.anti_last_reveal = time.time()
    room.anti_since_reveal = 0
    room.anti_triggers += 1
    await manager.broadcast({"type": "reveal_update", "charStates": room.char_states, "auto": True})
    await manager.broadcast({
        "type": "auto_hint",
        "text": "自动揭示一关键词",
        "reason": reason,
        "revealed": target,
    })
    _, t, p = RevealEngine.get_progress(room.char_states)
    if p >= 100 and room.phase != "complete":
        room.phase = "complete"
        await manager.broadcast({"type": "game_end", "winner": "系统", "charStates": room.char_states})

# ── 签到奖励 ──
SIGNIN_REWARD_MAP = {1: 30, 2: 30, 3: 30, 4: 50, 5: 80, 6: 100, 7: 150}
DEFAULT_SIGNIN_REWARD = 50

# ── 礼物处理 ──
async def handle_gift(msg: dict):
    user = msg.get("nickname","观众")
    gift_name = msg.get("giftName","")
    gift_value = int(msg.get("diamondCount", 0) or 0)
    gift_count = msg.get("count", 1)
    slot_id = slot_manager.resolve_gift(gift_name)
    if not slot_id:
        return
    slot_state = slot_manager.get_slot_state(slot_id)
    is_like_mode = slot_state and slot_state.get("like_mode", False)
    price = 0
    gift_info = GIFT_LIBRARY.get(gift_name, {})
    if is_like_mode:
        threshold = slot_state.get("like_threshold", 500)
        progress = room.like_progress.get(slot_id, 0) + gift_count
        room.like_progress[slot_id] = progress
        await manager.broadcast({"type":"like_update", "slotId": slot_id, "progress": progress, "threshold": threshold})
        if progress >= threshold:
            room.like_progress[slot_id] = 0
            room.anti_last_reveal = time.time()
            room.anti_since_reveal = 0
            room.anti_triggers = 0
            u = RevealEngine.get_unrevealed(room.char_states)
            if u:
                room.char_states = RevealEngine.reveal_char(room.char_states, rnd.choice(u)["char"])
                await manager.broadcast({"type":"reveal_update","charStates":room.char_states})
            r2, t2, p2 = RevealEngine.get_progress(room.char_states)
            if r2 == t2 and t2 > 0 and room.phase != "complete":
                room.phase = "complete"
                await manager.broadcast({"type":"game_end","winner":user,"charStates":room.char_states})

    if not is_like_mode:
        price = gift_info.get("coins", 0)
        if price > 0:
            if not coins.spend(user, price):
                await manager.broadcast({"type":"gift_error","user":user,"msg":f"金币不足！{gift_name}需要{price}金币"})
                return
        combo = coins.update_combo(user)
        room.gift_log.append({"user":user,"giftName":gift_name,"slotId":slot_id,"time":time.time()})
        if gift_value > 0:
            await add_score(user, gift_value)
    else:
        combo = {"count": 0, "multiplier": 1.0}
    if db is not None:
        try:
            db.log_gift(user, gift_name, gift_value or price)
            u = db.get_user(user) or {"name": user}
            db.upsert_user({**u, "name": user, "total_gifts": (u.get("total_gifts",0) or 0) + 1,
                            "last_seen": time.time()})
        except Exception as e:
            print(f"[DB] log_gift error: {e}")
    multiplier = combo["multiplier"]
    bonus_reveal = 0
    if multiplier >= 3.0:
        bonus_reveal = 2
    elif multiplier >= 2.0:
        bonus_reveal = 1

    if slot_id.startswith("diff_"):
        diff_map = {"diff_easy":"easy","diff_medium":"medium","diff_hard":"hard","diff_hell":"hell","diff_void":"void"}
        nd = diff_map.get(slot_id)
        if nd:
            room.next_difficulty = nd
            nd_name = DIFFICULTY_NAME_MAP.get(nd, nd)
            await manager.broadcast({"type":"difficulty_scheduled", "nextDifficulty": nd, "nextDifficultyName": nd_name})
            print(f"[Difficulty] 礼物→槽位{slot_id} = {nd} ({nd_name})")

    elif slot_id == "effect_complete" and not is_like_mode:
        for s in room.char_states:
            if s["isContent"] and not s["revealed"]:
                s["revealed"] = True
        room.phase = "complete"
        await manager.broadcast({"type":"reveal_update","charStates":room.char_states})
        await manager.broadcast({"type":"game_end","winner":user,"charStates":room.char_states})

    elif slot_id == "effect_reveal1":
        revealed_any = False
        for _ in range(1 + bonus_reveal):
            u = RevealEngine.get_unrevealed(room.char_states)
            if u:
                target = rnd.choice(u)["char"]
                room.char_states = RevealEngine.reveal_char(room.char_states, target)
                revealed_any = True
        if revealed_any:
            await manager.broadcast({"type":"reveal_update","charStates":room.char_states})

    elif slot_id == "effect_reveal_sentence":
        revealed_any = False
        for _ in range(1 + bonus_reveal):
            clause = RevealEngine.get_unrevealed_clause(room.char_states, room.soup_answer)
            if clause:
                for ch in set(room.char_states[i]["char"] for i in clause):
                    if RevealEngine.is_content_word(ch):
                        room.char_states = RevealEngine.reveal_char(room.char_states, ch)
                        revealed_any = True
        if revealed_any:
            await manager.broadcast({"type":"reveal_update","charStates":room.char_states})

    elif slot_id == "effect_reveal_30p":
        u = RevealEngine.get_unrevealed(room.char_states)
        if u:
            target_count = max(1, int(len(u) * 0.3))
            targets = rnd.sample(u, min(target_count, len(u)))
            for s in targets:
                room.char_states = RevealEngine.reveal_char(room.char_states, s["char"])
            await manager.broadcast({"type":"reveal_update","charStates":room.char_states})

    r,t,p = RevealEngine.get_progress(room.char_states)
    if r == t and t > 0 and room.phase != "complete":
        room.phase = "complete"
        await manager.broadcast({"type":"game_end","winner":user,"charStates":room.char_states})

    balance = coins.get_balance(user)
    taunt_text = ""
    combo_count = combo["count"]
    if combo_count >= 10:
        taunt_text = COMBO_TAUNTS.get(10, "")
    elif combo_count >= 5:
        taunt_text = COMBO_TAUNTS.get(5, "")
    elif combo_count >= 3:
        taunt_text = COMBO_TAUNTS.get(3, "")
    if not taunt_text:
        taunt_list = SLOT_TAUNTS.get(slot_id, ["感谢赠送！"])
        taunt_text = rnd.choice(taunt_list)
    script = f"感谢{user}的{gift_name}！"
    if taunt_text:
        script += " " + taunt_text
    await manager.broadcast({
        "type":"gift_effect",
        "user":user,
        "giftName":gift_name,
        "slotId":slot_id,
        "coins": gift_value or price,
        "icon": gift_info.get("icon", ""),
        "script": script,
        "taunt": taunt_text,
        "combo": combo["count"],
        "multiplier": multiplier,
        "balance": balance,
        "spent": price,
    })

# ── CosyVoice3 一键部署 ──
_cosyvoice_deploy_lock = asyncio.Lock()
_cosyvoice_deploy_progress = {"step": "", "pct": 0, "text": ""}
_cosyvoice_gpu_cache = None
_cosyvoice_gpu_cache_time = 0

async def _check_gpu_info_async(force: bool = False):
    global _cosyvoice_gpu_cache, _cosyvoice_gpu_cache_time
    now = time.time()
    if not force and _cosyvoice_gpu_cache and (now - _cosyvoice_gpu_cache_time) < 30:
        return _cosyvoice_gpu_cache
    def _detect():
        info = {"cuda": False, "directml": False, "name": "", "vram": ""}
        try:
            result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("\n")[0].split(", ")
                info["cuda"] = True
                info["name"] = parts[0] if len(parts) > 0 else ""
                info["vram"] = parts[1] + " MB" if len(parts) > 1 else ""
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        if not info["cuda"]:
            try:
                import onnxruntime
                if any("Dml" in p for p in onnxruntime.get_available_providers()):
                    info["directml"] = True
                    info["name"] = "DirectML (Windows GPU)"
            except Exception:
                pass
        return info
    loop = asyncio.get_running_loop()
    _cosyvoice_gpu_cache = await loop.run_in_executor(None, _detect)
    _cosyvoice_gpu_cache_time = now
    return _cosyvoice_gpu_cache

def _pip_install_cosyvoice_deps(gpu_info: dict = None):
    installed = set()
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "list", "--format=freeze"],
                           capture_output=True, text=True, timeout=30)
        for line in r.stdout.strip().splitlines():
            pkg_name = line.split("==")[0].strip().lower()
            if pkg_name:
                installed.add(pkg_name)
    except Exception:
        pass
    candidates = [
        "torch>=2.0.0", "torchaudio>=2.0.0",
        "soundfile", "librosa",
        "hydra-core", "omegaconf", "einops",
        "vector-quantize-pytorch", "tensorboard", "lightning",
        "conformer", "diffusers", "modelscope",
        "transformers", "onnx", "protobuf", "pyarrow", "wetext", "pyworld",
        "huggingface_hub",
        # CosyVoice3 运行时必需
        "openai-whisper", "inflect", "HyperPyYAML",
        # Matcha-TTS 依赖（git clone 失败时用 pip 版兜底）
        "matcha-tts",
    ]
    if gpu_info and gpu_info.get("cuda"):
        candidates.append("onnxruntime-gpu==1.18.0")
    elif gpu_info and gpu_info.get("directml"):
        candidates.append("onnxruntime-directml")
    else:
        candidates.append("onnxruntime")
    to_install = []
    for pkg in candidates:
        base = pkg.split(">=")[0].split("==")[0].strip().lower()
        if base not in installed:
            to_install.append(pkg)
    if not to_install:
        print("[TTS Deploy] 所有 Python 依赖已安装，跳过")
        return
    print(f"[TTS Deploy] 安装 {len(to_install)} 个缺失依赖: {to_install}")
    batch_size = 5
    total_batches = (len(to_install) + batch_size - 1) // batch_size
    for i in range(0, len(to_install), batch_size):
        batch = to_install[i:i + batch_size]
        batch_idx = i // batch_size
        pct = 10 + int(30 * (batch_idx / total_batches))
        _cosyvoice_deploy_progress.update({
            "step": "install_deps", "pct": pct,
            "text": f"安装依赖 ({batch_idx+1}/{total_batches}): {batch[0].split('>')[0].split('=')[0]}..."
        })
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"] + batch,
            timeout=1200,
        )

def _safe_rmtree(path):
    """安全删除 git 目录，先删 .git 避免 Windows 文件锁"""
    import shutil
    import time
    for git_dir in [path / ".git"]:
        p = git_dir
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    time.sleep(0.5)
    shutil.rmtree(path, ignore_errors=True)
    if path.exists():
        time.sleep(1)
        try:
            shutil.rmtree(path, onerror=lambda fn, p, ex: None)
        except Exception:
            pass


def _ensure_cosyvoice_repo():
    """克隆 CosyVoice 仓库到 backend/CosyVoiceV7/（如已存在则跳过）"""
    repo_root = Path(__file__).resolve().parent.parent
    cv_dir = repo_root / "backend" / "CosyVoiceV7"
    if cv_dir.exists() and (cv_dir / "cosyvoice").exists():
        return
    # 多源尝试：gitclone.com 镜像优先（国内可访问），GitHub 直连兜底
    urls = [
        "https://gitclone.com/github.com/FunAudioLLM/CosyVoice.git",
        "https://github.com/FunAudioLLM/CosyVoice.git",
        "https://hub.fastgit.xyz/FunAudioLLM/CosyVoice.git",
    ]
    if cv_dir.exists():
        _safe_rmtree(cv_dir)
    cv_dir.mkdir(parents=True, exist_ok=True)
    last_error = ""
    for url in urls:
        try:
            subprocess.check_call(["git", "clone", "--depth", "1", url, str(cv_dir)], timeout=120)
            print(f"[CosyVoice Deploy] 仓库克隆成功: {url}")
            # 克隆 Matcha-TTS 子模块（pip 已装 matcha-tts 兜底，失败不致命）
            matcha_dir = cv_dir / "third_party" / "Matcha-TTS"
            matcha_dir.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.check_call(
                    ["git", "clone", "--depth", "1",
                     "https://gitclone.com/github.com/shivammehta25/Matcha-TTS.git",
                     str(matcha_dir)],
                    timeout=120,
                )
                print("[CosyVoice Deploy] Matcha-TTS 子模块克隆成功")
            except Exception as e:
                print(f"[CosyVoice Deploy] Matcha-TTS 子模块克隆失败 (将使用 pip 版): {e}")
            return
        except Exception as e:
            last_error = str(e)[:120]
            print(f"[CosyVoice Deploy] 克隆失败 ({url}): {e}")
            # 清理失败的克隆
            _safe_rmtree(cv_dir)
            cv_dir.mkdir(parents=True, exist_ok=True)
            continue
    raise RuntimeError(f"无法克隆 CosyVoice 仓库，请检查网络连接 ({last_error})")

def _cosyvoice_model_files_complete(model_dir: Path) -> bool:
    """检查推理所需模型文件是否完整（spk2info.pt 可选，由 CosyVoice 运行时自动生成）"""
    required = [
        "llm.pt", "flow.pt", "hift.pt",
        "campplus.onnx", "speech_tokenizer_v3.onnx",
    ]
    blanken_required = [
        "CosyVoice-BlankEN/model.safetensors",
        "CosyVoice-BlankEN/config.json",
        "CosyVoice-BlankEN/generation_config.json",
        "CosyVoice-BlankEN/merges.txt",
        "CosyVoice-BlankEN/tokenizer_config.json",
        "CosyVoice-BlankEN/vocab.json",
    ]
    for f in required + blanken_required:
        fp = model_dir / f
        if not fp.exists() or fp.stat().st_size < 1024:
            return False
    return True


def _download_cosyvoice_model():
    model_dir = Path(tts_engine.__file__).resolve().parent / "CosyVoiceV7" / "pretrained_models" / "Fun-CosyVoice3-0.5B"
    if _cosyvoice_model_files_complete(model_dir):
        return
    model_dir.mkdir(parents=True, exist_ok=True)

    # 推理不需要的文件（跳过以节省 ~4.1 GB）
    _SKIP_FILES = {
        "llm.rl.pt",                       # RL 微调模型
        "flow.decoder.estimator.fp32.onnx",  # TensorRT 引擎（load_trt=False）
        "speech_tokenizer_v3.batch.onnx",    # 批处理模式
        "README.md",
        "dingding.png",
        ".gitattributes",
    }

    # === 方案 1: ModelScope 逐文件下载（带详细进度） ===
    try:
        from modelscope.hub.api import HubApi
        from modelscope.hub.file_download import model_file_download
        import shutil

        api = HubApi()
        repo_files = api.get_model_files(
            "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
            recursive=True,
        )

        to_download = []
        for f in repo_files:
            fpath = f.get("Path", "")
            fsize = f.get("Size", 0)
            if fsize <= 0:  # 目录
                continue
            if os.path.basename(fpath) in _SKIP_FILES:
                continue
            dest = model_dir / fpath
            if dest.exists() and dest.stat().st_size > 1024:
                continue
            to_download.append((fpath, fsize))

        if to_download:
            to_download.sort(key=lambda x: -x[1])  # 大文件优先
            total = len(to_download)
            total_bytes = sum(s for _, s in to_download)
            dl_bytes = 0
            cache_dir = model_dir.parent / ".msc_download"

            for i, (fpath, fsize) in enumerate(to_download):
                pct = 55 + int(35 * dl_bytes / total_bytes) if total_bytes else 55 + int(35 * i / total)
                fsize_mb = fsize / (1024 * 1024)
                _cosyvoice_deploy_progress.clear()
                _cosyvoice_deploy_progress.update({
                    "step": "download_model",
                    "pct": pct,
                    "text": f"下载模型中 ({i + 1}/{total}): {fpath} ({fsize_mb:.0f} MB)",
                })

                dest = model_dir / fpath
                dest.parent.mkdir(parents=True, exist_ok=True)
                cached = model_file_download(
                    "FunAudioLLM/Fun-CosyVoice3-0.5B-2512", fpath,
                    cache_dir=str(cache_dir),
                )
                shutil.copy2(str(cached), str(dest))
                dl_bytes += fsize

            if cache_dir.exists():
                shutil.rmtree(cache_dir)

        if _cosyvoice_model_files_complete(model_dir):
            return
    except Exception as e:
        print(f"[TTS Deploy] ModelScope 逐文件下载失败: {e}")
        import traceback
        traceback.print_exc()

    # === 方案 2: 通过 huggingface_hub + hf-mirror.com 镜像 ===
    os.environ["HF_ENDPOINT"] = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
    try:
        import huggingface_hub
        huggingface_hub.snapshot_download(
            "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
            local_dir=str(model_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
            ignore_patterns=["llm.rl.pt", "flow.decoder.estimator.fp32.onnx", "speech_tokenizer_v3.batch.onnx"],
        )
        if _cosyvoice_model_files_complete(model_dir):
            return
    except Exception as e:
        print(f"[TTS Deploy] HF 镜像下载失败: {e}")

    # === 方案 3: 直接 HF 直连（需 HF_TOKEN + 接受协议） ===
    try:
        os.environ.pop("HF_ENDPOINT", None)
        import huggingface_hub
        huggingface_hub.snapshot_download(
            "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
            local_dir=str(model_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
            ignore_patterns=["llm.rl.pt", "flow.decoder.estimator.fp32.onnx", "speech_tokenizer_v3.batch.onnx"],
        )
        if _cosyvoice_model_files_complete(model_dir):
            return
    except Exception as e:
        print(f"[TTS Deploy] HF 直连失败: {e}")

    # 所有方案都失败 — 生成详细缺失报告
    missing = []
    for f in ["llm.pt", "flow.pt", "hift.pt", "campplus.onnx", "speech_tokenizer_v3.onnx"]:
        if not (model_dir / f).exists():
            missing.append(f)
    if not (model_dir / "CosyVoice-BlankEN").is_dir():
        missing.append("CosyVoice-BlankEN/ (tokenizer dir)")
    elif not (model_dir / "CosyVoice-BlankEN" / "model.safetensors").exists():
        missing.append("CosyVoice-BlankEN/model.safetensors")
    raise RuntimeError(
        f"模型下载失败，缺失文件: {missing}。请尝试：\n"
        "1. 确认网络能访问 modelscope.cn\n"
        "2. 或手动下载模型到 backend/CosyVoiceV7/pretrained_models/Fun-CosyVoice3-0.5B/\n"
        "3. 如需从 HuggingFace 下载，在 .env 中添加 HF_TOKEN=你的token\n"
        "   (获取: https://huggingface.co/settings/tokens)\n"
        "   需先接受协议: https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512"
    )

async def _run_cosyvoice_deploy():
    global _cosyvoice_deploy_progress
    loop = asyncio.get_running_loop()
    try:
        async with _cosyvoice_deploy_lock:
            gpu_info = await _check_gpu_info_async(force=True)
            _cosyvoice_deploy_progress.clear()
            _cosyvoice_deploy_progress.update({"step": "install_deps", "pct": 10, "text": "安装 Python 依赖..."})
            await loop.run_in_executor(None, lambda: _pip_install_cosyvoice_deps(gpu_info))
            _cosyvoice_deploy_progress.clear()
            _cosyvoice_deploy_progress.update({"step": "install_deps", "pct": 40, "text": "依赖安装完成"})
            _cosyvoice_deploy_progress.clear()
            _cosyvoice_deploy_progress.update({"step": "clone_repo", "pct": 45, "text": "克隆 CosyVoice 仓库..."})
            await loop.run_in_executor(None, _ensure_cosyvoice_repo)
            _cosyvoice_deploy_progress.clear()
            _cosyvoice_deploy_progress.update({"step": "clone_repo", "pct": 50, "text": "CosyVoice 仓库就绪"})
            _cosyvoice_deploy_progress.clear()
            _cosyvoice_deploy_progress.update({"step": "download_model", "pct": 55, "text": "下载模型文件中..."})
            await loop.run_in_executor(None, _download_cosyvoice_model)
            _cosyvoice_deploy_progress.clear()
            _cosyvoice_deploy_progress.update({"step": "download_model", "pct": 90, "text": "模型下载完成"})
            _cosyvoice_deploy_progress.clear()
            _cosyvoice_deploy_progress.update({"step": "verify", "pct": 95, "text": "正在验证..."})
            tts_engine.reset_cosyvoice()
            status = await loop.run_in_executor(None, tts_engine.cosyvoice_status)
            if status["status"] == "ready":
                _cosyvoice_deploy_progress.clear()
                _cosyvoice_deploy_progress.update({"step": "done", "pct": 100, "text": "部署成功！CosyVoice3 已就绪"})
            else:
                _cosyvoice_deploy_progress.clear()
                _cosyvoice_deploy_progress.update({"step": "error", "pct": 0, "text": f"验证失败: {status['detail']}"})
    except Exception as e:
        _cosyvoice_deploy_progress.clear()
        _cosyvoice_deploy_progress.update({"step": "error", "pct": 0, "text": f"部署失败: {str(e)[:200]}"})
        print(f"[CosyVoice Deploy] Error: {e}")
        import traceback
        traceback.print_exc()
