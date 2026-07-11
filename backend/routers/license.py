"""
授权 API 路由 — /api/license/*

服务端授权校验，与 standalone/license.py 共享验证逻辑。
启动时读取 .env 中的 LICENSE_KEY，暴露查询和激活端点。
"""
import os
import sys
import time
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

# 将 standalone/ 目录加入 Python 路径以导入 license 核心模块
_STANDALONE_DIR = Path(__file__).resolve().parent.parent / "standalone"
if str(_STANDALONE_DIR) not in sys.path:
    sys.path.insert(0, str(_STANDALONE_DIR))

# 尝试从环境变量读取授权配置
LICENSE_KEY = os.environ.get("LICENSE_KEY", "")
LICENSE_MODE = os.environ.get("LICENSE_MODE", "trial")

# 动态导入 license 核心模块（开发环境用 .py，生产环境用 .pyd）
try:
    import license as _lic
    LIC_AVAILABLE = True
except ImportError:
    _lic = None
    LIC_AVAILABLE = False

router = APIRouter(tags=["license"])


class ActivateReq(BaseModel):
    key: str


def _auth_format(status_response: dict) -> dict:
    """将 license status 响应转为 admin.js 期望的 auth 格式（含 ok/machine_id/reason 等字段）。"""
    status = status_response.get("status", "")
    mid = _lic.get_machine_id() if LIC_AVAILABLE else ""
    if status == "active":
        return {
            "ok": True, "is_permanent": status_response.get("is_permanent", False),
            "remaining_days": status_response.get("remaining_days", 0),
            "source": status_response.get("source", ""), "machine_id": mid,
            "trial_available": True,
        }
    if status == "trial":
        return {
            "ok": True, "source": "trial",
            "remaining_seconds": status_response.get("remaining_seconds", 0),
            "machine_id": mid, "trial_available": True,
        }
    reason_map = {"trial_expired": "trial_expired", "expired": "license_expired",
                  "inactive": "inactive", "unavailable": "unavailable"}
    return {
        "ok": False, "reason": reason_map.get(status, "unknown"),
        "machine_id": mid, "trial_available": status in ("trial_available", "inactive", "unavailable"),
    }


@router.get("/api/auth/status")
async def auth_status():
    result = await license_status()
    return _auth_format(result)


@router.get("/api/auth/start-trial")
async def auth_start_trial():
    return await trial_start()


@router.post("/api/auth/activate")
async def auth_activate(req: ActivateReq):
    return await license_activate(req)


@router.get("/api/license/status")
async def license_status():
    """返回当前授权状态（服务端视角）"""
    if not LIC_AVAILABLE:
        return {
            "mode": LICENSE_MODE,
            "key_configured": bool(LICENSE_KEY),
            "status": "unavailable",
            "msg": "授权模块未加载（独立部署模式）",
        }

    # 尝试用环境变量中的 LICENSE_KEY 验证
    if LICENSE_KEY:
        info = _lic.parse_license(LICENSE_KEY)
        if info:
            return {
                "mode": LICENSE_MODE,
                "status": "active",
                "source": "env",
                "type": info["type"],
                "is_permanent": info.get("is_permanent", False),
                "is_expired": info.get("is_expired", False),
                "remaining_days": info.get("remaining_days", 0),
            }

    # 检查本地授权文件（与 standalone 共享）
    try:
        saved = _lic.load_saved_license()
        if saved:
            if saved.get("expired"):
                return {"status": "expired", "source": "local", "msg": "授权已过期"}
            return {
                "status": "active",
                "source": "local",
                "type": saved.get("license_type", "unknown"),
                "is_permanent": saved.get("is_permanent", False),
                "remaining_days": -1 if saved.get("is_permanent") else max(
                    0, (saved.get("expires_at", 0) - int(time.time())) // 86400
                ),
            }
    except Exception:
        pass

    # 检查试用状态
    try:
        trial = _lic.get_trial_status()
        if trial.get("available"):
            return {"status": "trial_available", "mode": LICENSE_MODE}
        if trial.get("is_expired"):
            return {"status": "trial_expired", "mode": LICENSE_MODE}
        return {
            "status": "trial",
            "mode": LICENSE_MODE,
            "remaining_seconds": trial.get("remaining_seconds", 0),
        }
    except Exception:
        pass

    return {"status": "inactive", "mode": LICENSE_MODE}


@router.post("/api/license/activate")
async def license_activate(req: ActivateReq):
    """激活授权码（服务器端，含机器码校验）"""
    if not LIC_AVAILABLE:
        return {"ok": False, "error": "授权模块未加载"}

    machine_code = _lic.get_machine_code()
    info = _lic.parse_license(req.key, machine_code=machine_code)
    if info is None:
        return {"ok": False, "error": "授权码无效或不匹配本机"}
    if info.get("is_expired"):
        return {"ok": False, "error": "授权码已过期"}

    # 持久化到本地授权文件（与 standalone EXE 共享存储）
    _lic.save_license(req.key, info)
    return {"ok": True, **info}


@router.get("/api/license/trial/start")
async def trial_start():
    """开始免费试用（已有有效试用不会重置）"""
    if not LIC_AVAILABLE:
        return {"ok": False, "error": "授权模块未加载"}

    # 检查是否有正在进行的试用，防止重复重置
    current = _lic.get_trial_status()
    if current.get("used"):
        if current.get("is_expired"):
            return {"ok": False, "error": "免费试用已过期"}
        return {"ok": True, "remaining_seconds": current.get("remaining_seconds", 0)}

    status = _lic.start_trial()
    return {"ok": True, "remaining_seconds": status.get("remaining_seconds", 0)}
