"""
礼物与别名路由 — /api/gift/* + /api/gift/aliases
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from state import (
    db, coins, room, manager, GIFT_PRICES, GIFT_NAME_MAP, GIFT_LIBRARY,
    slot_manager, handle_gift,
)

router = APIRouter(tags=["gift"])

@router.get("/api/gift/shop")
async def gift_shop():
    return {"gifts": [{"type": k, "name": GIFT_NAME_MAP.get(k, k), "price": v} for k, v in GIFT_PRICES.items()]}

# ── 礼物别名 ──
class AliasReq(BaseModel):
    alias: str
    gifts: str = ""
    effect: str = ""
    enabled: int = 1

@router.get("/api/gift/aliases")
async def get_aliases():
    if db is None:
        return {"aliases": []}
    return {"aliases": db.get_aliases()}

@router.post("/api/gift/aliases")
async def add_alias(req: AliasReq):
    if db is None:
        return {"ok": False, "msg": "持久化未启用"}
    db.upsert_alias(req.alias, req.gifts, req.effect, 1 if req.enabled else 0)
    return {"ok": True, "alias": req.alias}

@router.put("/api/gift/aliases/{alias}")
async def update_alias(alias: str, req: AliasReq):
    if db is None:
        return {"ok": False, "msg": "持久化未启用"}
    db.upsert_alias(alias, req.gifts, req.effect, 1 if req.enabled else 0)
    return {"ok": True, "alias": alias}

@router.delete("/api/gift/aliases/{alias}")
async def delete_alias(alias: str):
    if db is None:
        return {"ok": False, "msg": "持久化未启用"}
    db.del_alias(alias)
    return {"ok": True}

# ── 礼物购买 ──
class BuyGiftReq(BaseModel):
    gift_type: str
    user: str = "default"

@router.post("/api/gift/buy")
async def buy_gift(req: BuyGiftReq):
    price = GIFT_PRICES.get(req.gift_type, 0)
    if price == 0:
        return {"ok": False, "msg": "该礼物无需购买"}
    if not coins.spend(req.user, price):
        return {"ok": False, "msg": "金币不足", "balance": coins.get_balance(req.user)}
    await handle_gift({"nickname": req.user, "giftName": req.gift_type, "count": 1})
    return {"ok": True, "balance": coins.get_balance(req.user), "gift_type": req.gift_type}
