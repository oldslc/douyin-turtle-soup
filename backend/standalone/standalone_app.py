"""
独立集成版 — 控制面板 + 投屏端
完全自包含，无需启动 server.py（端口 3010）。

用法:
    python standalone_app.py              # 默认端口 3090
    python standalone_app.py --port 8080  # 指定端口
    python standalone_app.py --backend http://myserver:3010  # 连接外部后端

特性:
    - 内置 HTTP 服务器提供 admin/overlay 页面
    - 内置 WebSocket 处理游戏状态
    - 默认模拟 API 响应（无真实游戏后端也可用）
    - 可指定外部后端（生产模式）
    - PyWebView 原生窗口
"""
import asyncio
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path
import urllib.error
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote



# ── 授权模块 ──
import license as lic

# ── 可写配置存储（替代硬编码 lambda） ──
_game_config = {"roundTimeout": 600}
_anti_stall_config = {"enabled": True, "interval": 180, "danmaku": 50}
_banned_words: list = [
    "加微信", "QQ群", "加群", "私聊", "扫码", "二维码",
    "进群", "拉群", "微信号", "手机号", "电话",
    "代刷", "代练", "外挂", "辅助", "脚本", "刷屏器",
    "赌博", "赌场", "博彩",
    "色情", "黄片", "A片",
    "政治", "领导人", "共产党", "习近平",
    "卖号", "买号", "租号", "交易",
    "广告", "推广", "招代理",
    "骗子", "骗钱", "诈骗",
]
_slot_overrides: dict = {}

# ── 防卡死 / 计时器 / 自动下一局 状态 ──
_anti_last_reveal = 0.0
_danmaku_since_reveal = 0
_anti_triggers = 0
_auto_start_pending = False
AUTO_START_DELAY = 10
ANTI_STALL_DECAY = 0.8
_background_tasks: set = set()

# ── 字符判断 ──
FUNCTION_WORDS = frozenset("的了在是我有不人被这对于把和就这那而或与个以到去来着呢吧吗啊呀哦嗯")


# ── 揭示辅助函数 ──

def _is_content_word(ch: str) -> bool:
    return bool(re.match(r"[一-龥]", ch)) and ch not in FUNCTION_WORDS

def _get_unrevealed(states: list) -> list:
    return [s for s in states if s["isContent"] and not s["revealed"]]

def _bcast(msg: dict):
    """同步方法：向 WS 广播消息。"""
    asyncio.run_coroutine_threadsafe(_ws_broadcast(msg), _ws_loop)

def _reveal_char(states: list, char: str) -> list:
    return [{**s, "revealed": True} if s["char"] == char else s for s in states]

def _reveal_random_char() -> bool:
    """揭示一个随机未揭示的内容字。返回是否揭示了。"""
    global _anti_last_reveal
    u = _get_unrevealed(_mock_state.char_states)
    if not u:
        return False
    target = random.choice(u)["char"]
    _mock_state.char_states = _reveal_char(_mock_state.char_states, target)
    _anti_last_reveal = time.time()
    _bcast({"type": "reveal_update", "charStates": _mock_state.char_states, "newChars": [target]})
    return True

def _reveal_sentence() -> bool:
    """揭示完整一句（按标点分句）。返回是否揭示了。"""
    answer = _mock_state.soup_answer
    clauses = re.split(r"(?<=[，。！？、；：])", answer)
    idx = 0
    for clause in clauses:
        if not clause.strip():
            idx += len(clause)
            continue
        start, end = idx, idx + len(clause)
        for i in range(start, end):
            if i < len(_mock_state.char_states) and _mock_state.char_states[i]["isContent"] and not _mock_state.char_states[i]["revealed"]:
                chars = set()
                for j in range(start, end):
                    if j < len(_mock_state.char_states) and _is_content_word(_mock_state.char_states[j]["char"]):
                        _mock_state.char_states = _reveal_char(_mock_state.char_states, _mock_state.char_states[j]["char"])
                        chars.add(_mock_state.char_states[j]["char"])
                _bcast({"type": "reveal_update", "charStates": _mock_state.char_states, "newChars": list(chars)})
                return True
        idx = end
    return False

def _reveal_30p() -> bool:
    """揭示 30% 的未揭示内容字。返回是否揭示了。"""
    u = _get_unrevealed(_mock_state.char_states)
    if not u:
        return False
    target_count = max(1, int(len(u) * 0.3))
    targets = random.sample(u, min(target_count, len(u)))
    chars = []
    for s in targets:
        _mock_state.char_states = _reveal_char(_mock_state.char_states, s["char"])
        chars.append(s["char"])
    _bcast({"type": "reveal_update", "charStates": _mock_state.char_states, "newChars": chars})
    return True

def _check_game_complete():
    """若所有字已揭示，结束游戏。"""
    r, t, _ = 0, 0, 0
    c = [s for s in _mock_state.char_states if s["isContent"]]
    r = sum(1 for s in c if s["revealed"])
    t = len(c)
    if r == t and t > 0 and _mock_state.phase != "complete":
        _mock_state.phase = "complete"
        _bcast({"type": "game_end", "winner": "系统", "charStates": _mock_state.char_states})


# ── 后台 asyncio 任务 ──

async def _timer_loop():
    """每秒广播剩余时间，超时强制揭示。"""
    while True:
        await asyncio.sleep(1)
        try:
            if _mock_state.phase in ("idle", "complete", "lobby"):
                if _mock_state.phase == "complete" and not _auto_start_pending:
                    _auto_start_pending = True
                    asyncio.create_task(_auto_start_after_delay())
                continue
            elapsed = time.time() - _mock_state.start_time
            remaining = max(0, _game_config.get("roundTimeout", 600) - int(elapsed))
            _mock_state.remaining = remaining
            await _ws_broadcast({"type": "timer", "remaining": remaining, "elapsed": int(elapsed)})
            if remaining <= 0:
                await _ws_broadcast({"type": "timer", "remaining": 0, "elapsed": int(elapsed)})
                for s in _mock_state.char_states:
                    if s["isContent"] and not s["revealed"]:
                        s["revealed"] = True
                _mock_state.phase = "complete"
                await _ws_broadcast({"type": "reveal_update", "charStates": _mock_state.char_states, "auto": True})
                await _ws_broadcast({"type": "game_end", "winner": "系统", "charStates": _mock_state.char_states})
        except Exception as e:
            print(f"[Timer] Error: {e}")

async def _anti_stall_loop():
    """每 30s 检查防卡死条件，自动揭示。"""
    while True:
        await asyncio.sleep(30)
        try:
            if not _mock_state.soup_answer or _mock_state.phase in ("idle", "complete", "lobby"):
                continue
            if not _anti_stall_config.get("enabled", True):
                continue
            now = time.time()
            decay = ANTI_STALL_DECAY ** _anti_triggers
            time_cond = (now - _anti_last_reveal) >= (_anti_stall_config.get("interval", 180) * decay)
            danmaku_cond = _danmaku_since_reveal >= (_anti_stall_config.get("danmaku", 50) * decay)
            if time_cond or danmaku_cond:
                u = _get_unrevealed(_mock_state.char_states)
                if not u:
                    continue
                # 优先揭示高频字：按频率选择（这里用随机作为简化版）
                _anti_triggers += 1
                _reveal_random_char()
                _danmaku_since_reveal = 0
                _anti_last_reveal = time.time()
                _check_game_complete()
        except Exception as e:
            print(f"[AntiStall] Error: {e}")

async def _auto_start_after_delay():
    """等待后自动开始下一局。"""
    await asyncio.sleep(AUTO_START_DELAY)
    try:
        if _mock_state.phase == "complete":
            print("[AutoStart] 自动开始下一局")
            _do_game_start(difficulty=_mock_state.current_difficulty or "medium")
    except Exception as e:
        print(f"[AutoStart] Error: {e}")
    finally:
        _auto_start_pending = False


# ── 游戏启动（可被 HTTP + 自动下一局复用） ──

def _do_game_start(difficulty: str = "medium", soup_id: str = ""):
    """选汤、初始化状态、广播 game_start。"""
    global _anti_last_reveal, _danmaku_since_reveal, _anti_triggers
    if not soup_id:
        if difficulty in ("easy", "medium", "hard", "hell", "void"):
            pool = [s for s in SOUPS_DATA if s.get("difficulty") == difficulty]
        else:
            pool = SOUPS_DATA
        if not pool:
            pool = SOUPS_DATA
    else:
        pool = [s for s in SOUPS_DATA if s.get("id") == soup_id]
        if not pool:
            pool = SOUPS_DATA
    soup = random.choice(pool) if pool else None
    if not soup:
        print("[Game] 题库为空，无法开始")
        return

    _mock_state.phase = "reading"
    _mock_state.start_time = time.time()
    _mock_state.round_total += 1
    _mock_state.current_difficulty = difficulty
    _mock_state.soup_text = soup.get("surface", "")
    _mock_state.soup_answer = soup.get("bottom", "")
    _mock_state.soup_keywords = soup.get("keywords", [])
    bottom = soup.get("bottom", "")
    _mock_state.char_states = [
        {"char": ch, "revealed": False,
         "isContent": bool(re.match(r"[一-龥]", ch)) and ch not in FUNCTION_WORDS}
        for ch in bottom
    ]
    # 重置防卡死计数器
    _anti_last_reveal = time.time()
    _danmaku_since_reveal = 0
    _anti_triggers = 0

    asyncio.run_coroutine_threadsafe(
        _ws_broadcast({
            "type": "game_start", "phase": "reading",
            "surface": _mock_state.soup_text,
            "keywords": _mock_state.soup_keywords,
            "charStates": _mock_state.char_states,
            "difficulty": difficulty,
            "remaining": _game_config.get("roundTimeout", 600),
            "roundTimeout": _game_config.get("roundTimeout", 600),
        }),
        _ws_loop,
    )
    print(f"[Game] 开始: {soup.get('title', '')} ({difficulty})")


# ── WS 弹幕处理 ──

async def _handle_danmaku(data: dict):
    """处理弹幕消息：碰词揭示 + LLM 分类 + 结果广播。"""
    global _danmaku_since_reveal, _anti_last_reveal
    user = data.get("user", "观众")
    content = data.get("content", "").strip()
    if not content or _mock_state.phase not in ("reading",):
        return

    # 1. 碰词揭示：遍历弹幕每个字，检查是否匹配未揭示 content 字
    new_chars = []
    for ch in content:
        for s in _mock_state.char_states:
            if s["char"] == ch and s["isContent"] and not s["revealed"]:
                s["revealed"] = True
                new_chars.append(ch)
                break

    if new_chars:
        _danmaku_since_reveal = 0
        _anti_last_reveal = time.time()
        await _ws_broadcast({
            "type": "reveal_update",
            "charStates": _mock_state.char_states,
            "newChars": new_chars,
        })
        _check_game_complete()

    # 2. LLM 分类（在线程中执行，避免阻塞事件循环）
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _llm_classify, content, _mock_state.soup_answer, _mock_state.soup_keywords)
    await _ws_broadcast({
        "type": "classification",
        "user": user, "text": content, "result": result,
    })

    # 3. 更新弹幕计数器（用于 anti-stall 判断）
    _danmaku_since_reveal += 1

# ── WebSocket 广播 ──
_ws_clients: set = set()
_ws_loop = None

# ── 配置 ──
PORT = 3090
WS_PORT = PORT + 1  # WebSocket 用下一个端口
HOST = "127.0.0.1"

# ── 路径处理（兼容 PyInstaller EXE 和直接运行） ──
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _BASE = sys._MEIPASS
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_BASE)  # backend/（仅开发模式）
# 确保能 import 同级的 tts_engine 等模块
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    if sys._MEIPASS not in sys.path:
        sys.path.insert(0, sys._MEIPASS)
elif _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

# ── TTS 音频目录 ──
_TTS_DIR = os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else _BASE, "tts_audio")
os.makedirs(_TTS_DIR, exist_ok=True)

def _parse_multipart(body: bytes, content_type: str) -> dict:
    """简易 multipart/form-data 解析器 — 返回 {field_name: value|{filename,content,content_type}}"""
    import re
    m = re.search(r'boundary=([^;\s]+)', content_type)
    if not m:
        return {}
    boundary = m.group(1).strip('"').encode()
    parts = body.split(b'--' + boundary)
    result = {}
    for part in parts:
        part = part.strip(b'\r\n ')
        if part in (b'', b'--'):
            continue
        header_end = part.find(b'\r\n\r\n')
        if header_end == -1:
            continue
        hdr = part[:header_end].decode('utf-8', errors='replace')
        data = part[header_end + 4:]
        if data.endswith(b'\r\n'):
            data = data[:-2]
        nm = re.search(r'name="([^"]*)"', hdr)
        name = nm.group(1) if nm else ''
        fm = re.search(r'filename="([^"]*)"', hdr)
        if fm:
            ct = re.search(r'Content-Type:\s*(\S+)', hdr)
            result[name] = {
                "filename": fm.group(1),
                "content": data,
                "content_type": ct.group(1) if ct else 'application/octet-stream',
            }
        else:
            result[name] = data.decode('utf-8', errors='replace')
    return result


def _resolve_src(filename: str) -> str:
    """尝试 _BASE（EXE 内）→ _PARENT（开发）→ 同级目录 解析数据文件路径"""
    p = os.path.join(_BASE, filename)
    if os.path.isfile(p):
        return p
    p2 = os.path.join(_PARENT, filename)
    if os.path.isfile(p2):
        return p2
    # EXE 打包时文件在 _BASE，回退到同目录
    return os.path.join(_BASE, filename)

ADMIN_SRC = _resolve_src("admin.py")
OVERLAY_SRC = _resolve_src("overlay.py")


def _exec_py_var(filepath, varname):
    with open(filepath, encoding="utf-8") as f:
        src = f.read()
    g = {}
    exec(src, g)
    return g[varname]

ADMIN_HTML_RAW = _exec_py_var(ADMIN_SRC, "ADMIN_HTML")
OVERLAY_HTML_RAW = _exec_py_var(OVERLAY_SRC, "OVERLAY_HTML")

# ── 可选加载题库 ──
SOUPS_DATA = []
SOUPS_CACHE = os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else _BASE, "soups_cache.json")
_BANNED_WORDS_FILE = os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else _BASE, "banned_words.json")
try:
    SOUPS_SRC = _resolve_src("data_soups.py")
    if os.path.isfile(SOUPS_SRC):
        SOUPS_DATA = _exec_py_var(SOUPS_SRC, "SOUPS")
        print(f"  已加载 {len(SOUPS_DATA)} 道题库")
except Exception:
    pass
# 合并持久化的用户修改（增删题目在重启后保留）
try:
    if os.path.isfile(SOUPS_CACHE):
        with open(SOUPS_CACHE, encoding="utf-8") as f:
            cached = json.load(f)
        if isinstance(cached, list) and len(cached) >= len(SOUPS_DATA):
            SOUPS_DATA = cached
            print(f"  从缓存恢复 {len(SOUPS_DATA)} 道（含用户自建）")
except Exception:
    pass

def _save_soups():
    try:
        with open(SOUPS_CACHE, "w", encoding="utf-8") as f:
            json.dump(SOUPS_DATA, f,ensure_ascii=False)
    except Exception:
        pass

# ── 屏蔽词持久化 ──
def _load_banned_words():
    global _banned_words
    try:
        if os.path.isfile(_BANNED_WORDS_FILE):
            with open(_BANNED_WORDS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            # 文件非空 → 加载用户保存的词；为空（旧版遗留）→ 保留默认值
            if isinstance(data, list) and len(data) > 0:
                _banned_words = data
                print(f"  已加载 {len(_banned_words)} 条屏蔽词")
            elif isinstance(data, list) and len(data) == 0:
                # 旧版存了空列表，覆盖为默认值
                _save_banned_words()
                print(f"  屏蔽词文件为空，已重置为默认值 ({len(_banned_words)} 条)")
        else:
            # 首次运行，保存默认值到文件
            _save_banned_words()
            print(f"  已保存默认屏蔽词 ({len(_banned_words)} 条)")
    except Exception:
        pass

def _save_banned_words():
    try:
        with open(_BANNED_WORDS_FILE, "w", encoding="utf-8") as f:
            json.dump(_banned_words, f, ensure_ascii=False)
    except Exception:
        pass

# 启动时加载屏蔽词
_load_banned_words()

# ── LLM 配置（持久化到本地 JSON）──
_LLM_CONFIG_FILE = os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else _BASE, "llm_config.json")
_llm_config = {
    "api_key": "", "base_url": "", "model": "deepseek-v4-flash", "reasoning": True,
    "qa_api_key": "", "qa_base_url": "", "qa_model": "mimo-v2.5",
}
try:
    if os.path.isfile(_LLM_CONFIG_FILE):
        with open(_LLM_CONFIG_FILE, encoding="utf-8") as f:
            _llm_config.update(json.load(f))
except Exception:
    pass

def _save_llm_config():
    try:
        with open(_LLM_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_llm_config, f, ensure_ascii=False)
    except Exception:
        pass

def _llm_chat(messages, model=None, temperature=0.7, max_tokens=1024, timeout=30, response_format=None, reasoning=True):
    """使用 urllib 调用 OpenAI 兼容 API（零额外依赖）
    reasoning=False 时传入 reasoning_effort="none" 请求模型关闭推理。
    """
    api_key = _llm_config.get("api_key", "")
    base_url = _llm_config.get("base_url", "").rstrip("/")
    model_name = model or _llm_config.get("model", "")
    if not api_key or not base_url or not model_name:
        return None
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if not reasoning:
        payload["reasoning_effort"] = "none"
    if response_format:
        payload["response_format"] = response_format
    body = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_text = resp.read().decode("utf-8")
        try:
            data = json.loads(resp_text)
        except json.JSONDecodeError:
            print(f"[LLM] API 返回非 JSON 内容: {resp_text[:300]}")
            raise Exception(f"API 返回格式异常（非 JSON），请检查 base_url 是否正确。响应开头: {resp_text[:80]}")
        return data
    except urllib.error.HTTPError as e:
        err_text = e.read().decode("utf-8", errors="replace")
        # 如果 response_format 被 API 拒绝，回退重试（不带此参数）
        if e.code == 400 and response_format:
            print(f"[LLM] response_format 被拒绝，回退重试: {err_text[:200]}")
            return _llm_chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, timeout=timeout, response_format=None, reasoning=reasoning)
        raise Exception(f"HTTP {e.code}: {err_text[:200]}")
    except urllib.error.URLError as e:
        raise Exception(f"连接失败: {e.reason}")

# AI 出题方向 prompt 映射（与 routers/admin.py 同步）
_DIRECTION_PROMPTS = {
    "random":        "",
    "mystery":       "方向为悬疑推理：包含谋杀、失踪、盗窃等需要逻辑推理的情节，线索要埋得巧妙，反转要合理。",
    "horror":        "方向为恐怖惊悚：包含灵异事件、鬼怪传说或心理恐怖元素，氛围要阴森压抑，结局要令人不寒而栗。",
    "daily":         "方向为日常推理：场景设定在日常生活（家庭、学校、办公室等），看似普通的事件背后有惊人的真相。",
    "sci-fi":        "方向为科幻想象：涉及人工智能、时空旅行、虚拟现实、未来世界等科幻元素，逻辑自洽。",
    "ethics":        "方向为情感伦理：围绕爱情、亲情、友情、道德困境等人性主题，情感冲击力强，引人深思。",
    "fairy-tale":    "方向为黑暗童话：基于经典童话、寓言或知名故事进行暗黑、反转改编，既熟悉又意外。",
    "urban":         "方向为都市传说：设定在现代都市中，带有怪谈、都市传说色彩，亦真亦假，细思极恐。",
    "history":       "方向为历史秘闻：基于真实历史事件或人物进行创意改编，历史背景准确，核心谜题有新意。",
    "dark-humor":    "方向为黑色幽默：情节荒诞讽刺，结局出人意料又合情合理，让人哭笑不得。",
    "psychological": "方向为心理迷宫：涉及人格分裂、记忆错乱、梦境与现实交织、感官欺骗等心理悬疑元素。",
}
_DIFFICULTY_CONSTRAINTS = {
    "easy":   "简单难度：单步推理即可解开，剧情直白零误导，线索明显摆在汤面中，适合新手快速上手。",
    "medium": "一般难度：两步推理或一次关键反转，线索半隐半现，需要跳出初始视角重新审视。",
    "hard":   "困难难度：三步以上逻辑链，多层反转或巧妙误导，线索分散在不同细节中，需要串联推敲。",
    "hell":   "地狱难度：复杂嵌套谜局，多重反转环环相扣，大部分线索隐晦，需要极强的逆向思维才能突破。",
    "void":   "无人区难度：极度抽象荒诞，违背常理和直觉，线索若有若无，需要彻底打破思维定势才能触及真相。",
    "auto":   "自适应难度：AI 根据题目本身自动判断归属的难度等级，覆盖各层次。",
}

# ── 加载礼物库 ──
GIFT_LIBRARY = {}  # {gift_name: {coins, icon}}
GIFT_JSON_CANDIDATES = [
    os.path.join(_BASE, "gift_icons.json"),  # EXE 打包内部
    os.path.join(_PARENT, "gift_icons.json"), # backend/
    os.path.join(os.path.dirname(_PARENT), "gift_icons.json"),  # 项目根目录
    "C:/Users/27871/OneDrive/Desktop/CCcat猜词大挑战/overlay/gift_icons.json",
]
GIFT_JSON_SRC = GIFT_JSON_CANDIDATES[0]
for _p in GIFT_JSON_CANDIDATES:
    if os.path.isfile(_p):
        GIFT_JSON_SRC = _p
        break
if os.path.isfile(GIFT_JSON_SRC):
    try:
        with open(GIFT_JSON_SRC, "r", encoding="utf-8") as f:
            GIFT_LIBRARY = json.load(f)
        print(f"  已加载 {len(GIFT_LIBRARY)} 个礼物")
    except Exception:
        pass

# ── 加载主题库 ──
BUILTIN_THEMES = {}
THEMES_SRC = _resolve_src("theme_manager.py")
if os.path.isfile(THEMES_SRC):
    try:
        BUILTIN_THEMES = _exec_py_var(THEMES_SRC, "BUILTIN_THEMES")
        print(f"  已加载 {len(BUILTIN_THEMES)} 个主题")
    except Exception as e:
        print(f"  [WARN] 主题加载失败: {e}")

# 9个固定槽位定义（与 gift_slots.py 一致）
SLOT_DEFINITIONS = [
    {"id": "effect_complete", "group": "effect", "name": "直接通关", "desc": "立即通关当前故事", "default_gift": "梦幻城堡"},
    {"id": "effect_reveal1",   "group": "effect", "name": "揭示一字",  "desc": "随机揭示一个高频实词字", "default_gift": "啤酒"},
    {"id": "effect_reveal_sentence", "group": "effect", "name": "揭示一句", "desc": "揭示完整一句话", "default_gift": "棒棒糖"},
    {"id": "effect_reveal_30p","group": "effect", "name": "揭示30%",  "desc": "立即揭示30%的未揭示内容", "default_gift": "墨镜"},
    {"id": "diff_easy",  "group": "difficulty", "name": "难度-简单", "desc": "下局切换为简单", "default_gift": "鲜花"},
    {"id": "diff_medium","group": "difficulty", "name": "难度-一般", "desc": "下局切换为一般", "default_gift": "玫瑰"},
    {"id": "diff_hard",  "group": "difficulty", "name": "难度-困难", "desc": "下局切换为困难", "default_gift": "跑车"},
    {"id": "diff_hell",  "group": "difficulty", "name": "难度-地狱", "desc": "下局切换为地狱", "default_gift": "嘉年华"},
    {"id": "diff_void",  "group": "difficulty", "name": "难度-无人区", "desc": "下局切换为无人区", "default_gift": "梦幻城堡"},
]


def _build_slots():
    """构建模拟槽位数据（含礼物信息，合并用户覆盖）"""
    result = []
    for sd in SLOT_DEFINITIONS:
        gift_name = sd["default_gift"]
        gift_info = GIFT_LIBRARY.get(gift_name, {})
        over = _slot_overrides.get(sd["id"], {})
        slot = {
            "id": sd["id"],
            "group": sd["group"],
            "name": sd["name"],
            "desc": sd["desc"],
            "gift_name": over.get("gift_name", gift_name),
            "gift_coins": over.get("gift_coins", gift_info.get("coins", 0)),
            "gift_icon": over.get("gift_icon", gift_info.get("icon", "")),
            "enabled": over.get("enabled", True),
            "like_mode": False,
            "like_threshold": 500,
        }
        result.append(slot)
    return result


def _search_gifts(query: str) -> list:
    """搜索礼物库，返回所有匹配的礼品，按价值升序排列"""
    q = query.lower().strip()
    items = list(GIFT_LIBRARY.items())
    if q:
        items = [(k, v) for k, v in items if q in k.lower()]
    items.sort(key=lambda x: x[1].get("coins", 0))
    return [{"name": k, "coins": v.get("coins", 0), "icon": v.get("icon", "")} for k, v in items]


def inject_html(html: str, server_url: str, ws_url: str) -> str:
    """注入前端配置 — 劫持 API 调用指向本地服务器"""
    script = (
        "<script>"
        f"window.SERVER_URL={json.dumps(server_url)};"
        f"window.WS_URL={json.dumps(ws_url)};"
        "window.__STANDALONE__=true;"
        "window.__STANDALONE_TTS__=true;"
        "(function(){"
        "var _f=window.fetch;"
        "window.fetch=function(u,o){"
        "if(typeof u==='string'&&u.startsWith('/'))u=window.SERVER_URL+u;"
        "return _f.call(window,u,o);"
        "};"
        "})();"
        "</script>"
    )
    h = html.replace("</head>", script + "</head>")
    # 替换 WebSocket URL 构造
    for pattern in [
        "(location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws'",
        "((location.protocol==='https:')?'wss:':'ws:')+'//'+location.host+'/ws'",
    ]:
        h = h.replace(pattern, "window.WS_URL")
    return h


def _apply_theme(html: str, theme_id: str) -> str:
    """为 HTML 注入主题 CSS 变量。"""
    import re
    theme = BUILTIN_THEMES.get(theme_id)
    if not theme:
        return html
    vars_dict = theme["vars"]
    css_lines = [f"  {k}: {v};" for k, v in vars_dict.items()]
    css_block = ":root {\n" + "\n".join(css_lines) + "\n}"
    new_html, n = re.subn(r":root\s*\{[^}]*\}", css_block, html, count=1)
    if n == 0:
        new_html = html.replace("</style>", f"{css_block}\n</style>", 1)
    return new_html


EDGE_CN_VOICES = {
    "zh-CN-XiaoxiaoNeural": "晓晓 (女声·推荐)",
    "zh-CN-XiaoyiNeural": "晓伊 (女声·情感)",
    "zh-CN-YunxiNeural": "云希 (男声)",
    "zh-CN-YunjianNeural": "云健 (男声)",
    "zh-CN-XiaohanNeural": "晓涵 (女声·温柔)",
    "zh-CN-XiaomengNeural": "晓梦 (女声·活泼)",
    "zh-CN-XiaochenNeural": "晓辰 (女声·知性)",
    "zh-CN-XiaomoNeural": "晓墨 (女声·文学)",
    "zh-CN-XiaoruiNeural": "晓睿 (女声·成熟)",
    "zh-CN-XiaoshuangNeural": "晓双 (女声·元气)",
    "zh-CN-XiaoxuanNeural": "晓萱 (女声·亲和)",
    "zh-CN-XiaoyanNeural": "晓颜 (女声·自然)",
    "zh-CN-XiaozhenNeural": "晓珍 (女声·温柔)",
    "zh-CN-YunyangNeural": "云扬 (男声·阳光)",
    "zh-CN-YunyeNeural": "云野 (男声·随性)",
    "zh-CN-YunfanNeural": "云帆 (男声·深沉)",
    "zh-CN-YunhaoNeural": "云皓 (男声·活力)",
}

# ── 模拟 API 响应 ──
class MockState:
    """模拟游戏状态"""
    def __init__(self):
        self.phase = "idle"
        self.start_time = 0
        self.round_total = 0
        self.round_correct = 0
        self.qa_history = []
        self.gift_log = []
        self.char_states = []
        self.active_theme = "dark"
        self.soup_text = ""
        self.soup_answer = ""
        self.soup_keywords = []
        self.current_difficulty = ""
        self.remaining = 0

    def reset(self):
        self.phase = "idle"
        self.start_time = 0
        self.qa_history = []
        self.char_states = []
        self.soup_text = ""
        self.soup_answer = ""
        self.soup_keywords = []
        self.current_difficulty = ""
        self.remaining = 0

    def to_dict(self):
        dur = int(time.time() - self.start_time) if self.start_time else 0
        return {
            "totalScore": 0,
            "totalDanmaku": len(self.qa_history),
            "totalGifts": len(self.gift_log),
            "paid_users": 0,
            "round_count": self.round_total,
            "session_duration": dur,
            "accuracy": round(self.round_correct / max(self.round_total, 1) * 100) if self.round_total else 0,
            "danmaku_series": [],
            "gift_series": [],
            "recentGifts": [{
                "user": g["user"], "gift_name": g["giftName"],
                "coins": 0,
            } for g in self.gift_log[-10:]],
        }


_mock_state = MockState()

# ── TTS 配置（可写，POST 持久化） ──
_tts_config = {
    "engine": "edge", "voice": "zh-CN-XiaoxiaoNeural", "rate": 1.0,
    "voices": EDGE_CN_VOICES,
    "engines": {"edge": {"available": True}},
    "cosyvoice_spk": "default",
    "cosyvoice_speakers": {},
}

def _build_tts_config():
    base = dict(_tts_config)
    if _cosyvoice_preloaded:
        # 优先使用预加载/部署缓存（含上次真实检测结果）
        with _cosyvoice_preload_lock:
            cached = dict(_cosyvoice_preload_cache)
        if cached.get("status") and cached["status"] not in ("loading",):
            base["engines"] = {"edge": {"available": True}, "cosyvoice": cached}
            print(f"[TTS Config] 使用缓存 status={cached.get('status')}", flush=True)
        else:
            # 缓存不可用时实时检测
            live = _get_cosyvoice_engine()
            base["engines"] = {"edge": {"available": True}, "cosyvoice": live}
            print(f"[TTS Config] 实时检测 status={live.get('status')}", flush=True)
            # 异步回写缓存
            with _cosyvoice_preload_lock:
                _cosyvoice_preload_cache.clear()
                _cosyvoice_preload_cache.update(live)
        try:
            import tts_engine
            speakers = tts_engine.list_cosyvoice_speakers()
            if speakers:
                base["cosyvoice_speakers"] = speakers
        except Exception:
            pass
    else:
        # 后台加载中，返回缓存状态（不阻塞 HTTP）
        with _cosyvoice_preload_lock:
            base["engines"] = {"edge": {"available": True}, "cosyvoice": dict(_cosyvoice_preload_cache)}
        base["cosyvoice_speakers"] = {}
    return base


# ── TTS 音频生成 ──

_tts_rate_str_cache: str = ""

def _tts_rate_str() -> str:
    r = _tts_config.get("rate", 1.0)
    if r >= 1:
        return f"+{int((r-1)*100)}%"
    return f"-{int((1-r)*100)}%"

async def _generate_tts_async(text: str) -> tuple:
    """根据引擎配置合成语音，返回 (filepath, url)。失败返回 (None, None)。
    CosyVoice → .wav, Edge TTS → .mp3。"""
    engine = _tts_config.get("engine", "edge")

    # ── CosyVoice ──
    if engine == "cosyvoice":
        try:
            import tts_engine
        except ImportError:
            print("[TTS] cosyvoice 引擎未安装")
            return None, None
        spk_id = _tts_config.get("cosyvoice_spk", "default")
        try:
            loop = asyncio.get_running_loop()
            sr, wav_bytes = await loop.run_in_executor(
                None, lambda: tts_engine.cosyvoice_generate(text, spk_id)
            )
        except Exception:
            sr, wav_bytes = None, None
        if wav_bytes:
            filename = f"tts_{int(time.time())}_{hash(text) & 0xFFFF}.wav"
            filepath = os.path.join(_TTS_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(wav_bytes)
            print(f"[TTS] CosyVoice({spk_id}) -> {filename}")
            return filepath, f"/audio/{filename}"
        print("[TTS] CosyVoice 合成失败")
        return None, None

    # ── Edge TTS ──
    try:
        import edge_tts
    except ImportError:
        print("[TTS] edge-tts 未安装，跳过语音合成")
        return None, None
    voice = _tts_config.get("voice", "zh-CN-XiaoxiaoNeural")
    rate = _tts_rate_str()
    filename = f"tts_{int(time.time())}_{hash(text) & 0xFFFF}.mp3"
    filepath = os.path.join(_TTS_DIR, filename)
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(filepath)
        return filepath, f"/audio/{filename}"
    except Exception as e:
        print(f"[TTS] 合成失败: {e}")
        return None, None

# ── CosyVoice 部署状态 ──
_cv_deploy_lock = threading.Lock()
_cv_deploy_progress: dict = {}  # {"step": ..., "pct": ..., "text": ...}

# frozen EXE 中 pip 需要原始 Python 解释器
if getattr(sys, "frozen", False):
    _python_exe = getattr(sys, "_base_executable", None) or sys.executable
else:
    _python_exe = sys.executable

# EXE 模式下 CosyVoice 本地存储路径（EXE 旁边的 CosyVoiceV7/）
_cosyvoice_site = None   # pip install --target 目录
_cosyvoice_local_dir = None  # EXE 旁边的 CosyVoiceV7 目录
_cosyvoice_exe_inited = False


def _init_cosyvoice_exe_paths():
    """EXE 模式下初始化 CosyVoice 的存储路径。"""
    global _cv_dir, _cosyvoice_site, _cosyvoice_local_dir, _cosyvoice_exe_inited
    if _cosyvoice_exe_inited:
        return
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else _BASE
    _cosyvoice_local_dir = os.path.join(base, "CosyVoiceV7")
    _cosyvoice_site = os.path.join(_cosyvoice_local_dir, ".cosyvoice_site")
    os.makedirs(_cosyvoice_site, exist_ok=True)
    if _cosyvoice_site not in sys.path:
        sys.path.insert(0, _cosyvoice_site)
    if _cosyvoice_local_dir not in sys.path:
        sys.path.insert(0, _cosyvoice_local_dir)
    _cv_dir = _cosyvoice_local_dir
    _cosyvoice_exe_inited = True


# 使用 tts_engine 定义的位置（backend/CosyVoiceV7/）
_cv_dir = None  # 延迟初始化


def _get_cosyvoice_engine():
    """返回 cosyvoice engine 的真实状态。"""
    try:
        import tts_engine as te
        if getattr(sys, "frozen", False):
            _init_cosyvoice_exe_paths()
            # 覆盖 tts_engine 中的路径为 EXE 旁边的目录
            te.COSYVOICE_DIR = Path(_cosyvoice_local_dir)
        result = te.cosyvoice_status()
        print(f"[CosyVoice] _get_cosyvoice_engine -> {result.get('status')}: {result.get('detail', '')[:80]}", flush=True)
        return result
    except ImportError:
        return {"status": "deps_missing", "detail": "tts_engine 不可用"}
    except Exception as e:
        print(f"[CosyVoice] _get_cosyvoice_engine 异常: {e}", flush=True)
        return {"status": "error", "detail": str(e)[:100]}


def _get_cv_deploy_status():
    """返回 CosyVoice 部署实时状态。"""
    with _cv_deploy_lock:
        running = _cv_deploy_progress.get("step") in (None, "", "done", "error") and False
        # 正在运行中的标志：没有 done/error 就有进度
        step = _cv_deploy_progress.get("step", "")
        if step and step not in ("done", "error"):
            return {
                "deploying": True,
                "progress": dict(_cv_deploy_progress),
                "error": None,
            }
        if step == "error":
            return {
                "deploying": False,
                "progress": dict(_cv_deploy_progress),
                "error": _cv_deploy_progress.get("text", ""),
            }
        return {"deploying": False, "progress": None, "error": None}


def _cosyvoice_model_files_complete(model_dir: str) -> bool:
    """检查模型文件是否齐全。"""
    required = ["llm.pt", "flow.pt", "hift.pt", "campplus.onnx", "speech_tokenizer_v3.onnx"]
    for f in required:
        if not os.path.isfile(os.path.join(model_dir, f)):
            return False
    # 检查 CosyVoice-BlankEN tokenizer 目录
    tokenizer_dir = os.path.join(model_dir, "CosyVoice-BlankEN")
    if not os.path.isdir(tokenizer_dir):
        return False
    for bf in ["model.safetensors", "config.json", "vocab.json", "tokenizer_config.json", "merges.txt"]:
        if not os.path.isfile(os.path.join(tokenizer_dir, bf)):
            return False
    return True


def _pip_install_cosyvoice_deps():
    """安装缺失的 Python 依赖。"""
    # 检查已安装的包
    installed = set()
    try:
        r = subprocess.run(
            [_python_exe, "-m", "pip", "list", "--format=freeze"],
            capture_output=True, text=True, timeout=30,
        )
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
        "openai-whisper", "inflect", "HyperPyYAML",
        "matcha-tts",
        "flow_matching", "torch-einops-utils",  # cosyvoice flow matching 需要的
        "onnxruntime-gpu==1.18.0",  # 先尝试 GPU 版，失败再用 CPU 版
    ]
    to_install = []
    for pkg in candidates:
        base = pkg.split(">=")[0].split("==")[0].strip().lower()
        if base not in installed:
            to_install.append(pkg)

    if not to_install:
        return

    # EXE 模式：用 --target 安装到 EXE 旁边的本地目录
    extra_pip_args = []
    if getattr(sys, "frozen", False):
        _init_cosyvoice_exe_paths()
        extra_pip_args = ["--target", _cosyvoice_site]

    # 逐个安装（个别包如 matcha-tts 需要编译，用短超时 + 非致命）
    total = len(to_install)
    for idx, pkg in enumerate(to_install):
        pct = 10 + int(30 * ((idx + 1) / total))
        base_name = pkg.split(">=")[0].split("==")[0]
        with _cv_deploy_lock:
            _cv_deploy_progress.update({
                "step": "install_deps", "pct": pct,
                "text": f"安装依赖 ({idx+1}/{total}): {base_name}...",
            })
        timeout = 300 if base_name in ("matcha-tts", "onnxruntime-gpu") else 600
        try:
            subprocess.check_call(
                [_python_exe, "-m", "pip", "install", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", pkg] + extra_pip_args,
                timeout=timeout,
            )
        except subprocess.CalledProcessError:
            # onnxruntime-gpu 失败时试 CPU 版
            if base_name == "onnxruntime-gpu":
                try:
                    subprocess.check_call(
                        [_python_exe, "-m", "pip", "install", "onnxruntime"] + extra_pip_args,
                        timeout=600,
                    )
                except subprocess.CalledProcessError as ex:
                    print(f"[CosyVoice Deploy] onnxruntime 安装也失败: {ex}")
                    with _cv_deploy_lock:
                        _cv_deploy_progress.update({
                            "step": "install_deps", "pct": pct,
                            "text": f"onnxruntime 安装失败（非致命）: {str(ex)[:80]}",
                        })
            else:
                # 非致命依赖失败时打印警告并继续
                print(f"[CosyVoice Deploy] 依赖 {base_name} 安装失败（跳过，非致命）")
                with _cv_deploy_lock:
                    _cv_deploy_progress.update({
                        "step": "install_deps", "pct": pct,
                        "text": f"{base_name} 安装跳过（非致命），继续...",
                    })


def _ensure_cosyvoice_repo():
    """克隆 CosyVoice 仓库（如已存在则跳过）。"""
    global _cv_dir
    if getattr(sys, "frozen", False):
        _init_cosyvoice_exe_paths()
        _cv_dir = _cosyvoice_local_dir
    else:
        import tts_engine as te
        _cv_dir = str(te.COSYVOICE_DIR)
    if os.path.isdir(os.path.join(_cv_dir, "cosyvoice")):
        with _cv_deploy_lock:
            _cv_deploy_progress.update({
                "step": "clone_repo", "pct": 50,
                "text": "CosyVoice 仓库已存在",
            })
        return

    urls = [
        "https://gitclone.com/github.com/FunAudioLLM/CosyVoice.git",
        "https://github.com/FunAudioLLM/CosyVoice.git",
    ]
    last_error = ""
    for url in urls:
        try:
            subprocess.check_call(["git", "clone", "--depth", "1", url, _cv_dir], timeout=120)
            # 克隆子模块 Matcha-TTS（失败不致命）
            matcha_dir = os.path.join(_cv_dir, "third_party", "Matcha-TTS")
            os.makedirs(matcha_dir, exist_ok=True)
            try:
                subprocess.check_call(
                    ["git", "clone", "--depth", "1",
                     "https://gitclone.com/github.com/shivammehta25/Matcha-TTS.git",
                     str(matcha_dir)],
                    timeout=60,
                )
            except Exception:
                pass
            with _cv_deploy_lock:
                _cv_deploy_progress.update({
                    "step": "clone_repo", "pct": 50,
                    "text": "CosyVoice 仓库克隆成功",
                })
            return
        except subprocess.CalledProcessError as e:
            last_error = str(e)
            continue
    raise RuntimeError(f"克隆 CosyVoice 仓库失败: {last_error}")


def _download_cosyvoice_model():
    """下载 CosyVoice3 模型文件。"""
    global _cv_dir
    model_dir = os.path.join(_cv_dir, "pretrained_models", "Fun-CosyVoice3-0.5B")
    if _cosyvoice_model_files_complete(model_dir):
        with _cv_deploy_lock:
            _cv_deploy_progress.update({
                "step": "download_model", "pct": 85,
                "text": "模型文件已存在",
            })
        return

    os.makedirs(model_dir, exist_ok=True)
    model_id = "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"
    with _cv_deploy_lock:
        _cv_deploy_progress.update({
            "step": "download_model", "pct": 60,
            "text": f"从 Hugging Face 下载模型 ({model_id})...",
        })
    try:
        # 在进程内导入 huggingface_hub（_cosyvoice_site 已在 sys.path 中）
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=model_id,
            local_dir=model_dir,
            local_dir_use_symlinks=False,
            resume_download=True,
        )
    except Exception as e:
        raise RuntimeError(f"模型下载失败: {e}")


def _run_cosyvoice_deploy():
    """在后端线程中执行完整部署流程。"""
    try:
        # EXE 模式：验证 Python 解释器可用
        if getattr(sys, "frozen", False):
            base_python = getattr(sys, "_base_executable", None)
            if not base_python or not os.path.isfile(base_python):
                raise RuntimeError("未检测到系统 Python 解释器，无法安装 CosyVoice 依赖。\n请确保已安装 Python 3.8+ 并在系统 PATH 中。")

        # Step 1: 安装依赖
        with _cv_deploy_lock:
            _cv_deploy_progress.update({"step": "install_deps", "pct": 5, "text": "检查 Python 依赖..."})
        _pip_install_cosyvoice_deps()
        with _cv_deploy_lock:
            _cv_deploy_progress.update({"step": "install_deps", "pct": 40, "text": "依赖安装完成"})

        # Step 2: 克隆仓库
        with _cv_deploy_lock:
            _cv_deploy_progress.update({"step": "clone_repo", "pct": 45, "text": "克隆 CosyVoice 仓库..."})
        _ensure_cosyvoice_repo()

        # Step 3: 下载模型
        with _cv_deploy_lock:
            _cv_deploy_progress.update({"step": "download_model", "pct": 55, "text": "下载模型文件中..."})
        _download_cosyvoice_model()

        # Step 4: 验证
        with _cv_deploy_lock:
            _cv_deploy_progress.update({"step": "verify", "pct": 90, "text": "正在验证..."})
        import tts_engine as te
        if getattr(sys, "frozen", False):
            _init_cosyvoice_exe_paths()
            te.COSYVOICE_DIR = Path(_cosyvoice_local_dir)
        te.reset_cosyvoice()
        print(f"[CosyVoice Deploy] COSYVOICE_DIR={te.COSYVOICE_DIR}, exists={te.COSYVOICE_DIR.exists()}", flush=True)
        status = te.cosyvoice_status()
        print(f"[CosyVoice Deploy] 验证 status={status.get('status')}, detail={status.get('detail','')[:100]}", flush=True)
        if status["status"] == "ready":
            with _cv_deploy_lock:
                _cv_deploy_progress.update({
                    "step": "done", "pct": 100,
                    "text": "部署成功！CosyVoice3 已就绪",
                })
            # 同步更新预加载缓存，防止后续 _get_cosyvoice_engine 返回旧状态
            with _cosyvoice_preload_lock:
                _cosyvoice_preload_cache.clear()
                _cosyvoice_preload_cache.update(status)
        else:
            with _cv_deploy_lock:
                _cv_deploy_progress.update({
                    "step": "error", "pct": 0,
                    "text": f"验证失败: {status.get('detail', '未知错误')}",
                })
    except Exception as e:
        with _cv_deploy_lock:
            _cv_deploy_progress.update({
                "step": "error", "pct": 0,
                "text": f"部署失败: {str(e)[:200]}",
            })
        traceback.print_exc()


# ── CosyVoice 后台预加载 ──
_cosyvoice_preloaded = False
_cosyvoice_preload_lock = threading.Lock()
_cosyvoice_preload_cache: dict = {"status": "loading", "detail": "引擎加载中..."}


def _background_preload_cosyvoice():
    """后台线程预加载 CosyVoice 引擎，避免阻塞 HTTP。"""
    global _cosyvoice_preloaded
    print("[CosyVoice] 后台预加载开始...", flush=True)
    t0 = time.time()
    try:
        import tts_engine
        if getattr(sys, "frozen", False):
            _init_cosyvoice_exe_paths()
            tts_engine.COSYVOICE_DIR = Path(_cosyvoice_local_dir)
        print(f"[CosyVoice] tts_engine 导入完成 ({time.time()-t0:.1f}s)，开始 cosyvoice_status()...", flush=True)
        t1 = time.time()
        status = tts_engine.cosyvoice_status()
        print(f"[CosyVoice] cosyvoice_status() 返回 ({time.time()-t1:.1f}s): {status.get('status')}", flush=True)
        with _cosyvoice_preload_lock:
            _cosyvoice_preload_cache.clear()
            _cosyvoice_preload_cache.update(status)
    except Exception as e:
        print(f"[CosyVoice] 预加载异常: {e}", flush=True)
        traceback.print_exc()
        with _cosyvoice_preload_lock:
            _cosyvoice_preload_cache.update({"status": "error", "detail": str(e)[:200]})
    finally:
        _cosyvoice_preloaded = True
        print(f"[CosyVoice] 预加载完成，总耗时 {time.time()-t0:.1f}s", flush=True)


# ── 题库筛选 ──
def _filter_soups(query_string: str) -> dict:
    """按难度筛选，补充 answer_length"""
    from urllib.parse import parse_qs
    params = parse_qs(query_string)
    diff = params.get("difficulty", [None])[0]
    raw = SOUPS_DATA
    if diff:
        raw = [s for s in raw if s.get("difficulty") == diff]
    result = []
    for s in raw:
        item = dict(s)
        item["answer_length"] = len(item.get("bottom", ""))
        result.append(item)
    return {"soups": result}


# ── 授权 API ──
def _get_auth_status():
    """返回授权状态（前端友好格式）"""
    status = lic.check()
    if status.get("ok"):
        return {
            "ok": True,
            "source": status["source"],
            "is_permanent": status.get("is_permanent", False),
            "remaining_days": status.get("remaining_days", 0),
            "remaining_seconds": status.get("remaining_seconds", 0),
            "machine_id": lic.get_machine_id(),
        }
    # 未授权或过期
    result = {
        "ok": False,
        "reason": status.get("reason", "unknown"),
        "machine_id": lic.get_machine_id(),
        "trial_available": status.get("trial_available", False),
    }
    if "remaining_seconds" in status:
        result["remaining_seconds"] = status["remaining_seconds"]
    return result


def _activate_auth(key: str) -> dict:
    """激活授权码"""
    return lic.activate(key)


# ── LLM 工具函数 ──
def _fetch_llm_models():
    """尝试从 API 获取模型列表（通过 urllib）"""
    api_key = _llm_config.get("api_key", "")
    base_url = _llm_config.get("base_url", "").rstrip("/")
    if not api_key or not base_url:
        return {"ok": False, "models": [], "error": "请先配置 API 地址和 Key"}
    try:
        req = urllib.request.Request(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = sorted([m["id"] for m in data.get("data", []) if "id" in m])
        return {"ok": True, "models": names}
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e)}

def _llm_ping():
    """测试 LLM 连接"""
    try:
        data = _llm_chat(
            messages=[{"role": "user", "content": "仅回复一个词：OK"}],
            temperature=0.1, max_tokens=100,
        )
        if data is None:
            return {"ok": False, "model": _llm_config.get("model", ""), "error": "LLM 未配置", "msg": "请先在下方填写 API 地址和 Key"}
        choice = data["choices"][0]
        text = (choice["message"].get("content") or choice["message"].get("reasoning_content") or "").strip()
        return {"ok": True, "model": _llm_config.get("model", ""), "response": text, "msg": f"✅ 模型 {_llm_config.get('model', '')} 响应正常"}
    except Exception as e:
        err = str(e)
        if "401" in err or "403" in err or "1010" in err:
            msg = "API Key 无效，请检查并重新填写"
        elif "404" in err:
            msg = f"模型 '{_llm_config.get('model', '')}' 不存在或 API 地址有误"
        elif "timeout" in err.lower():
            msg = "连接超时，请检查网络"
        elif "connection" in err.lower() or "refused" in err.lower():
            msg = f"无法连接到 {_llm_config.get('base_url', '')}"
        else:
            msg = f"连接失败: {err[:100]}"
        return {"ok": False, "model": _llm_config.get("model", ""), "error": err, "msg": msg}

def _llm_classify(text, answer, keywords):
    """游戏弹幕分类：是/不是/是也不是，始终用普通模式（无推理）。"""
    api_key = _llm_config.get("qa_api_key") or _llm_config.get("api_key", "")
    base_url = (_llm_config.get("qa_base_url") or _llm_config.get("base_url", "")).rstrip("/")
    model_name = _llm_config.get("qa_model") or _llm_config.get("model", "")
    if not api_key or not base_url or not model_name:
        return "不是"
    try:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "严格分类弹幕是否猜中汤底答案。只回复：是、不是、是也不是。规则：弹幕直接说出答案中的具体人物/物品/事件→是；弹幕提及同类但不匹配的内容（如其他水果）或完全无关→不是；弹幕相关但不准确→是也不是。注意：苹果和荔枝都是水果但不匹配，应回答不是。今天天气真好完全无关，应回答不是。"},
                {"role": "user", "content": f"汤底: {answer}\n关键词: {'、'.join(keywords)}\n弹幕: {text}"},
            ],
            "max_tokens": 500, "temperature": 0.1,
        }
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}",
                     "User-Agent": "Mozilla/5.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                data = json.loads(raw.decode("utf-8", errors="replace"))
        r = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        r = r.strip()
        if r in ("是", "不是", "是也不是"):
            return r
        # reasoning 模型 content 可能为空，从 reasoning_content 末尾提取标签
        rc = (data.get("choices") or [{}])[0].get("message", {}).get("reasoning_content", "") or ""
        rc = rc.strip()
        if rc:
            # 只检查末尾 100 字符，优先匹配长标签
            tail = rc[-100:]
            if "是也不是" in tail: return "是也不是"
            if "不是" in tail: return "不是"
            if "是" in tail: return "是"
        return "不是"
    except Exception:
        return "不是"

def _parse_ai_soups_text(text):
    """从 AI 返回的文本中解析出海龟汤数组。返回 (soups_list_or_None, error_str_or_None)。"""
    text = (text or "").strip()
    if not text:
        return None, "AI 返回了空内容，请检查模型是否支持文本生成或更换模型"
    # 去除可能的 markdown 代码块包裹
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    try:
        soups = json.loads(text)
    except json.JSONDecodeError:
        print(f"[AI] JSON 解析失败, 前200字符: {text[:200]}")
        import re as _re
        # 使用贪婪匹配：从第一个 [ 到最后一个 ]，避免字符串内含 ] 被截断
        block = _re.search(r'\[[\s\S]*\]', text, _re.DOTALL)
        if block:
            try:
                soups = json.loads(block.group(0))
            except (json.JSONDecodeError, ValueError):
                preview = text[:120]
                return None, f"AI 返回了不完整的 JSON 数据（预览: {preview}），请尝试减少单次生成数量或更换模型"
        else:
            return None, f"AI 返回格式异常，无法解析为 JSON: {text[:120]}"
    if isinstance(soups, dict):
        # 尝试从包装键中提取
        wrapped = soups.get("soups") or soups.get("data")
        if isinstance(wrapped, list):
            soups = wrapped
        elif soups.get("title") or soups.get("surface") or soups.get("content"):
            # 单条谜题直接返回的对象，包装成数组
            soups = [soups]
        else:
            soups = []
    if not isinstance(soups, list):
        return None, "AI 返回格式异常，期待数组但得到 " + type(soups).__name__
    if not soups:
        return None, "AI 返回了空数组，请尝试重新生成"
    return soups, None


def _normalize_ai_soup(s, difficulty, direction, idx):
    """标准化单条 AI 谜题：补全 id/difficulty/direction，并将 keywords 字符串转为数组。"""
    import time as _time
    s["id"] = s.get("id") or f"ai-{int(_time.time())}-{idx}"
    s["difficulty"] = s.get("difficulty", difficulty)
    s["direction"] = s.get("direction", direction)
    # 模型有时把 keywords 输出成逗号字符串而非数组，这里统一转为数组
    kw = s.get("keywords")
    if isinstance(kw, str):
        s["keywords"] = [k.strip() for k in kw.replace("，", ",").split(",") if k.strip()]
    elif not isinstance(kw, list):
        s["keywords"] = []
    return s


def _ai_generate(difficulty, count, direction):
    """使用 LLM 生成海龟汤谜题（通过 urllib）。
    根据 reasoning 模式选择参数：
    - 思考模式 ON（推理模型）: 分批每批 3 题，max_tokens=16384，timeout=300
    - 思考模式 OFF（普通模型）: 分批每批 5 题，max_tokens=4096，timeout=60
    """
    try:
        reasoning = _llm_config.get("reasoning", True)
        if reasoning:
            BATCH = 3
            MAX_TOKENS = 16384
            TIMEOUT = 300
        else:
            BATCH = 5
            MAX_TOKENS = 4096
            TIMEOUT = 60
        print(f"[AI] 思考模式={'ON' if reasoning else 'OFF'}, 模型={_llm_config.get('model', '')}")
        all_soups = []
        remaining = count
        last_finish_reason = None
        while remaining > 0:
            batch_count = min(BATCH, remaining)
            data = _llm_chat(
                messages=[{"role": "user", "content": _build_ai_prompt(difficulty, batch_count, direction)}],
                temperature=0.8, max_tokens=MAX_TOKENS, timeout=TIMEOUT,
                response_format={"type": "json_object"}, reasoning=reasoning,
            )
            if data is None:
                if not all_soups:
                    return {"soups": [], "error": "LLM 未配置，请在 AI 出题页设置 API 地址和 Key"}
                break  # 已生成部分，直接返回已得结果
            choice = data["choices"][0] if data.get("choices") else None
            if choice is None:
                if not all_soups:
                    return {"soups": [], "error": "AI 返回了空响应（无 choices），请尝试重新生成"}
                break
            last_finish_reason = choice.get("finish_reason")
            raw_content = choice["message"].get("content") or ""
            raw_reasoning = choice["message"].get("reasoning_content") or ""
            # 推理模型若被 max_tokens 截断，content 常为空而 reasoning 有值
            if not raw_content.strip() and last_finish_reason == "length":
                print(f"[AI] content 为空且 finish_reason=length（reasoning {len(raw_reasoning)} 字符），token 配额不足")
                if not all_soups:
                    return {"soups": [], "error": "AI 推理 token 配额不足导致未输出结果，请减少单次生成数量或更换非推理模型"}
                break
            soups, err = _parse_ai_soups_text(raw_content or raw_reasoning)
            if err:
                print(f"[AI] 批次解析失败: {err}")
                if not all_soups:
                    return {"soups": [], "error": err}
                break  # 已有部分结果，跳过本批错误
            all_soups.extend(soups)
            remaining -= batch_count
        if not all_soups:
            return {"soups": [], "error": "AI 未生成任何谜题，请重试或更换模型"}
        all_soups = [_normalize_ai_soup(s, difficulty, direction, i) for i, s in enumerate(all_soups)]
        return {"soups": all_soups}
    except Exception as e:
        err_msg = str(e)
        print(f"[AI] 生成异常: {traceback.format_exc()}")
        if "401" in err_msg or "403" in err_msg or "Authentication" in err_msg or "Incorrect API key" in err_msg or "1010" in err_msg:
            hint = "API Key 无效或未填写，请在 AI 出题页下方配置正确的 API Key"
        elif "404" in err_msg or "Not Found" in err_msg:
            hint = f"模型 '{_llm_config.get('model', '')}' 不存在或 API 地址有误，请检查 LLM API 配置"
        elif "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
            hint = "请求超时，AI 推理耗时过长，请减少生成数量或更换响应更快的模型"
        elif "connection" in err_msg.lower() or "refused" in err_msg.lower():
            hint = f"无法连接 API 服务器 ({_llm_config.get('base_url', '')})，请检查地址和网络"
        else:
            hint = f"AI 生成失败 [{type(e).__name__}]: {err_msg[:60]}"
        return {"soups": [], "error": hint}

def _build_ai_prompt(difficulty, count, direction):
    """构建 AI 出题 prompt"""
    dir_name = {"random":"🎲 综合随机","mystery":"🔍 悬疑推理","horror":"👻 恐怖惊悚","daily":"☕ 日常推理","sci-fi":"🚀 科幻想象","ethics":"💔 情感伦理","fairy-tale":"🧙 黑暗童话","urban":"🌃 都市传说","history":"📜 历史秘闻","dark-humor":"😈 黑色幽默","psychological":"🌀 心理迷宫"}.get(direction, direction)
    dir_prompt = _DIRECTION_PROMPTS.get(direction, "")
    diff_constraint = _DIFFICULTY_CONSTRAINTS.get(difficulty, _DIFFICULTY_CONSTRAINTS["medium"])
    return f"""你是一个海龟汤谜题生成器。请生成{count}个海龟汤谜题。

难度：{difficulty}（要求：{diff_constraint}）
方向：{dir_name}。{dir_prompt}

每个谜题是一个JSON对象，包含以下字段：
- title: 标题（简短有力）
- surface: 汤面（有趣有悬念的谜面）
- bottom: 汤底（合理完整的谜底）
- keywords: 关键词数组（3-5个）
- difficulty: 难度，值为"{difficulty}"
- direction: 方向，值为"{direction}"

以JSON数组格式返回。示例如下：
[
  {{
    "title": "雨中的空椅子",
    "surface": "一个雨夜，小明看到公园的长椅上放着一把湿透的伞。第二天他听说昨晚有人在那张长椅上坐着等了一夜。小明看了看那把伞，吓得跑掉了。为什么？",
    "bottom": "那把伞是小明自己遗忘的。昨晚他在梦游状态下冒雨去了公园，把伞放在椅子上，然后空手回家。但他完全不记得这件事，所以看到自己的伞出现在别人描述中的地点时，以为遇到了灵异事件。",
    "keywords": ["梦游", "雨伞", "遗忘", "长椅"],
    "difficulty": "{difficulty}",
    "direction": "{direction}"
  }}
]

仅返回JSON数组，不要markdown包裹，不要额外文字。"""


# ── HTTP Handler ──
class Handler(BaseHTTPRequestHandler):
    """轻量 HTTP 服务器 — 提供页面 + API 模拟"""

    def _parse_path(self):
        parsed = urlparse(self.path)
        return parsed.path.rstrip("/") or "/"

    def _read_body(self):
        content_len = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_len) if content_len else b"{}"

    # ── GET ──
    def do_GET(self):
        path = self._parse_path()

        # 页面路由
        if path == "/":
            return self._html(ADMIN_HTML_RAW)
        if path == "/overlay":
            overlay_html = _apply_theme(OVERLAY_HTML_RAW, _mock_state.active_theme)
            return self._html(overlay_html)

        # TTS 音频文件服务
        if path.startswith("/audio/"):
            filename = os.path.basename(path[len("/audio/"):])
            filepath = os.path.join(_TTS_DIR, filename)
            if os.path.isfile(filepath):
                file_size = os.path.getsize(filepath)
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(file_size))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                with open(filepath, "rb") as f:
                    self.wfile.write(f.read())
                return
            return self._json({"error": "not found"}, status=404)

        # API 路由
        routes = {
            "/api/health": lambda: {"status": "ok", "phase": _mock_state.phase, "connections": 0},
            "/api/config": lambda: {
                "api_key_configured": bool(_llm_config.get("api_key")),
                "base_url": _llm_config.get("base_url", ""),
                "model": _llm_config.get("model", ""),
                "reasoning": _llm_config.get("reasoning", True),
                "qa_api_key_configured": bool(_llm_config.get("qa_api_key")),
                "qa_base_url": _llm_config.get("qa_base_url", ""),
                "qa_model": _llm_config.get("qa_model", ""),
            },
            "/api/admin/anti-stall-config": lambda: dict(_anti_stall_config),
            "/api/admin/game-config": lambda: dict(_game_config),
            "/api/admin/slots": lambda: {"slots": _build_slots()},
            "/api/admin/themes": lambda: {"themes": [
                {"id": t["id"], "name": t["name"], "accent": t["accent"],
                 "preview": t["vars"]["--bg-grad"]}
                for t in BUILTIN_THEMES.values()
            ]},
            "/api/theme": lambda: {"theme_id": _mock_state.active_theme},
            "/api/admin/banned-words": lambda: {"words": _banned_words},
            "/api/triggers": lambda: {"triggers": []},
            "/api/admin/llm-models": lambda: _fetch_llm_models(),
            "/api/admin/metrics": lambda: _mock_state.to_dict(),
            "/api/leaderboard": lambda: {"leaderboard": []},
            "/api/tts/config": lambda: _build_tts_config(),
            "/api/admin/soups": lambda: _filter_soups(urlparse(self.path).query),
            "/api/admin/gifts/search": lambda: {"gifts": _search_gifts(unquote(urlparse(self.path).query.split("=")[-1] if "q=" in self.path else ""))},
            "/api/tts/cosyvoice-deploy": lambda: _get_cv_deploy_status(),
            "/api/admin/ai-directions": lambda: {"directions": [
                {"id":"random","name":"🎲 综合随机","desc":"AI自由发挥，不限定方向"},
                {"id":"mystery","name":"🔍 悬疑推理","desc":"谋杀、失踪、盗窃等推理解谜"},
                {"id":"horror","name":"👻 恐怖惊悚","desc":"灵异、鬼怪、心理恐怖"},
                {"id":"daily","name":"☕ 日常推理","desc":"日常生活隐藏的反转真相"},
                {"id":"sci-fi","name":"🚀 科幻想象","desc":"AI、时空旅行、未来科技"},
                {"id":"ethics","name":"💔 情感伦理","desc":"爱情、亲情、友情、人性抉择"},
                {"id":"fairy-tale","name":"🧙 黑暗童话","desc":"经典童话/故事的暗黑反转"},
                {"id":"urban","name":"🌃 都市传说","desc":"现代都市诡异怪谈"},
                {"id":"history","name":"📜 历史秘闻","desc":"历史事件/人物的另类解读"},
                {"id":"dark-humor","name":"😈 黑色幽默","desc":"讽刺荒诞、出人意料"},
                {"id":"psychological","name":"🌀 心理迷宫","desc":"人格分裂、记忆陷阱、梦境"}
            ]},
        }

        # ── 授权 API ──
        if path == "/api/auth/status":
            return self._json(_get_auth_status())
        if path == "/api/auth/start-trial":
            lic.start_trial()
            return self._json({"ok": True, "status": _get_auth_status()})

        handler = routes.get(path)
        if handler:
            return self._json(handler())
        self._json({"error": "not found"}, status=404)

    # ── POST ──
    def do_POST(self):
        path = self._parse_path()
        raw = self._read_body()

        # ── CosyVoice 说话人注册（multipart，需在 JSON 解码前处理）──
        if path == "/api/tts/cosyvoice-speaker":
            ct = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ct:
                return self._json({"ok": False, "error": "需要 multipart 上传"})
            parts = _parse_multipart(raw, ct)
            fdata = parts.get("file", {})
            if not fdata.get("content"):
                return self._json({"ok": False, "error": "未找到上传文件"})
            spk_name = parts.get("name", "").strip() if isinstance(parts.get("name"), str) else ""
            if not spk_name:
                fn = fdata.get("filename", "")
                spk_name = os.path.splitext(os.path.basename(fn))[0] if fn else ""
            if not spk_name:
                spk_name = f"upload_{uuid.uuid4().hex[:8]}"
            # 优先保存到 CosyVoiceV7/asset（开发模式），否则保存到 tts_audio/cosyvoice/
            cv_asset = os.path.join(_PARENT, "CosyVoiceV7", "asset")
            if not os.path.isdir(cv_asset):
                cv_asset = os.path.join(_TTS_DIR, "cosyvoice")
            os.makedirs(cv_asset, exist_ok=True)
            fname = f"zero_shot_prompt_{spk_name}.wav"
            dest = os.path.join(cv_asset, fname)
            with open(dest, "wb") as f:
                f.write(fdata["content"])
            registered = False
            try:
                import tts_engine
                registered = tts_engine.register_cosyvoice_speaker(spk_name, dest)
            except Exception:
                pass
            # 更新 speaker 列表供下拉框使用
            spkers = _tts_config.get("cosyvoice_speakers", {})
            spkers[spk_name] = {"available": True, "name": spk_name}
            _tts_config["cosyvoice_speakers"] = spkers
            return self._json({"ok": True, "spk_id": spk_name, "name": spk_name, "registered": registered})

        # ── CosyVoice 说话人删除 ──
        if path == "/api/tts/cosyvoice-speaker/delete":
            try:
                body = raw.decode("utf-8")
            except UnicodeDecodeError:
                body = raw.decode("gbk", errors="replace")
            try:
                data = json.loads(body)
                spk_id = data.get("spk_id", "")
                if not spk_id:
                    return self._json({"ok": False, "error": "缺少 spk_id"})
                if spk_id == "default":
                    return self._json({"ok": False, "error": "不能删除默认音色"})
                # 尝试从引擎删除
                try:
                    import tts_engine
                    tts_engine.remove_cosyvoice_speaker(spk_id)
                except Exception:
                    pass
                # 总是从配置中移除
                spkers = _tts_config.get("cosyvoice_speakers", {})
                removed = spkers.pop(spk_id, None) is not None
                _tts_config["cosyvoice_speakers"] = spkers
                return self._json({"ok": True, "removed_from_config": removed})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)[:100]})

        try:
            body = raw.decode("utf-8")
        except UnicodeDecodeError:
            body = raw.decode("gbk", errors="replace")

        # ── 题库操作（需要实际修改 SOUPS_DATA）──
        if path == "/api/admin/soups/delete":
            try:
                sid = json.loads(body).get("id", "")
                global SOUPS_DATA
                SOUPS_DATA = [s for s in SOUPS_DATA if s.get("id") != sid]
                _save_soups()
            except Exception:
                pass
            return self._json({"ok": True})
        if path == "/api/admin/soups/add":
            try:
                data = json.loads(body)
                new_id = f"soup-{len(SOUPS_DATA)+1:03d}"
                SOUPS_DATA.append({
                    "id": data.get("id", new_id),
                    "title": data.get("title", ""),
                    "surface": data.get("surface", ""),
                    "bottom": data.get("bottom", ""),
                    "keywords": data.get("keywords", []),
                    "difficulty": data.get("difficulty", "medium"),
                })
                _save_soups()
            except Exception:
                pass
            return self._json({"ok": True})
        if path == "/api/admin/soups/import":
            try:
                data = json.loads(body)
                for s in data.get("soups", []):
                    if s.get("surface") and s.get("bottom"):
                        s["id"] = s.get("id", f"soup-{len(SOUPS_DATA)+1:03d}")
                        s["keywords"] = s.get("keywords", [])
                        s["difficulty"] = s.get("difficulty", "medium")
                        SOUPS_DATA.append(s)
                _save_soups()
            except Exception:
                pass
            return self._json({"ok": True, "count": 1})
        if path == "/api/admin/ai-approve":
            try:
                data = json.loads(body)
                soup = data.get("soup", {})
                if soup.get("surface") and soup.get("bottom"):
                    soup["id"] = soup.get("id", f"soup-{len(SOUPS_DATA)+1:03d}")
                    SOUPS_DATA.append(soup)
                    _save_soups()
            except Exception:
                pass
            return self._json({"ok": True})

        # ── 授权激活 ──
        if path == "/api/auth/activate":
            try:
                data = json.loads(body)
                key = data.get("key", "").strip()
                if not key:
                    return self._json({"ok": False, "error": "请输入授权码"})
                result = _activate_auth(key)
                return self._json({**result, "status": _get_auth_status() if result.get("ok") else None})
            except Exception:
                return self._json({"ok": False, "error": "激活请求解析失败"})

        # ── LLM 配置保存 ──
        if path == "/api/config":
            try:
                data = json.loads(body)
                changed = False
                if data.get("api_key"):
                    _llm_config["api_key"] = data["api_key"]; changed = True
                if data.get("base_url"):
                    _llm_config["base_url"] = data["base_url"]; changed = True
                if data.get("model"):
                    _llm_config["model"] = data["model"]; changed = True
                if "reasoning" in data:
                    _llm_config["reasoning"] = bool(data["reasoning"]); changed = True
                # 问答模型配置
                if data.get("qa_api_key"):
                    _llm_config["qa_api_key"] = data["qa_api_key"]; changed = True
                if data.get("qa_base_url"):
                    _llm_config["qa_base_url"] = data["qa_base_url"]; changed = True
                if data.get("qa_model"):
                    _llm_config["qa_model"] = data["qa_model"]; changed = True
                if changed:
                    _save_llm_config()
            except Exception:
                pass
            return self._json({"ok": True, "model": _llm_config.get("model", ""), "base_url": _llm_config.get("base_url", "")})

        # ── LLM ping（测试连接）──
        if path == "/api/admin/llm-ping":
            return self._json(_llm_ping())
        if path == "/api/admin/qa-ping":
            try:
                result = _llm_classify("测试", "测试答案", ["测试"])
                return self._json({"ok": True, "model": _llm_config.get("qa_model", ""), "response": result,
                                   "msg": f"✅ 问答模型 {_llm_config.get('qa_model', '')} 响应正常"})
            except Exception as e:
                return self._json({"ok": False, "model": _llm_config.get("qa_model", ""), "error": str(e)[:100],
                                   "msg": "❌ 问答模型检测失败"})

        # ── AI 出题 ──
        if path == "/api/admin/ai-generate":
            try:
                data = json.loads(body)
                diff = data.get("difficulty", "medium")
                count = data.get("count", 5)
                direction = data.get("direction", "random")
                return self._json(_ai_generate(diff, count, direction))
            except Exception:
                return self._json({"soups": [], "error": "AI 生成请求解析失败"})

        # ── 游戏弹幕分类 ──
        if path == "/api/classify":
            try:
                data = json.loads(body)
                text = data.get("text", "")
                answer = data.get("answer", "")
                keywords = data.get("keywords", [])
                result = _llm_classify(text, answer, keywords)
                # 猜中则自动揭示一字
                if result == "是" and _mock_state.phase in ("reading", "playing"):
                    _reveal_random_char()
                    _check_game_complete()
                return self._json({"text": text, "answerType": result, "layer": "llm"})
            except Exception:
                return self._json({"text": "", "answerType": "不是", "layer": "error"})

        # ── 游戏控制端点（实际修改状态） ──
        if path == "/api/game/start":
            try:
                data = json.loads(body)
                difficulty = data.get("difficulty", _mock_state.current_difficulty) or "medium"
                soup_id = data.get("soup_id", "")
                _do_game_start(difficulty=difficulty, soup_id=soup_id)
                return self._json({"ok": True, "surface": _mock_state.soup_text, "difficulty": difficulty})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)[:100]})

        if path == "/api/admin/reset":
            _mock_state.reset()
            asyncio.run_coroutine_threadsafe(_ws_broadcast({"type": "game_end"}), _ws_loop)
            return self._json({"ok": True})

        if path == "/api/admin/force-reveal":
            for cs in _mock_state.char_states:
                cs["revealed"] = True
            _mock_state.phase = "complete"
            _bcast({"type": "reveal_update", "charStates": _mock_state.char_states})
            _bcast({"type": "game_end", "winner": "系统", "charStates": _mock_state.char_states})
            return self._json({"ok": True})

        # ── 礼物效果触发 ──
        if path == "/api/effect/trigger":
            try:
                d = json.loads(body)
                slot_id = d.get("slot_id", "")
                user = d.get("user", "系统")
                ok = False
                if slot_id == "effect_complete":
                    for cs in _mock_state.char_states:
                        if cs["isContent"] and not cs["revealed"]:
                            cs["revealed"] = True
                    _mock_state.phase = "complete"
                    _bcast({"type": "reveal_update", "charStates": _mock_state.char_states})
                    _bcast({"type": "game_end", "winner": user, "charStates": _mock_state.char_states})
                    ok = True
                elif slot_id == "effect_reveal1":
                    ok = _reveal_random_char()
                elif slot_id == "effect_reveal_sentence":
                    ok = _reveal_sentence()
                elif slot_id == "effect_reveal_30p":
                    ok = _reveal_30p()
                if ok:
                    _bcast({"type": "gift_effect", "user": user, "slotId": slot_id, "giftName": d.get("gift_name", "")})
                    _check_game_complete()
                return self._json({"ok": ok})
            except Exception:
                return self._json({"ok": False})

        if path == "/api/admin/difficulty":
            try:
                _mock_state.current_difficulty = json.loads(body).get("difficulty", "medium")
            except Exception:
                pass
            return self._json({"ok": True})

        if path == "/api/admin/anti-stall-config":
            try:
                d = json.loads(body)
                _anti_stall_config["enabled"] = d.get("enabled", True)
                _anti_stall_config["interval"] = int(d.get("interval", 180))
                _anti_stall_config["danmaku"] = int(d.get("danmaku", 50))
            except Exception:
                pass
            return self._json({"ok": True})

        if path == "/api/admin/game-config":
            try:
                _game_config["roundTimeout"] = int(json.loads(body).get("roundTimeout", 600))
            except Exception:
                pass
            return self._json({"ok": True})

        if path == "/api/admin/banned-words":
            try:
                d = json.loads(body)
                # admin.js 发 {word: "xxx"} 添加单个词
                if "word" in d:
                    w = d["word"].strip()
                    if w and w not in _banned_words:
                        _banned_words.append(w)
                        _save_banned_words()
                # 兼容批处理 {words: [...]}
                elif "words" in d:
                    _banned_words.clear()
                    _banned_words.extend(d["words"])
                    _save_banned_words()
            except Exception:
                pass
            return self._json({"ok": True})

        if path == "/api/admin/config-reload":
            return self._json({"ok": True, "msg": "独立模式无需重载"})

        # ── 槽位操作 ──
        if path == "/api/admin/slots/assign":
            try:
                d = json.loads(body)
                sid = str(d.get("slot_id", ""))
                _slot_overrides[sid] = {
                    "gift_name": d.get("gift_name", ""),
                    "gift_coins": d.get("gift_coins", 0),
                    "gift_icon": d.get("gift_icon", ""),
                }
                asyncio.run_coroutine_threadsafe(_ws_broadcast({"type": "slots_updated"}), _ws_loop)
            except Exception:
                pass
            return self._json({"ok": True})

        if path == "/api/admin/slots/toggle":
            try:
                d = json.loads(body)
                sid = str(d.get("slot_id", ""))
                _slot_overrides.setdefault(sid, {})["enabled"] = d.get("enabled", True)
                asyncio.run_coroutine_threadsafe(_ws_broadcast({"type": "slots_updated"}), _ws_loop)
            except Exception:
                pass
            return self._json({"ok": True})

        if path == "/api/admin/slots/like-config":
            try:
                d = json.loads(body)
                sid = str(d.get("slot_id", ""))
                over = _slot_overrides.setdefault(sid, {})
                over["like_mode"] = d.get("like_mode", False)
                over["like_threshold"] = d.get("like_threshold", 0)
                asyncio.run_coroutine_threadsafe(_ws_broadcast({"type": "slots_updated"}), _ws_loop)
            except Exception:
                pass
            return self._json({"ok": True})

        # ── TTS 配置持久化 ──
        if path == "/api/tts/config":
            try:
                data = json.loads(body)
                for key in ("engine", "voice", "rate", "cosyvoice_spk"):
                    if key in data:
                        _tts_config[key] = data[key]
            except Exception:
                pass
            return self._json({"ok": True})

        # 主题切换（需要存储状态）
        if path == "/api/admin/theme":
            try:
                data = json.loads(body)
                tid = data.get("theme_id", "")
                if tid in BUILTIN_THEMES:
                    _mock_state.active_theme = tid
            except Exception:
                pass
            return self._json({"ok": True})

        # ── TTS 语音合成（实际调用 edge-tts） ──
        if path == "/api/tts/synthesize":
            try:
                data = json.loads(body)
                text = data.get("text", "")
                if not text:
                    return self._json({"ok": False, "error": "text 为空"})
                filepath, url = asyncio.run(_generate_tts_async(text))
                if filepath and os.path.isfile(filepath):
                    # 返回音频数据
                    ext = os.path.splitext(filepath)[1].lower()
                    file_size = os.path.getsize(filepath)
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/wav" if ext == ".wav" else "audio/mpeg")
                    self.send_header("Content-Length", str(file_size))
                    self.send_header("X-TTS-Rate", str(_tts_config.get("rate", 1.0)))
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    with open(filepath, "rb") as f:
                        self.wfile.write(f.read())
                    return
                engine = _tts_config.get("engine", "edge")
                msg = "CosyVoice 合成失败，请检查部署状态" if engine == "cosyvoice" else "TTS 合成失败"
                return self._json({"ok": False, "error": msg}, status=400)
            except ImportError:
                return self._json({"ok": False, "error": "edge-tts 未安装"})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)[:100]})

        special = {
            "/api/admin/ai-directions": {"directions": [
                {"id":"random","name":"🎲 综合随机","desc":"AI自由发挥，不限定方向"},
                {"id":"mystery","name":"🔍 悬疑推理","desc":"谋杀、失踪、盗窃等推理解谜"},
                {"id":"horror","name":"👻 恐怖惊悚","desc":"灵异、鬼怪、心理恐怖"},
                {"id":"daily","name":"☕ 日常推理","desc":"日常生活隐藏的反转真相"},
                {"id":"sci-fi","name":"🚀 科幻想象","desc":"AI、时空旅行、未来科技"},
                {"id":"ethics","name":"💔 情感伦理","desc":"爱情、亲情、友情、人性抉择"},
                {"id":"fairy-tale","name":"🧙 黑暗童话","desc":"经典童话/故事的暗黑反转"},
                {"id":"urban","name":"🌃 都市传说","desc":"现代都市诡异怪谈"},
                {"id":"history","name":"📜 历史秘闻","desc":"历史事件/人物的另类解读"},
                {"id":"dark-humor","name":"😈 黑色幽默","desc":"讽刺荒诞、出人意料"},
                {"id":"psychological","name":"🌀 心理迷宫","desc":"人格分裂、记忆陷阱、梦境"}
            ]},
            "/api/admin/ai-approve-all": {"ok": True},
            "/api/admin/tts/cosyvoice": {"ok": False, "error": "独立模式无 TTS"},
            "/api/tts/cosyvoice-uninstall": {"ok": True},
        }
        handler = special.get(path)
        if handler is not None:
            return self._json(handler)
        # CosyVoice 部署（独立处理 — 需要动态状态）
        if path == "/api/tts/cosyvoice-deploy":
            with _cv_deploy_lock:
                cur = _cv_deploy_progress.get("step", "")
                if cur and cur != "error":
                    return self._json({"ok": False, "error": "部署正在进行或已完成"})
                _cv_deploy_progress.clear()
                _cv_deploy_progress["step"] = "starting"
                _cv_deploy_progress["pct"] = 0
                _cv_deploy_progress["text"] = "启动部署..."
            t = threading.Thread(target=_run_cosyvoice_deploy, daemon=True)
            t.start()
            return self._json({"ok": True})
        self._json({"error": "not found"}, status=404)

    # ── PUT（违禁词批量设置）──
    def do_PUT(self):
        self._json({"ok": True})

    # ── DELETE ──
    def do_DELETE(self):
        path = self._parse_path()
        if path == "/api/admin/banned-words":
            try:
                raw = self._read_body()
                d = json.loads(raw.decode("utf-8"))
                word = d.get("word", "")
                if word and word in _banned_words:
                    _banned_words.remove(word)
                    _save_banned_words()
            except Exception:
                pass
            return self._json({"ok": True})
        self._json({"ok": True})

    # ── Response helpers ──
    def _html(self, content: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _json(self, data: dict, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, fmt, *args):
        if args and args[1] != "/api/health":
            print(f"  [HTTP] {args[0]} {args[1]} {args[2]}")


# ── WebSocket Handler ──
async def _ws_broadcast(msg: dict):
    """向所有连接的 WS 客户端广播消息"""
    global _ws_clients
    if not _ws_clients:
        return
    text = json.dumps(msg, ensure_ascii=False)
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send(text)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


async def _ws_serve(host, port):
    """启动 WebSocket 服务器 —— 心跳、弹幕、游戏广播"""
    global _ws_loop
    _ws_loop = asyncio.get_event_loop()
    try:
        import websockets
    except ImportError:
        print("[WS] websockets 未安装，WebSocket 不可用")
        return

    async def handler(websocket):
        _ws_clients.add(websocket)
        try:
            await websocket.send(json.dumps({"type": "connected", "standalone": True, "phase": _mock_state.phase}))
            # 如果游戏进行中，补发完整状态，让后连入的投屏端能同步
            if _mock_state.phase not in ("idle", "lobby") and _mock_state.soup_text:
                await websocket.send(json.dumps({
                    "type": "state_sync",
                    "room": {
                        "phase": _mock_state.phase,
                        "soup_text": _mock_state.soup_text,
                        "char_states": _mock_state.char_states,
                        "difficulty_name": _mock_state.current_difficulty or "",
                    }
                }))
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "")
                    if msg_type == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))
                    elif msg_type == "danmaku":
                        try:
                            await _handle_danmaku(data.get("data", {}))
                        except Exception as e:
                            print(f"[WS] danmaku error: {e}")
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        finally:
            _ws_clients.discard(websocket)

    async def serve():
        async with websockets.serve(handler, host, port, ping_interval=30):
            # 后台任务：计时器 + 防卡死
            t1 = asyncio.create_task(_timer_loop())
            t2 = asyncio.create_task(_anti_stall_loop())
            _background_tasks.add(t1)
            _background_tasks.add(t2)
            t1.add_done_callback(_background_tasks.discard)
            t2.add_done_callback(_background_tasks.discard)
            await asyncio.Future()

    try:
        await serve()
    except OSError as e:
        print(f"[WS] 端口 {port} 被占用: {e}")


# ── Overlay JS API（PyWebView） ──
class OverlayApi:
    """PyWebView JS API — 从 admin 页面控制 overlay 窗口"""
    def __init__(self, overlay_url: str):
        self._overlay_url = overlay_url
        self._window = None
        self._lock = threading.Lock()

    def open_overlay(self) -> dict:
        with self._lock:
            if self._window is not None:
                try:
                    self._window.show()
                    return {"ok": True, "already_open": True}
                except Exception:
                    self._window = None
            import webview
            self._window = webview.create_window(
                "海龟汤 · 投屏端",
                url=self._overlay_url,
                width=480, height=854, resizable=True,
            )
            self._window.events.closed += self._on_closed
        return {"ok": True}

    def close_overlay(self) -> dict:
        with self._lock:
            if self._window is None:
                return {"ok": True, "already_closed": True}
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
        return {"ok": True}

    def _on_closed(self):
        self._window = None


# ── 入口 ──
def main():
    import argparse
    parser = argparse.ArgumentParser(description="海龟汤 · 独立集成版")
    parser.add_argument("--port", type=int, default=PORT, help=f"HTTP 端口（默认 {PORT}）")
    parser.add_argument("--backend", type=str, default=None,
                        help="外部后端地址（如 http://myserver:3010），省略则使用模拟模式")
    parser.add_argument("--no-gui", action="store_true", help="无 GUI 模式（仅启动服务器）")
    args = parser.parse_args()

    # ── 授权状态（静默检查，不再弹窗阻塞） ──
    auth = lic.check()

    port = args.port
    ws_port = port + 1
    server_url = f"http://{HOST}:{port}"
    ws_url = f"ws://{HOST}:{ws_port}/ws"

    # 注入 HTML
    global ADMIN_HTML_RAW, OVERLAY_HTML_RAW
    if args.backend:
        backend = args.backend.rstrip("/")
        b_ws_url = backend.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        ADMIN_HTML_RAW = inject_html(ADMIN_HTML_RAW, backend, b_ws_url)
        OVERLAY_HTML_RAW = inject_html(OVERLAY_HTML_RAW, backend, b_ws_url)
        mode = f"后端: {backend}"
    else:
        ADMIN_HTML_RAW = inject_html(ADMIN_HTML_RAW, server_url, ws_url)
        OVERLAY_HTML_RAW = inject_html(OVERLAY_HTML_RAW, server_url, ws_url)
        mode = "独立模式（模拟 API，无后端依赖）"

    print("=" * 50)
    print("  海龟汤 · 独立集成版")
    print(f"  {mode}")
    print("=" * 50)
    print(f"  控制面板: {server_url}/")
    print(f"  投屏端:   {server_url}/overlay")
    print(f"  WebSocket: {ws_url}")
    if auth.get("source") == "trial":
        remain = lic.format_remaining(auth.get("remaining_seconds", 0))
        print(f"  授权: 试用模式（剩余 {remain}）")
    elif auth.get("source") == "license":
        if auth.get("is_permanent"):
            print(f"  授权: 永久授权")
        else:
            print(f"  授权: 授权码（剩余 {auth.get('remaining_days', 0)} 天）")
    print("=" * 50)

    # ── 启动 HTTP 服务器 ──
    httpd = HTTPServer((HOST, port), Handler)
    http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()

    # ── 启动 WebSocket 服务器 ──
    ws_thread = threading.Thread(
        target=lambda: asyncio.run(_ws_serve(HOST, ws_port)),
        daemon=True,
    )
    ws_thread.start()

    # ── 后台预加载 CosyVoice（不阻塞 HTTP）──
    t = threading.Thread(target=_background_preload_cosyvoice, daemon=True)
    t.start()

    if args.no_gui:
        print("\n[无 GUI 模式] 按 Ctrl+C 停止...")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("\n正在关闭...")
        finally:
            httpd.shutdown()
        return

    # ── GUI 模式 —— PyWebView ──
    if args.backend:
        overlay_url = f"{args.backend.rstrip('/')}/overlay"
    else:
        overlay_url = f"{server_url}/overlay"

    try:
        import webview
        webview.create_window(
            "海龟汤 · 控制台"
            if not args.backend else "海龟汤 · 控制台（远程模式）",
            url=server_url,
            width=1280, height=800, resizable=True,
            js_api=OverlayApi(overlay_url),
        )
        webview.start(private_mode=True, debug=False)
    except ImportError:
        import webbrowser
        webbrowser.open(server_url)
        httpd.serve_forever()
    except Exception as e:
        print(f"[错误] GUI 启动失败: {e}")
        traceback.print_exc()
        import webbrowser
        webbrowser.open(server_url)
        httpd.serve_forever()
    finally:
        httpd.shutdown()
    print("[独立版] 已退出")


if __name__ == "__main__":
    main()
