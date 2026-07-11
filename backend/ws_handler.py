"""
WebSocket 处理器 — 连接管理 + 消息路由 + 弹幕处理
"""
import json
import time

from fastapi import WebSocket, WebSocketDisconnect
from state import (
    room, manager, spam_filter,
    SCORE_BY_DIFFICULTY,
    RevealEngine,
    llm_classify, add_score,
    handle_gift,
)


async def handle_danmaku(msg: dict):
    text = msg.get("text","").strip()
    user = msg.get("nickname","观众")
    if not text or not room.soup_answer:
        return
    passed, reason = spam_filter.check_danmaku(text, user)
    if not passed:
        return
    any_revealed = False
    for ch in text:
        if ch in room.soup_answer and RevealEngine.is_content_word(ch):
            if any(s["char"]==ch and not s["revealed"] for s in room.char_states):
                room.char_states = RevealEngine.reveal_char(room.char_states, ch)
                any_revealed = True
    if any_revealed:
        room.anti_last_reveal = time.time()
        room.anti_since_reveal = 0
        room.anti_triggers = 0
        await manager.broadcast({"type":"reveal_update","charStates":room.char_states})
    else:
        room.anti_since_reveal += 1
    result = await llm_classify(text, room.soup_answer, room.soup_keywords)
    room.guess_count += 1
    room.qa_history.append({"user":user,"question":text,"result":result,"timestamp":time.time()})
    room.round_total += 1
    if result in ("是", "是也不是"):
        room.round_correct += 1
        room.round_correct_times.append(time.time() - room.start_time)
    await manager.broadcast({"type":"classification","text":text,"user":user,"answerType":result,"layer":"llm"})
    if result in ("是", "是也不是"):
        base = SCORE_BY_DIFFICULTY.get(room.current_difficulty, 15)
        delta = base if result == "是" else base // 2
        await add_score(user, delta)
    _, total, pct = RevealEngine.get_progress(room.char_states)
    if pct >= 100:
        room.phase = "complete"
        await manager.broadcast({"type":"game_end","winner":user,"charStates":room.char_states})


async def websocket_handler(ws: WebSocket):
    """WebSocket 连接主处理循环。"""
    cid = f"client_{len(manager.active)}_{int(time.time())}"
    await manager.connect(ws, cid)
    await ws.send_json({"type": "state_sync", "room": room.to_dict()})
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            t = msg.get("type", "")
            if t == "danmaku":
                await handle_danmaku(msg)
            elif t == "gift":
                await handle_gift(msg)
            elif t == "start_round":
                from routers.game import game_start
                await game_start(msg.get("difficulty", "medium"))
            elif t == "buy_gift":
                from routers.gift import buy_gift, BuyGiftReq
                await buy_gift(BuyGiftReq(gift_type=msg.get("gift_type",""), user=msg.get("user","default")))
            elif t == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(cid)
