"""
授权码生成工具（开发者专用）

用法:
  python keygen.py gen-keys        # 首次：生成 Ed25519 密钥对
  python keygen.py show-pub        # 查看公钥（嵌入 license.py）
  python keygen.py make <机器码> <类型>  # 生成绑定机器码的授权码
  python keygen.py verify <授权码>      # 验证授权码是否有效
  python keygen.py machine-id      # 显示本机机器码

类型: 7d=7天, 1m=30天, 1y=365天, perm=永久
"""
import base64
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path


_HERE = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

# 搜索路径列表：EXE 所在目录 → EXE 父目录（dist/..）→ 工作目录
def _find_file(name: str) -> Path | None:
    for base in ([_HERE, _HERE.parent, Path.cwd()] if getattr(sys, 'frozen', False) else [_HERE]):
        p = base / name
        if p.exists():
            return p
    return None

_KEY_FILE = _find_file("secret.key")
_PUB_FILE = _find_file("public.key")

# 如果找不到 key 文件，回退到 _HERE（让错误提示更准确）
if _KEY_FILE is None:
    _KEY_FILE = _HERE / "secret.key"
if _PUB_FILE is None:
    _PUB_FILE = _HERE / "public.key"

PUBLIC_KEY_HEX = ""  # 验证时填入从 gen-keys 输出的公钥


def _load_private() -> bytes:
    if not _KEY_FILE.exists():
        print("未找到 secret.key，请先运行: python keygen.py gen-keys")
        sys.exit(1)
    return _KEY_FILE.read_bytes()


def gen_keys():
    """生成 Ed25519 密钥对（写入当前工作目录）"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, PublicFormat, NoEncryption,
    )

    private = Ed25519PrivateKey.generate()
    public = private.public_key()

    # 写入 CWD（用户运行命令的目录），而非 EXE 所在目录
    cwd = Path.cwd()
    key_path = cwd / "secret.key"
    pub_path = cwd / "public.key"

    key_path.write_bytes(
        private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    )
    pub_path.write_bytes(public.public_bytes(Encoding.Raw, PublicFormat.Raw))

    pub_hex = public.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    print("=" * 55)
    print("  密钥对已生成！")
    print("=" * 55)
    print(f"  私钥: {key_path}  (切勿外泄)")
    print(f"  公钥: {pub_path}")
    print()
    print("  请将以下公钥复制到 license.py 的 PUBLIC_KEY_HEX：")
    print()
    print(f'  PUBLIC_KEY_HEX = "{pub_hex}"')
    print()
    print("  或者在本目录运行: python keygen.py embed")
    print("  (自动将公钥写入同目录下的 license.py)")
    print()


def show_pub():
    """显示公钥"""
    if not _PUB_FILE.exists():
        print("未找到 public.key，请先运行: python keygen.py gen-keys")
        return
    pub_hex = _PUB_FILE.read_bytes().hex()
    print("公钥 (嵌入 license.py):")
    print(f'  PUBLIC_KEY_HEX = "{pub_hex}"')


def embed_pub():
    """将公钥自动写入 license.py"""
    if not _PUB_FILE.exists():
        print("未找到 public.key，请先运行: python keygen.py gen-keys")
        return
    pub_hex = _PUB_FILE.read_bytes().hex()
    # 搜索 license.py：EXE 所在目录 → 父目录 → CWD
    candidates = [_HERE]
    if getattr(sys, 'frozen', False):
        candidates.append(_HERE.parent)
    candidates.append(Path.cwd())
    lic_path = None
    for d in candidates:
        p = d / "license.py"
        if p.exists():
            lic_path = p
            break
    if lic_path is None:
        print("未找到 license.py，请手动将以下公钥粘贴到 license.py 的 PUBLIC_KEY_HEX：")
        print(f'  PUBLIC_KEY_HEX = "{pub_hex}"')
        return
    content = lic_path.read_text(encoding="utf-8")
    import re
    new_content = re.sub(
        r'PUBLIC_KEY_HEX\s*=\s*"[^"]*"',
        f'PUBLIC_KEY_HEX = "{pub_hex}"',
        content,
    )
    if new_content == content:
        print("警告: 未找到 PUBLIC_KEY_HEX 占位符，请手动粘贴")
        print(f'  PUBLIC_KEY_HEX = "{pub_hex}"')
        return
    lic_path.write_text(new_content, encoding="utf-8")
    print(f"公钥已写入 {lic_path}")


def make_license(machine_code: str, lic_type: str) -> str:
    """生成 Ed25519 签名授权码"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

    if lic_type not in ("7d", "1m", "1y", "perm"):
        print(f"未知类型 '{lic_type}'，支持: 7d, 1m, 1y, perm")
        sys.exit(1)

    private = Ed25519PrivateKey.from_private_bytes(_load_private())
    ts = str(int(time.time()))
    mid = machine_code.strip()[:12]
    payload = f"{lic_type}-{ts}-{mid}"

    sig = private.sign(payload.encode())
    sig_b64 = base64.b64encode(sig).rstrip(b"=").decode()

    return f"LIC-{lic_type}-{ts}-{mid}-{sig_b64}"


def verify_license(license_key: str) -> dict:
    """验证授权码（调试用）"""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return {"ok": False, "error": "cryptography 库未安装"}

    pub_hex = PUBLIC_KEY_HEX
    if not pub_hex and _PUB_FILE.exists():
        pub_hex = _PUB_FILE.read_bytes().hex()

    if not pub_hex:
        return {"ok": False, "error": "未设置公钥，请先运行 gen-keys 生成密钥对"}

    try:
        parts = license_key.strip().split("-")
        if len(parts) not in (4, 5) or parts[0] != "LIC":
            return {"ok": False, "error": "授权码格式无效"}

        lic_type = parts[1]
        ts_str = parts[2]
        durations = {"7d": 7, "1m": 30, "1y": 365, "perm": -1}

        if lic_type not in durations:
            return {"ok": False, "error": f"未知类型: {lic_type}"}

        if len(parts) == 5:
            # 新格式 Ed25519
            mid = parts[3]
            sig_b64 = parts[4]
            payload = f"{lic_type}-{ts_str}-{mid}"

            pad = 4 - len(sig_b64) % 4
            if pad < 4:
                sig_b64 += "=" * pad
            signature = base64.b64decode(sig_b64)

            pub_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
            pub_key.verify(signature, payload.encode())

            activated_at = int(ts_str)
            duration = durations[lic_type]
            now = int(time.time())
            expires_at = -1 if duration == -1 else activated_at + duration * 86400

            return {
                "ok": True,
                "type": lic_type,
                "machine_id": mid,
                "is_permanent": duration == -1,
                "is_expired": False if duration == -1 else (now > expires_at),
                "remaining_days": -1 if duration == -1 else max(0, (expires_at - now) // 86400),
            }
        else:
            return {"ok": False, "error": "旧格式 HMAC 授权码，请使用 license.py 验证"}
    except InvalidSignature:
        return {"ok": False, "error": "签名无效 — 授权码被篡改或公钥不匹配"}
    except Exception as e:
        return {"ok": False, "error": f"验证失败: {e}"}


def get_machine_code() -> str:
    """采集本机硬件指纹"""
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


def _interactive_mode():
    """交互菜单模式（双击 EXE 时使用）"""
    print("=" * 55)
    print("  海龟汤授权码生成工具")
    print("=" * 55)
    print()

    while True:
        print("请选择操作:")
        print("  1. 生成授权码")
        print("  2. 查询本机机器码")
        print("  3. 验证授权码")
        print("  0. 退出")
        print()
        choice = input("请输入编号: ").strip()

        if choice == "1":
            mc = input("请输入客户机器码: ").strip()
            if not mc:
                print("错误: 机器码不能为空\n")
                continue
            print("授权类型: 7d=7天  1m=30天  1y=365天  perm=永久")
            lt = input("请输入类型: ").strip()
            if lt not in ("7d", "1m", "1y", "perm"):
                print(f"错误: 未知类型 '{lt}'\n")
                continue
            try:
                code = make_license(mc, lt)
                print(f"\n授权码: {code}\n")
            except Exception as e:
                print(f"错误: {e}\n")

        elif choice == "2":
            try:
                mid = get_machine_code()[:12]
                print(f"\n本机机器码: {mid}\n")
            except Exception as e:
                print(f"错误: {e}\n")

        elif choice == "3":
            lic = input("请输入授权码: ").strip()
            if not lic:
                print("错误: 授权码不能为空\n")
                continue
            result = verify_license(lic)
            for k, v in result.items():
                print(f"  {k}: {v}")
            print()

        elif choice == "0":
            print("已退出")
            break

        else:
            print("无效选择，请重新输入\n")

    input("\n按回车键退出...")


def main():
    if len(sys.argv) < 2:
        _interactive_mode()
        return

    cmd = sys.argv[1]

    if cmd == "gen-keys":
        gen_keys()
    elif cmd == "show-pub":
        show_pub()
    elif cmd == "embed":
        embed_pub()
    elif cmd == "make":
        if len(sys.argv) < 4:
            print("用法: python keygen.py make <机器码> <类型>")
            print("类型: 7d, 1m, 1y, perm")
            return
        code = make_license(sys.argv[2], sys.argv[3])
        print(code)
    elif cmd == "verify":
        if len(sys.argv) < 3:
            print("用法: python keygen.py verify <授权码>")
            return
        result = verify_license(sys.argv[2])
        for k, v in result.items():
            print(f"  {k}: {v}")
    elif cmd == "machine-id":
        print(get_machine_code()[:12])
    elif cmd == "machine-code":
        print(get_machine_code())
    else:
        print(f"未知命令: {cmd}")
        print(__doc__.strip())


if __name__ == "__main__":
    main()
