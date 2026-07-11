"""
授权码生成工具 — 入口转发

实际工具位于项目根目录的 license_tools/ 文件夹中。
请前往 license_tools/ 目录运行命令。

用法:
  cd license_tools
  pip install -r requirements.txt
  python keygen.py gen-keys          # 首次：生成 Ed25519 密钥对
  python keygen.py make <机器码> <类型>  # 生成绑定机器码的授权码
  python keygen.py verify <授权码>      # 验证授权码
"""
import sys
from pathlib import Path


def main():
    _tools_dir = Path(__file__).resolve().parent.parent.parent / "license_tools"
    print(f"本文件仅作入口转发。\n")
    print(f"请前往 license_tools/ 目录运行: cd {_tools_dir}")
    print()
    print(f"或直接运行: python {_tools_dir / 'keygen.py'} {' '.join(sys.argv[1:])}")
    print()
    print(f"首次使用请先安装依赖: pip install -r {_tools_dir / 'requirements.txt'}")


if __name__ == "__main__":
    main()
