"""
TTS 路由 — /api/tts/*
"""
import re
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from state import (
    db, tts_engine,
    _cosyvoice_deploy_lock, _cosyvoice_deploy_progress,
    _check_gpu_info_async as _check_gpu, _run_cosyvoice_deploy,
)
import uuid
from pathlib import Path

router = APIRouter(tags=["tts"])

class TTSReq(BaseModel):
    text: str
    rate: float | None = None

class TTSConfigReq(BaseModel):
    engine: str | None = None
    voice: str | None = None
    rate: float | None = None
    cosyvoice_spk: str | None = None

@router.post("/api/tts/synthesize")
async def tts_synthesize(req: TTSReq):
    engine = "edge"
    voice = None
    rate = req.rate
    spk_id = None
    if db is not None:
        engine = db.get_setting("tts_engine", "edge")
        voice = db.get_setting("tts_voice", None)
        spk_id = db.get_setting("cosyvoice_spk", None)
        if rate is None:
            rate_default = db.get_setting("tts_rate", None)
            if rate_default is not None:
                rate = float(rate_default)
    sr, audio_bytes = await tts_engine.async_generate_speech(req.text, engine=engine, voice=voice, rate=rate, spk_id=spk_id)
    if audio_bytes is None:
        return JSONResponse({"error": f"TTS engine '{engine}' not available"}, status_code=503)
    content_type = "audio/mpeg" if engine == "edge" else "audio/wav"
    headers = {"X-Sample-Rate": str(sr), "X-TTS-Engine": engine}
    if rate is not None:
        headers["X-TTS-Rate"] = str(rate)
    return Response(content=audio_bytes, media_type=content_type, headers=headers)

@router.get("/api/tts/status")
async def tts_status():
    engines = tts_engine.list_engines()
    engine = "edge"
    if db is not None:
        engine = db.get_setting("tts_engine", "edge")
    return {"available": engines.get(engine, {}).get("available", False), "engines": engines, "active": engine}

@router.get("/api/tts/config")
async def tts_get_config():
    engine = "edge"
    voice = None
    rate = 1.0
    if db is not None:
        engine = db.get_setting("tts_engine", "edge")
        voice = db.get_setting("tts_voice", "zh-CN-XiaoxiaoNeural")
        r = db.get_setting("tts_rate", None)
        if r is not None:
            rate = float(r)
    engines = tts_engine.list_engines()
    edge_voices = tts_engine.list_edge_voices()
    current_spk = tts_engine.DEFAULT_SPK_ID
    if db is not None:
        s = db.get_setting("cosyvoice_spk", None)
        if s:
            current_spk = s
    return {
        "engine": engine, "voice": voice, "rate": rate,
        "voices": edge_voices, "engines": engines,
        "cosyvoice_spk": current_spk,
        "cosyvoice_speakers": tts_engine.list_cosyvoice_speakers(),
    }

@router.post("/api/tts/config")
async def tts_set_config(req: TTSConfigReq):
    if req.engine is not None:
        if req.engine not in tts_engine.ENGINES:
            return JSONResponse({"error": f"Unknown engine: {req.engine}"}, status_code=400)
        if db is not None:
            db.set_setting("tts_engine", req.engine)
    if req.voice is not None:
        if db is not None:
            db.set_setting("tts_voice", req.voice)
    if req.rate is not None:
        if db is not None:
            db.set_setting("tts_rate", str(req.rate))
    if req.cosyvoice_spk is not None:
        if db is not None:
            db.set_setting("cosyvoice_spk", req.cosyvoice_spk)
    return {"ok": True, "engine": req.engine, "voice": req.voice, "rate": req.rate}

# ── CosyVoice3 部署 ──
@router.get("/api/tts/cosyvoice-deploy")
async def tts_cosyvoice_deploy_status():
    status = tts_engine.cosyvoice_status()
    gpu_info = await _check_gpu(force=False)
    return {
        "status": status["status"],
        "detail": status["detail"],
        "gpu": gpu_info,
        "deploying": _cosyvoice_deploy_lock.locked(),
        "progress": _cosyvoice_deploy_progress,
    }

@router.post("/api/tts/cosyvoice-deploy")
async def tts_cosyvoice_deploy_start():
    import sys
    if getattr(sys, "frozen", False):
        return {"ok": False, "error": "打包环境下无法自动部署，请下载 CosyVoice3 后手动放置"}
    if _cosyvoice_deploy_lock.locked():
        return {"ok": False, "error": "已有部署任务在进行中"}
    import asyncio
    _cosyvoice_deploy_progress.update({"step": "starting", "pct": 0, "text": "准备部署..."})
    asyncio.create_task(_run_cosyvoice_deploy())
    return {"ok": True, "message": "部署已启动"}

@router.post("/api/tts/cosyvoice-speaker")
async def tts_cosyvoice_add_speaker(file: UploadFile = File(...), name: str = Form("")):
    if file.content_type not in ("audio/wav", "audio/x-wav"):
        return JSONResponse({"ok": False, "error": "仅支持 WAV 文件"}, status_code=400)
    asset_dir = tts_engine.COSYVOICE_DIR / "asset"
    asset_dir.mkdir(parents=True, exist_ok=True)
    # 优先级：用户命名 > 文件名 > 随机 ID
    spk_id = name.strip()
    if not spk_id and file.filename:
        spk_id = re.sub(r'[^\w一-鿿\-]', '', Path(file.filename).stem)
    if not spk_id:
        spk_id = f"upload_{uuid.uuid4().hex[:8]}"
    fname = f"zero_shot_prompt_{spk_id}.wav"
    dest = asset_dir / fname
    content = await file.read()
    dest.write_bytes(content)
    ok = tts_engine.register_cosyvoice_speaker(spk_id, str(dest))
    if ok:
        return {"ok": True, "spk_id": spk_id, "name": spk_id}
    dest.unlink(missing_ok=True)
    return JSONResponse({"ok": False, "error": "说话人注册失败"}, status_code=500)

@router.post("/api/tts/cosyvoice-uninstall")
async def tts_cosyvoice_uninstall():
    if _cosyvoice_deploy_lock.locked():
        return {"ok": False, "error": "部署进行中，请等待完成后再卸载"}
    cv_dir = tts_engine.COSYVOICE_DIR
    if cv_dir.exists():
        # 用 _safe_rmtree 先删 .git 避免 Windows 文件锁
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        try:
            from state import _safe_rmtree
            _safe_rmtree(cv_dir)
        except Exception as e:
            return {"ok": False, "error": f"删除目录失败: {e}"}
    if db is not None:
        db.set_setting("tts_engine", "edge")
    tts_engine.reset_cosyvoice()
    return {"ok": True, "message": "已卸载"}
