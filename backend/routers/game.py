"""
游戏路由 — /api/game/* + 自适应难度
"""
from fastapi import APIRouter
from pydantic import BaseModel
from state import (
    room, manager, SOUPS, ROUND_TIMEOUT, DIFFICULTY_MULTIPLIER,
    DIFFICULTY_NAME_MAP, RevealEngine, compute_adaptive_difficulty,
)
import random as rnd
import time

router = APIRouter(tags=["game"])

@router.get("/api/game/state")
async def game_state():
    return room.to_dict()

@router.post("/api/game/start")
async def game_start(difficulty: str = "medium"):
    if room.next_difficulty:
        difficulty = room.next_difficulty
        room.next_difficulty = ""
    if difficulty == "auto":
        difficulty = compute_adaptive_difficulty()
    diff = difficulty if difficulty in DIFFICULTY_MULTIPLIER else "medium"
    candidates = [s for s in SOUPS if s.get("difficulty") == diff]
    if not candidates:
        candidates = [s for s in SOUPS if s.get("difficulty") == "medium"] or SOUPS
    soup = rnd.choice(candidates)
    room.reset()
    room.soup_text = soup["surface"]
    room.soup_answer = soup["bottom"]
    room.soup_keywords = soup["keywords"]
    room.current_difficulty = diff
    room.current_soup_id = soup.get("id", "")
    room.char_states = RevealEngine.init_char_states(room.soup_answer)
    room.phase = "reading"
    room.start_time = time.time()
    room.anti_last_reveal = room.start_time
    room.remaining = room.round_timeout
    await manager.broadcast({
        "type": "game_start", "surface": room.soup_text,
        "keywords": room.soup_keywords, "charStates": room.char_states,
        "difficulty": diff, "difficulty_name": DIFFICULTY_NAME_MAP.get(diff, diff),
        "remaining": room.remaining,
        "roundTimeout": room.round_timeout,
    })
    return {"ok": True, "surface": room.soup_text, "difficulty": diff}

@router.get("/api/game/difficulties")
async def game_difficulties():
    return {"difficulties": [
        {"id": k, "name": k, "multiplier": v} for k, v in DIFFICULTY_MULTIPLIER.items()
    ]}

@router.get("/api/adaptive/difficulty")
async def get_adaptive_difficulty():
    return {
        "current": room.current_difficulty,
        "suggested": compute_adaptive_difficulty(),
        "correct_rate": round(room.round_correct / max(room.round_total, 1), 3) if room.round_total >= 5 else None,
        "rounds_tracked": room.round_total,
    }
