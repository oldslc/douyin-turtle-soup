"""
虚拟货币 + 签到路由 — /api/coin/* + /api/signin
"""
import time
from fastapi import APIRouter
from state import db, coins, SIGNIN_REWARD_MAP, DEFAULT_SIGNIN_REWARD

router = APIRouter(tags=["coin"])

# ── 金币余额 ──
@router.get("/api/coin/balance")
async def coin_balance(user: str = "default"):
    return {"balance": coins.get_balance(user), "vip": coins.check_vip(user)}

@router.post("/api/coin/daily")
async def coin_daily(user: str = "default"):
    today = time.strftime("%Y-%m-%d")
    ok = coins.claim_daily(user, today)
    return {"ok": ok, "balance": coins.get_balance(user), "reward": 30 if ok else 0}

@router.post("/api/coin/recharge")
async def coin_recharge(user: str = "default", amount: int = 100):
    coins.add_coins(user, amount)
    return {"ok": True, "balance": coins.get_balance(user), "added": amount}

@router.get("/api/coin/leaderboard")
async def coin_leaderboard():
    return {"leaderboard": coins.get_leaderboard(5)}

@router.get("/api/coin/state")
async def coin_state(user: str = "default"):
    return coins.get_state(user)

# ── 签到 ──
@router.get("/api/signin")
async def signin_status(user: str = "default"):
    if db is None:
        return {"status": "unavailable", "msg": "持久化未启用", "streak": 0, "reward": 0, "today_done": False}
    ck = db.get_checkin(user)
    today = time.strftime("%Y-%m-%d")
    streak = ck.get("streak", 0) if ck else 0
    last_day = ck.get("last_day", "") if ck else ""
    today_done = (last_day == today)
    show_streak = streak + (0 if today_done else 1)
    reward = SIGNIN_REWARD_MAP.get(show_streak if show_streak <= 7 else 7, DEFAULT_SIGNIN_REWARD)
    return {
        "status": "ok" if not today_done else "repeat",
        "streak": streak,
        "total_days": (ck.get("total_days", 0) if ck else 0),
        "today_done": today_done,
        "reward": reward,
        "reward_map": SIGNIN_REWARD_MAP,
    }

@router.post("/api/signin")
async def do_signin(user: str = "default"):
    if db is None:
        return {"status": "unavailable", "msg": "持久化未启用"}
    today = time.strftime("%Y-%m-%d")
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    ck = db.get_checkin(user)
    if ck and ck.get("last_day") == today:
        return {"status": "repeat", "msg": "今天已签到", "streak": ck.get("streak", 0),
                "reward": 0, "balance": coins.get_balance(user)}
    if ck and ck.get("last_day") == yesterday:
        new_streak = (ck.get("streak", 0) or 0) + 1
    else:
        new_streak = 1
    reward = SIGNIN_REWARD_MAP.get(new_streak if new_streak <= 7 else 7, DEFAULT_SIGNIN_REWARD)
    db.upsert_checkin({
        "name": user, "last_day": today, "streak": new_streak,
        "total_days": ((ck.get("total_days", 0) if ck else 0) + 1),
    })
    coins.add_coins(user, reward)
    return {"status": "ok", "reward": reward, "streak": new_streak,
            "balance": coins.get_balance(user)}
