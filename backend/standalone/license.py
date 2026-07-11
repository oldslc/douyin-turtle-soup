"""
授权核心模块 — License 生成/验证 + 5h 试用跟踪 + Ed25519 机器码绑定

旧格式 (HMAC):   LIC-{type}-{timestamp}-{hmac_hex[:12]}
新格式 (Ed25519): LIC-{type}-{timestamp}-{mid[:12]}-{sig_base64}

类型:
  7d   = 7 天
  1m   = 30 天
  1y   = 365 天
  perm = 永久

试用: 5 小时墙钟时间（从首次启动算起）
存储: %%APPDATA%%/haiyutang/ （混淆 JSON）
"""

import base64
import hashlib
import hmac
import json
import os
import subprocess
import time
from pathlib import Path

# ── Ed25519 公钥（由 keygen.py gen-keys 生成后手动填入） ──
# 格式: 32 字节 raw 公钥的十六进制字符串
PUBLIC_KEY_HEX = "dfe9bedaf405b1b8aec503912f88249b47032aa81f5b2ace079808d3dba83a3a"

_OBFUSCATION_KEY = b"hyt-obfuscate-key-2026"

# 旧 HMAC 密钥（仅用于旧格式兼容，新格式使用 Ed25519）
_LICENSE_SECRET = b"haiyutang-license-s3cr3t-2026-v2"

LICENSE_DURATIONS = {
    "7d": 7 * 24 * 3600,
    "1m": 30 * 24 * 3600,
    "1y": 365 * 24 * 3600,
    "perm": -1,
}

TRIAL_SECONDS = 5 * 3600

_APP_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "haiyutang"
_LICENSE_FILE = _APP_DIR / "license.dat"
_TRIAL_FILE = _APP_DIR / "trial.dat"

# ── Ed25519 可选导入（Cython 兼容） ──
try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    _HAVE_ED25519 = True
except ImportError:
    _HAVE_ED25519 = False


# ═══════════════════════════════════════════
# 机器码
# ═══════════════════════════════════════════

def get_machine_code() -> str:
    """采集本机硬件指纹，返回 SHA256 哈希。

    组合来源：主板 UUID + CPU 序列号 + 硬盘序列号。
    任一来源采集失败不影响整体（用空字符串代替）。
    """
    parts = []

    for cmd in [
        ["wmic", "csproduct", "get", "uuid"],
        ["wmic", "cpu", "get", "processorid"],
        ["wmic", "diskdrive", "get", "serialnumber"],
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            lines = [l.strip() for l in r.stdout.split("\n") if l.strip()]
            if len(lines) >= 2:
                parts.append(lines[1])
        except Exception:
            pass

    raw = "|".join(parts) if parts else os.environ.get("COMPUTERNAME", "UNKNOWN")
    return hashlib.sha256(raw.encode()).hexdigest()


def get_machine_id() -> str:
    """短机器标识（前 12 位 hex，用于授权码展示和 UI）"""
    return get_machine_code()[:12]


# ═══════════════════════════════════════════
# 加密存储工具
# ═══════════════════════════════════════════

def _xor_obfuscate(data: bytes, key: bytes = _OBFUSCATION_KEY) -> bytes:
    return bytes(d ^ key[i % len(key)] for i, d in enumerate(data))


def _write_obfuscated(path: Path, obj: dict):
    _APP_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj, separators=(",", ":")).encode()
    obscured = _xor_obfuscate(raw)
    b64 = base64.urlsafe_b64encode(obscured)
    path.write_bytes(b64)


def _read_obfuscated(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        b64 = path.read_bytes()
        obscured = base64.urlsafe_b64decode(b64)
        raw = _xor_obfuscate(obscured)
        return json.loads(raw)
    except Exception:
        return None


# ═══════════════════════════════════════════
# Ed25519 验证
# ═══════════════════════════════════════════

def _ed25519_verify(signature: bytes, message: bytes) -> bool:
    if not _HAVE_ED25519 or not PUBLIC_KEY_HEX:
        return False
    try:
        pub_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))
        pub_key.verify(signature, message)
        return True
    except InvalidSignature:
        return False


# ═══════════════════════════════════════════
# 授权码生成 / 验证
# ═══════════════════════════════════════════

def generate_license(license_type: str, custom_time: int | None = None) -> str:
    """生成旧 HMAC 格式授权码（测试/调试用）"""
    assert license_type in LICENSE_DURATIONS, f"未知类型: {license_type}"
    ts = str(custom_time or int(time.time()))
    payload = f"{license_type}:{ts}"
    sig = hmac.new(_LICENSE_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:12]
    return f"LIC-{license_type}-{ts}-{sig}"


def parse_license(key: str, machine_code: str | None = None) -> dict | None:
    """解析授权码，支持新旧两种格式。

    新格式 (5 段): LIC-{type}-{ts}-{mid}-{sig_b64}，Ed25519 签名。
    旧格式 (4 段): LIC-{type}-{ts}-{sig}，HMAC 签名。

    如果提供 machine_code，新格式会额外验证机器码匹配。
    返回 {type, activated_at, expires_at, is_permanent, ...} 或 None。
    """
    try:
        parts = key.strip().split("-")
        if len(parts) not in (4, 5) or parts[0] != "LIC":
            return None
        lic_type = parts[1]
        ts_str = parts[2]

        if lic_type not in LICENSE_DURATIONS:
            return None

        activated_at = int(ts_str)
        duration = LICENSE_DURATIONS[lic_type]
        is_permanent = duration == -1
        expires_at = -1 if is_permanent else activated_at + duration
        now = int(time.time())

        if len(parts) == 5:
            # ── 新格式：Ed25519 签名 + 机器码绑定 ──
            mid_expected = parts[3]
            sig_b64 = parts[4]
            payload = f"{lic_type}-{ts_str}-{mid_expected}"

            # 验证 Ed25519 签名（补 base64 padding）
            try:
                pad = 4 - len(sig_b64) % 4
                if pad < 4:
                    sig_b64 += "=" * pad
                signature = base64.b64decode(sig_b64)
            except Exception:
                return None

            if not _ed25519_verify(signature, payload.encode()):
                return None

            # 验证机器码
            if machine_code:
                actual_mid = machine_code[:12]
                if mid_expected != actual_mid:
                    return None  # 机器码不匹配

            return {
                "type": lic_type,
                "activated_at": activated_at,
                "expires_at": expires_at,
                "is_permanent": is_permanent,
                "is_expired": False if is_permanent else (now > expires_at),
                "remaining_days": -1 if is_permanent else max(0, (expires_at - now) // 86400),
                "machine_id": mid_expected,
            }
        else:
            # ── 旧格式：HMAC 签名 ──
            sig = parts[3]
            payload = f"{lic_type}:{ts_str}"
            expected = hmac.new(_LICENSE_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:12]
            if sig != expected:
                return None

            return {
                "type": lic_type,
                "activated_at": activated_at,
                "expires_at": expires_at,
                "is_permanent": is_permanent,
                "is_expired": False if is_permanent else (now > expires_at),
                "remaining_days": -1 if is_permanent else max(0, (expires_at - now) // 86400),
            }
    except Exception:
        return None


# ═══════════════════════════════════════════
# 本地激活状态管理
# ═══════════════════════════════════════════

def save_license(key: str, info: dict):
    """持久化已激活的授权信息（含机器码哈希）"""
    data = {
        "license_key": key,
        "license_type": info["type"],
        "activated_at": info["activated_at"],
        "expires_at": info["expires_at"],
        "is_permanent": info["is_permanent"],
    }
    if "machine_id" in info:
        data["machine_code_hash"] = get_machine_code()
    _write_obfuscated(_LICENSE_FILE, data)


def load_saved_license() -> dict | None:
    """读取本地已保存的授权（含有效期和机器码校验）"""
    data = _read_obfuscated(_LICENSE_FILE)
    if not data:
        return None

    now = int(time.time())

    # 机器码校验（如果是新格式保存的授权）
    stored_hash = data.get("machine_code_hash")
    if stored_hash:
        current_hash = get_machine_code()
        if stored_hash != current_hash:
            return {
                "expired": True,
                "reason": "machine_mismatch",
                "machine_mismatch": True,
                **data,
            }

    # 有效期校验
    if not data.get("is_permanent", False):
        expires = data.get("expires_at", 0)
        if now > expires:
            return {"expired": True, "reason": "license_expired", **data}

    return data


def clear_license():
    if _LICENSE_FILE.exists():
        _LICENSE_FILE.unlink()


# ═══════════════════════════════════════════
# 试用管理
# ═══════════════════════════════════════════

def get_trial_status() -> dict:
    data = _read_obfuscated(_TRIAL_FILE)
    if data is None:
        return {"available": True, "used": False}

    started_at = data.get("first_run", 0)
    elapsed = time.time() - started_at
    remaining = max(0, TRIAL_SECONDS - elapsed)
    expired = remaining <= 0

    return {
        "available": False,
        "used": True,
        "started_at": started_at,
        "elapsed_seconds": int(elapsed),
        "remaining_seconds": int(remaining),
        "is_expired": expired,
    }


def start_trial() -> dict:
    now = time.time()
    _write_obfuscated(_TRIAL_FILE, {"first_run": int(now)})
    return {
        "available": False,
        "used": True,
        "started_at": int(now),
        "elapsed_seconds": 0,
        "remaining_seconds": TRIAL_SECONDS,
        "is_expired": False,
    }


def reset_trial():
    if _TRIAL_FILE.exists():
        _TRIAL_FILE.unlink()


# ═══════════════════════════════════════════
# 统一授权检查
# ═══════════════════════════════════════════

def check() -> dict:
    """综合检查：已激活授权码 → 试用 → 未开始。

    返回示例:
      {"ok": True,  "source": "license", "type": "7d", "remaining_days": 5}
      {"ok": True,  "source": "license", "type": "perm", "is_permanent": True}
      {"ok": True,  "source": "trial",  "remaining_seconds": 3600}
      {"ok": False, "reason": "trial_expired"}
      {"ok": False, "reason": "license_expired"}
      {"ok": False, "reason": "machine_mismatch"}
    """
    saved = load_saved_license()
    if saved:
        if saved.get("expired"):
            reason = saved.get("reason", "license_expired")
            return {"ok": False, "reason": reason, **saved}
        return {
            "ok": True,
            "source": "license",
            "type": saved["license_type"],
            "is_permanent": saved.get("is_permanent", False),
            "remaining_days": -1 if saved.get("is_permanent") else max(
                0, (saved["expires_at"] - int(time.time())) // 86400
            ),
        }

    trial = get_trial_status()
    if trial.get("available"):
        return {"ok": False, "reason": "trial_not_started", "trial_available": True}

    if trial.get("is_expired"):
        return {"ok": False, "reason": "trial_expired"}

    return {
        "ok": True,
        "source": "trial",
        "remaining_seconds": trial["remaining_seconds"],
        "started_at": trial["started_at"],
    }


def activate(key: str) -> dict:
    """激活授权码。自动采集机器码绑定。

    返回: {"ok": True, ...} 或 {"ok": False, "error": "..."}
    """
    machine_code = get_machine_code()
    info = parse_license(key, machine_code=machine_code)
    if info is None:
        return {"ok": False, "error": "授权码无效或不匹配本机"}
    if info.get("is_expired"):
        return {"ok": False, "error": "授权码已过期"}
    save_license(key, info)
    return {"ok": True, **info}


# ═══════════════════════════════════════════
# 便捷查询
# ═══════════════════════════════════════════

def format_remaining(seconds: int) -> str:
    h, m = divmod(seconds, 3600)
    m //= 60
    if h > 0:
        return f"{h}小时{m}分钟"
    return f"{m}分钟"
