#!/usr/bin/env python3
"""Create the root virtual environment and optionally install PDF extraction."""
from pathlib import Path
import argparse
import importlib.util
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    p = argparse.ArgumentParser(description="创建统一框架的 Python 环境；核心框架只依赖标准库。")
    p.add_argument("--install-pdf-tools", action="store_true")
    p.add_argument("--init-git", action="store_true")
    args = p.parse_args(argv)
    if sys.version_info < (3, 10):
        p.error("需要 Python 3.10 或更新版本。")
    env = ROOT / ".venv"
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        # pip is unnecessary until optional tools are explicitly requested.
        venv.EnvBuilder(with_pip=args.install_pdf_tools).create(env)
    if args.install_pdf_tools:
        probe = subprocess.run([str(python), "-m", "pip", "--version"], capture_output=True)
        if probe.returncode:
            subprocess.run([str(python), "-m", "ensurepip", "--upgrade"], check=True)
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements-pdf.txt")], check=True)
    if args.init_git:
        result = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True)
        if result.returncode or Path(result.stdout.strip()).resolve() != ROOT.resolve():
            subprocess.run(["git", "init", "-b", "main", str(ROOT)], check=True)
        subprocess.run(["git", "-C", str(ROOT), "config", "core.autocrlf", "false"], check=True)
        subprocess.run(["git", "-C", str(ROOT), "config", "core.quotepath", "false"], check=True)
    print("PYTHON:", python)
    print("SETUP_OK: 根目录与项目共用此环境；无需激活，无需修改 CODEX_HOME。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
