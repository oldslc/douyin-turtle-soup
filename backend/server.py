"""
CCcat 海龟汤 — 合并版服务（单进程）
整合 LLM 分类 + WebSocket 游戏 + 弹幕中继 + 嵌入式前端
"""
import asyncio
import time
import subprocess
import webbrowser
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import uvicorn
from admin import ADMIN_HTML
from overlay import OVERLAY_HTML
from state import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, SERVER_PORT,
    FRONTEND_DIR, FRONTEND_DIST,
    ANTI_STALL_ENABLED, ANTI_STALL_INTERVAL, ANTI_STALL_DANMAKU,
    ANTI_STALL_DECAY, AUTO_START_DELAY,
    MOCK_LEADERBOARD,
    room, manager, db, spam_filter, theme_manager,
    get_client, recreate_client,
    llm_classify, llm_hint, llm_gift_solicit,
    auto_reveal_and_hint,
)
from ws_handler import websocket_handler, handle_danmaku

# ── Request Models（仅供本文件内路由使用） ──
class ClassifyReq(BaseModel):
    text: str; answer: str; keywords: list[str]
class HintReq(BaseModel):
    qaHistory: list[dict] = []; answer: str = ""; keywords: list[str] = []
class GiftSolicitReq(BaseModel):
    giftType: str = ""; context: dict = {}
class ConfigReq(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""
class PushDanmakuReq(BaseModel):
    user: str; content: str

# ── 后台任务引用 ──
_anti_stall_task = None
_timer_task = None
frontend_process = None

async def timer_tick_loop():
    while True:
        await asyncio.sleep(1)
        try:
            if room.phase == "complete" and not room._auto_start_pending:
                room._auto_start_pending = True
                asyncio.create_task(auto_start_after_delay())
            if not room.soup_answer or room.phase in ("idle", "complete", "lobby"):
                continue
            elapsed = time.time() - room.start_time
            remaining = max(0, room.round_timeout - int(elapsed))
            room.remaining = remaining
            await manager.broadcast({"type": "timer", "remaining": remaining, "elapsed": int(elapsed)})
            if remaining <= 0:
                await manager.broadcast({"type": "timer", "remaining": 0, "elapsed": int(elapsed)})
                for s in room.char_states:
                    if s["isContent"] and not s["revealed"]:
                        s["revealed"] = True
                room.phase = "complete"
                await manager.broadcast({"type": "reveal_update", "charStates": room.char_states, "auto": True})
                await manager.broadcast({"type": "game_end", "winner": "系统", "charStates": room.char_states})
        except Exception as e:
            print(f"[Timer] Error: {e}")

async def auto_start_after_delay():
    await asyncio.sleep(AUTO_START_DELAY)
    try:
        if room.phase == "complete":
            print("[AutoStart] 自动开始下一局")
            from routers.game import game_start
            await game_start("auto")
    except Exception as e:
        print(f"[AutoStart] Error: {e}")
    finally:
        room._auto_start_pending = False

async def anti_stall_loop():
    while True:
        await asyncio.sleep(30)
        try:
            if not room.soup_answer or room.phase in ("idle", "complete", "lobby"):
                continue
            if not ANTI_STALL_ENABLED:
                continue
            now = time.time()
            decay = ANTI_STALL_DECAY ** room.anti_triggers
            time_cond = (now - room.anti_last_reveal) >= (ANTI_STALL_INTERVAL * decay)
            danmaku_cond = room.anti_since_reveal >= (ANTI_STALL_DANMAKU * decay)
            if time_cond or danmaku_cond:
                await auto_reveal_and_hint("anti_stall")
        except Exception as e:
            print(f"[AntiStall] Error: {e}")
            await asyncio.sleep(30)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global frontend_process, _anti_stall_task, _timer_task
    if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
        print(f"[Server] 静态文件就绪: {FRONTEND_DIST}")
    elif FRONTEND_DIR.exists() and (FRONTEND_DIR / "package.json").exists():
        try:
            print(f"[Server] 尝试启动前端开发服务器...")
            if not (FRONTEND_DIR / "node_modules").exists():
                subprocess.run(["npm","install"], cwd=str(FRONTEND_DIR), shell=True, capture_output=True)
            frontend_process = subprocess.Popen(
                ["npm","run","dev"], cwd=str(FRONTEND_DIR), shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"[Server] 前端启动失败: {e}")
    print(f"[Server] 嵌入式前端可用: http://localhost:{SERVER_PORT}")
    # ── 授权状态检查 ──
    try:
        from routers.license import LIC_AVAILABLE, LICENSE_KEY
        import license as _lic
        if LIC_AVAILABLE and LICENSE_KEY:
            info = _lic.parse_license(LICENSE_KEY)
            if info:
                if info.get("is_permanent"):
                    print(f"[License] 永久授权")
                else:
                    print(f"[License] 授权码剩余 {info.get('remaining_days', 0)} 天")
            else:
                print(f"[License] 环境变量 LICENSE_KEY 格式无效")
        elif LIC_AVAILABLE:
            saved = _lic.load_saved_license()
            if saved and not saved.get("expired"):
                print(f"[License] 本地授权")
            else:
                trial = _lic.get_trial_status()
                if trial.get("is_expired"):
                    print(f"[License] 试用已过期")
                elif trial.get("used"):
                    print(f"[License] 试用剩余 {_lic.format_remaining(trial.get('remaining_seconds', 0))}")
                else:
                    print(f"[License] 试用未开始（已启用）")
    except Exception as e:
        print(f"[License] 检查失败: {e}")
    try:
        webbrowser.open(f"http://localhost:{SERVER_PORT}")
    except Exception:
        pass
    _anti_stall_task = asyncio.create_task(anti_stall_loop())
    print("[Server] 防卡死机制已启动")
    _timer_task = asyncio.create_task(timer_tick_loop())
    print("[Server] 倒计时已启动")
    yield
    if _anti_stall_task and not _anti_stall_task.done():
        _anti_stall_task.cancel()
    if _timer_task and not _timer_task.done():
        _timer_task.cancel()
    if frontend_process:
        frontend_process.kill()

app = FastAPI(title="CCcat 海龟汤", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── 注册路由模块 ──
from routers.admin import router as admin_router
from routers.game import router as game_router
from routers.tts import router as tts_router
from routers.gift import router as gift_router
from routers.coin import router as coin_router
from routers.license import router as license_router
app.include_router(admin_router)
app.include_router(game_router)
app.include_router(tts_router)
app.include_router(gift_router)
app.include_router(coin_router)
app.include_router(license_router)

# ── 本地路由 ──

@app.get("/health")
async def health():
    return {"status": "ok", "model": LLM_MODEL, "api_base": LLM_BASE_URL, "phase": room.phase, "connections": len(manager.active)}

@app.post("/classify")
async def classify(req: ClassifyReq):
    t0 = time.time()
    passed, reason = spam_filter.check_danmaku(req.text, "__api__")
    if not passed:
        return {"text": req.text, "answerType": "不是", "layer": reason, "latencyMs": (time.time()-t0)*1000}
    result = await llm_classify(req.text, req.answer, req.keywords)
    return {"text": req.text, "answerType": result, "layer": "llm", "latencyMs": (time.time()-t0)*1000}

@app.post("/hint")
async def hint(req: HintReq):
    hint_text = await llm_hint(req.qaHistory, req.answer, req.keywords)
    return {"hint": hint_text, "layer": "llm"}

@app.post("/gift-solicit")
async def gift_solicit(req: GiftSolicitReq):
    return {"script": await llm_gift_solicit(req.giftType, req.context), "giftType": req.giftType}

@app.get("/api/config")
async def get_config():
    return {"api_key_configured": bool(LLM_API_KEY), "base_url": LLM_BASE_URL, "model": LLM_MODEL}

@app.post("/api/config")
async def update_config(req: ConfigReq):
    global LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
    changed = False
    if req.api_key:
        LLM_API_KEY = req.api_key; changed = True
    if req.base_url:
        LLM_BASE_URL = req.base_url; changed = True
    if req.model:
        LLM_MODEL = req.model; changed = True
    if changed:
        recreate_client()
    return {"ok": True, "model": LLM_MODEL, "base_url": LLM_BASE_URL}

@app.post("/api/barrage/push")
async def push_barrage(req: PushDanmakuReq):
    await manager.broadcast({"type": "danmu", "data": {"user": req.user, "content": req.content}})
    return {"ok": True}

# ── 排行榜 ──
@app.get("/api/leaderboard")
async def leaderboard(limit: int = 10):
    if db is None:
        return {"leaderboard": [], "source": "memory"}
    users = db.get_top_users(limit)
    from tiers import get_tier
    mock_list = [
        {"name": u["name"], "score": u["score"],
         "tier": get_tier(u["score"]),
         "combo": 0, "total_gifts": 0}
        for u in MOCK_LEADERBOARD
    ]
    real_list = [
        {"name": u["name"], "score": u.get("score", 0),
         "tier": get_tier(u.get("score", 0)),
         "combo": u.get("combo", 0),
         "total_gifts": u.get("total_gifts", 0)}
        for u in users
    ]
    merged = sorted(real_list + mock_list, key=lambda x: x["score"], reverse=True)[:limit]
    return {"leaderboard": merged, "source": "mixed" if real_list else "mock"}

# ── 页面路由 ──
@app.get("/admin")
async def admin_page():
    return HTMLResponse(content=ADMIN_HTML)

@app.get("/overlay")
async def overlay_page():
    active = theme_manager.get_active()
    html = theme_manager.apply_to_html(OVERLAY_HTML, active)
    return HTMLResponse(content=html)

# ── WebSocket ──
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await websocket_handler(ws)

# ── 前端路由 ──
_dist_index = FRONTEND_DIST / "index.html"
if _dist_index.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
    print(f"[Server] 静态文件服务: {FRONTEND_DIST}")
else:
    @app.get("/")
    async def serve_root():
        return RedirectResponse(url="/admin")
    print(f"[Server] 嵌入式前端就绪")

# ── 入口 ──
if __name__ == "__main__":
    print("=" * 50)
    print(f"  CCcat 海龟汤 - V7 (三端分离)")
    print(f"  LLM: {LLM_MODEL} @ {LLM_BASE_URL}")
    print(f"  [Admin] http://localhost:{SERVER_PORT}/admin")
    print(f"  [Overlay] http://localhost:{SERVER_PORT}/overlay")
    print(f"  [WS]  ws://localhost:{SERVER_PORT}/ws")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
