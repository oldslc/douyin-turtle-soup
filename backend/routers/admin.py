"""
管理面板路由 — /api/admin/* + /api/theme + /api/triggers
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from admin import ADMIN_HTML
from state import (
    room, manager, db, slot_manager, spam_filter, theme_manager, SOUPS,
    LLM_MODEL,
    ANTI_STALL_ENABLED, ANTI_STALL_INTERVAL, ANTI_STALL_DANMAKU,
    ROUND_TIMEOUT,
    GIFT_LIBRARY, DIFFICULTY_NAME_MAP,
    get_client, reload_config,
)
import json
import time

router = APIRouter(tags=["admin"])

class BannedWordReq(BaseModel):
    word: str

class AssignSlotReq(BaseModel):
    slot_id: str
    gift_name: str

class ToggleSlotReq(BaseModel):
    slot_id: str
    enabled: bool

class SlotLikeConfigReq(BaseModel):
    slot_id: str
    like_mode: bool
    like_threshold: int = 500

class TriggerReq(BaseModel):
    type: str
    target: str = "*"
    effect: str = ""
    value: str = ""
    enabled: int = 1

# ── 违禁词 ──
@router.get("/api/admin/banned-words")
async def get_banned_words():
    return {"words": spam_filter.banned.get_all()}

@router.post("/api/admin/banned-words")
async def add_banned_word(req: BannedWordReq):
    ok = spam_filter.banned.add(req.word)
    return {"ok": ok, "word": req.word}

@router.delete("/api/admin/banned-words")
async def delete_banned_word(req: BannedWordReq):
    ok = spam_filter.banned.remove(req.word)
    return {"ok": ok, "word": req.word}

@router.put("/api/admin/banned-words")
async def set_banned_words(req: list[str]):
    spam_filter.banned.set_all(req)
    return {"ok": True, "count": len(req)}

# ── 配置 ──
@router.post("/api/admin/config-reload")
async def admin_reload_config():
    ok, msg = reload_config()
    return {"ok": ok, "msg": msg}

# ── 防卡死配置 ──
@router.get("/api/admin/anti-stall-config")
async def get_anti_stall_config():
    global ANTI_STALL_ENABLED, ANTI_STALL_INTERVAL, ANTI_STALL_DANMAKU
    return {"enabled": ANTI_STALL_ENABLED, "interval": ANTI_STALL_INTERVAL, "danmaku": ANTI_STALL_DANMAKU}

@router.post("/api/admin/anti-stall-config")
async def set_anti_stall_config(req: dict):
    global ANTI_STALL_ENABLED, ANTI_STALL_INTERVAL, ANTI_STALL_DANMAKU
    if "enabled" in req:
        ANTI_STALL_ENABLED = bool(req["enabled"])
    if "interval" in req:
        ANTI_STALL_INTERVAL = max(30, int(req["interval"]))
    if "danmaku" in req:
        ANTI_STALL_DANMAKU = max(5, int(req["danmaku"]))
    return {"ok": True}

# ── 游戏时长 ──
@router.get("/api/admin/game-config")
async def get_game_config():
    return {"roundTimeout": ROUND_TIMEOUT}

@router.post("/api/admin/game-config")
async def set_game_config(req: dict):
    global ROUND_TIMEOUT
    if "roundTimeout" in req:
        val = int(req["roundTimeout"])
        ROUND_TIMEOUT = max(30, min(3600, val))
        if db is not None:
            db.set_setting("round_timeout", str(ROUND_TIMEOUT))
        print(f"[Config] 游戏时长已更新: {ROUND_TIMEOUT}秒")
    return {"ok": True}

# ── 礼物槽位管理 ──
@router.get("/api/admin/slots")
async def get_slots():
    return {"slots": slot_manager.get_all_slots()}

@router.post("/api/admin/slots/assign")
async def assign_slot(req: AssignSlotReq):
    slot_manager.assign_gift(req.slot_id, req.gift_name)
    if db is not None:
        slot_manager.save_to_db(db)
    await manager.broadcast({"type": "slots_updated"})
    return {"ok": True}

@router.post("/api/admin/slots/toggle")
async def toggle_slot(req: ToggleSlotReq):
    slot_manager.set_enabled(req.slot_id, req.enabled)
    if db is not None:
        slot_manager.save_to_db(db)
    await manager.broadcast({"type": "slots_updated"})
    return {"ok": True}

@router.post("/api/admin/slots/like-config")
async def set_slot_like_config(req: SlotLikeConfigReq):
    slot_manager.set_like_config(req.slot_id, req.like_mode, req.like_threshold)
    if db is not None:
        slot_manager.save_to_db(db)
    await manager.broadcast({"type": "slots_updated"})
    return {"ok": True}

@router.get("/api/admin/gifts/search")
async def search_gifts(q: str = ""):
    return {"gifts": slot_manager.search_gifts(q)}

# ── 难度控制 ──
@router.post("/api/admin/difficulty")
async def admin_set_difficulty(req: dict):
    diff = req.get("difficulty", "medium")
    room.next_difficulty = diff
    name = {"easy":"简单","medium":"一般","hard":"困难","hell":"地狱","void":"无人区","auto":"自适应"}.get(diff, diff)
    await manager.broadcast({"type":"difficulty_scheduled", "nextDifficulty": diff, "nextDifficultyName": name})
    return {"ok": True, "difficulty": diff}

# ── 强制揭示 ──
@router.post("/api/admin/force-reveal")
async def admin_force_reveal():
    if room.char_states:
        for s in room.char_states:
            if s["isContent"] and not s["revealed"]:
                s["revealed"] = True
        room.phase = "complete"
        await manager.broadcast({"type": "reveal_update", "charStates": room.char_states})
    await manager.broadcast({"type": "game_end", "winner": "管理员"})
    return {"ok": True}

# ── 重置游戏 ──
@router.post("/api/admin/reset")
async def admin_reset():
    room.reset()
    await manager.broadcast({"type": "game_end", "winner": "系统"})
    return {"ok": True}

# ── 题库管理 ──
@router.get("/api/admin/soups")
async def admin_get_soups(difficulty: str = ""):
    if difficulty:
        candidates = [s for s in SOUPS if s.get("difficulty") == difficulty]
    else:
        candidates = SOUPS
    return {"soups": candidates}

@router.post("/api/admin/soups/delete")
async def admin_delete_soup(req: dict):
    sid = req.get("id", "")
    global SOUPS  # noqa: F811, F824
    import state
    state.SOUPS = [s for s in SOUPS if s.get("id") != sid]
    return {"ok": True}

@router.post("/api/admin/soups/add")
async def admin_add_soup(req: dict):
    new_id = f"soup-{len(SOUPS)+1:03d}"
    soup = {
        "id": req.get("id", new_id),
        "title": req.get("title", ""),
        "surface": req.get("surface", ""),
        "bottom": req.get("bottom", ""),
        "keywords": req.get("keywords", []),
        "difficulty": req.get("difficulty", "medium"),
    }
    SOUPS.append(soup)
    return {"ok": True, "id": soup["id"]}

@router.post("/api/admin/soups/import")
async def admin_import_soups(req: dict):
    soups = req.get("soups", [])
    count = 0
    for s in soups:
        if not s.get("surface") or not s.get("bottom"):
            continue
        s["id"] = s.get("id", f"soup-{len(SOUPS)+1:03d}")
        s["keywords"] = s.get("keywords", [])
        s["difficulty"] = s.get("difficulty", "medium")
        SOUPS.append(s)
        count += 1
    return {"ok": True, "count": count}

# ── AI 出题 ──
DIRECTION_MAP = {
    "random":        {"name": "🎲 综合随机",   "desc": "AI自由发挥，不限定方向"},
    "mystery":       {"name": "🔍 悬疑推理",   "desc": "谋杀、失踪、盗窃等推理解谜"},
    "horror":        {"name": "👻 恐怖惊悚",   "desc": "灵异、鬼怪、心理恐怖"},
    "daily":         {"name": "☕ 日常推理",   "desc": "日常生活隐藏的反转真相"},
    "sci-fi":        {"name": "🚀 科幻想象",   "desc": "AI、时空旅行、未来科技"},
    "ethics":        {"name": "💔 情感伦理",   "desc": "爱情、亲情、友情、人性抉择"},
    "fairy-tale":    {"name": "🧙 黑暗童话",   "desc": "经典童话/故事的暗黑反转"},
    "urban":         {"name": "🌃 都市传说",   "desc": "现代都市诡异怪谈"},
    "history":       {"name": "📜 历史秘闻",   "desc": "历史事件/人物的另类解读"},
    "dark-humor":    {"name": "😈 黑色幽默",   "desc": "讽刺荒诞、出人意料"},
    "psychological": {"name": "🌀 心理迷宫",   "desc": "人格分裂、记忆陷阱、梦境"},
}

DIFFICULTY_CONSTRAINTS = {
    "easy":   "简单难度：单步推理即可解开，剧情直白零误导，线索明显摆在汤面中，适合新手快速上手。",
    "medium": "一般难度：两步推理或一次关键反转，线索半隐半现，需要跳出初始视角重新审视。",
    "hard":   "困难难度：三步以上逻辑链，多层反转或巧妙误导，线索分散在不同细节中，需要串联推敲。",
    "hell":   "地狱难度：复杂嵌套谜局，多重反转环环相扣，大部分线索隐晦，需要极强的逆向思维才能突破。",
    "void":   "无人区难度：极度抽象荒诞，违背常理和直觉，线索若有若无，需要彻底打破思维定势才能触及真相。",
    "auto":   "自适应难度：AI 根据题目本身自动判断归属的难度等级，覆盖各层次。",
}

CHAR_LIMITS = {
    "easy":   {"surface": "10-40字",  "bottom": "30-100字",  "label": "简单版"},
    "medium": {"surface": "30-80字",  "bottom": "80-200字",  "label": "标准版"},
    "hard":   {"surface": "60-150字", "bottom": "150-300字", "label": "进阶版"},
    "hell":   {"surface": "120-250字","bottom": "250-400字", "label": "困难版"},
    "void":   {"surface": "200-300字","bottom": "300-500字", "label": "无人区"},
}

DIRECTION_PROMPTS = {
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

@router.post("/api/admin/ai-generate")
async def admin_ai_generate(req: dict):
    diff = req.get("difficulty", "medium")
    count = req.get("count", 5)
    direction = req.get("direction", "random")
    try:
        client = get_client()
        dir_info = DIRECTION_MAP.get(direction, DIRECTION_MAP["random"])
        dir_prompt = DIRECTION_PROMPTS.get(direction, "")
        diff_constraint = DIFFICULTY_CONSTRAINTS.get(diff, DIFFICULTY_CONSTRAINTS["medium"])
        limits = CHAR_LIMITS.get(diff, CHAR_LIMITS["medium"])
        prompt = f"""你是一个海龟汤谜题生成器。请生成{count}个海龟汤谜题。

难度：{diff}（{limits['label']}，要求：{diff_constraint}）
方向：{dir_info['name']}。{dir_prompt}

每个谜题是一个JSON对象，包含以下字段：
- title: 标题（简短有力）
- surface: 汤面（{limits['label']}，有趣有悬念的谜面，控制在{limits['surface']}）
- bottom: 汤底（{limits['label']}，合理完整的谜底，控制在{limits['bottom']}）
- keywords: 关键词数组（3-5个）
- difficulty: 难度，值为"{diff}"
- direction: 方向，值为"{direction}"

以JSON数组格式返回。示例如下：
[
  {{
    "title": "雨中的空椅子",
    "surface": "一个雨夜，小明看到公园的长椅上放着一把湿透的伞。第二天他听说昨晚有人在那张长椅上坐着等了一夜。小明看了看那把伞，吓得跑掉了。为什么？",
    "bottom": "那把伞是小明自己遗忘的。昨晚他在梦游状态下冒雨去了公园，把伞放在椅子上，然后空手回家。但他完全不记得这件事，所以看到自己的伞出现在别人描述中的地点时，以为遇到了灵异事件。",
    "keywords": ["梦游", "雨伞", "遗忘", "长椅"],
    "difficulty": "{diff}",
    "direction": "{direction}"
  }}
]

仅返回JSON数组，不要markdown包裹，不要额外文字。"""
        resp = client.chat.completions.create(
            model=LLM_MODEL, messages=[{"role":"user","content":prompt}],
            temperature=0.8, max_tokens=8192,
            response_format={"type":"json_object"},
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        soups = json.loads(text)
        if isinstance(soups, dict) and "soups" in soups:
            soups = soups["soups"]
        for i, s in enumerate(soups):
            s["id"] = f"ai-{int(time.time())}-{i}"
            s["difficulty"] = s.get("difficulty", diff)
            s["direction"] = s.get("direction", direction)
    except Exception as e:
        err_msg = str(e)
        print(f"[AI Generate] Error: {err_msg}")
        # 区分错误类型，返回友好提示
        if "401" in err_msg or "403" in err_msg or "Authentication" in err_msg or "Unauthorized" in err_msg or "Incorrect API key" in err_msg or "1010" in err_msg:
            hint = "API Key 无效或未填写，请在 AI 出题页下方配置正确的 API Key"
        elif "404" in err_msg or "Not Found" in err_msg:
            hint = f"模型 '{LLM_MODEL}' 不存在或 API 地址有误，请检查 LLM API 配置"
        elif "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
            hint = "请求超时，请检查网络连接或 API 地址"
        elif "connection" in err_msg.lower() or "refused" in err_msg.lower():
            hint = f"无法连接 API 服务器 ({LLM_BASE_URL})，请检查地址和网络"
        else:
            hint = f"AI 生成失败：{err_msg[:80]}"
        return {"soups": [], "error": hint}
    return {"soups": soups}

@router.get("/api/admin/ai-directions")
async def admin_ai_directions():
    """返回可用方向列表，供前端动态渲染选择器"""
    items = [{"id": k, "name": v["name"], "desc": v["desc"]} for k, v in DIRECTION_MAP.items()]
    return {"directions": items}

@router.post("/api/admin/llm-ping")
async def admin_llm_ping():
    status = ""
    try:
        client = get_client()
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role":"user","content":"仅回复一个词：OK"}],
            max_tokens=100, temperature=0.1,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            text = (resp.choices[0].message.model_extra or {}).get("reasoning_content", "").strip()
        return {"ok": True, "model": LLM_MODEL, "response": text, "msg": f"模型 {LLM_MODEL} 响应正常"}
    except Exception as e:
        return {"ok": False, "model": LLM_MODEL, "error": str(e), "msg": f"连接失败: {str(e)}"}

@router.get("/api/admin/llm-models")
async def admin_llm_models():
    try:
        client = get_client()
        models = client.models.list()
        names = sorted([m.id for m in models])
        return {"ok": True, "models": names}
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e)}

@router.get("/api/admin/qa-ping")
async def admin_qa_ping():
    """测试问答模型连接"""
    try:
        client = get_client()
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role":"user","content":"仅回复一个词：OK"}],
            max_tokens=100, temperature=0.1,
        )
        text = (resp.choices[0].message.content or "").strip()
        return {"ok": True, "model": LLM_MODEL, "response": text,
                "msg": f"✅ 模型 {LLM_MODEL} 响应正常"}
    except Exception as e:
        return {"ok": False, "model": LLM_MODEL, "error": str(e),
                "msg": f"❌ 模型检测失败: {str(e)[:100]}"}

@router.post("/api/admin/ai-approve")
async def admin_ai_approve(req: dict):
    soup = req.get("soup", {})
    if not soup.get("surface") or not soup.get("bottom"):
        return {"ok": False, "msg": "数据不完整"}
    soup["id"] = soup.get("id", f"soup-{len(SOUPS)+1:03d}")
    SOUPS.append(soup)
    return {"ok": True}

# ── 主题管理 ──
@router.get("/api/admin/themes")
async def admin_get_themes():
    return {"themes": theme_manager.list_themes()}

@router.post("/api/admin/theme")
async def admin_set_theme(req: dict):
    tid = req.get("theme_id", "")
    try:
        theme_manager.set_active(tid)
        await manager.broadcast({"type": "theme_change", "theme_id": tid})
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/api/theme")
async def admin_get_current_theme():
    return {"theme_id": theme_manager.get_active()}

# ── 数据面板 ──
@router.get("/api/admin/metrics")
async def admin_metrics():
    dur = int(time.time() - room.start_time) if room.start_time else 0
    return {
        "totalScore": 0,
        "totalDanmaku": len(room.qa_history),
        "totalGifts": len(room.gift_log),
        "paid_users": len(set(g["user"] for g in room.gift_log[-200:])),
        "round_count": room.round_total,
        "session_duration": dur,
        "accuracy": round(room.round_correct / max(room.round_total, 1) * 100) if room.round_total else 0,
        "danmaku_series": [],
        "gift_series": [],
        "recentGifts": [{"user": g["user"], "gift_name": g["giftName"], "coins": GIFT_LIBRARY.get(g["giftName"], {}).get("coins", 0)} for g in room.gift_log[-10:]],
    }

# ── 触发器 API ──
@router.get("/api/triggers")
async def get_triggers():
    if db is None:
        return {"triggers": []}
    return {"triggers": db.get_triggers()}

@router.post("/api/triggers")
async def add_trigger(req: TriggerReq):
    if db is None:
        return {"ok": False, "msg": "持久化未启用"}
    tid = db.add_trigger(req.type, req.target, req.effect, req.value, 1 if req.enabled else 0)
    return {"ok": True, "id": tid}

@router.delete("/api/triggers/{tid}")
async def delete_trigger(tid: int):
    if db is None:
        return {"ok": False, "msg": "持久化未启用"}
    db.del_trigger(tid)
    return {"ok": True}
