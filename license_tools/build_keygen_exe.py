"""
构建 keygen.exe

用法: python build_keygen_exe.py [--clean]
"""
import os
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DIST = os.path.join(_HERE, "dist")


def build():
    if "--clean" in sys.argv:
        for p in [_DIST, os.path.join(_HERE, "build"), os.path.join(_HERE, "keygen.spec")]:
            if os.path.isfile(p):
                os.remove(p)
            elif os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)

    os.makedirs(_DIST, exist_ok=True)

    print("Building keygen.exe ...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "keygen",
        "--distpath", _DIST,
        "--workpath", os.path.join(_HERE, "build"),
        "--specpath", _HERE,
        "--hidden-import", "cryptography",
        "--noconfirm",
        os.path.join(_HERE, "keygen.py"),
    ]
    subprocess.check_call(cmd, cwd=_HERE)

    # cleanup
    for f in ["keygen.spec"]:
        p = os.path.join(_HERE, f)
        if os.path.isfile(p):
            os.remove(p)
    build_dir = os.path.join(_HERE, "build")
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir, ignore_errors=True)

    exe_path = os.path.join(_DIST, "keygen.exe")
    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    print(f"\nDone! {exe_path} ({size_mb:.1f} MB)")
    print(f"\n用法:")
    print(f"  keygen gen-keys              # 生成密钥对")
    print(f"  keygen make <机器码> <类型>    # 生成授权码")
    print(f"  keygen verify <授权码>        # 验证授权码")
    print(f"  keygen machine-id            # 获取本机机器码")


if __name__ == "__main__":
    build()
