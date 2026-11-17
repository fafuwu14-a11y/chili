#!/usr/bin/env python3
"""Start the 赤鲤 demo server (zero third-party dependencies).

    python run.py                # http://127.0.0.1:8000
    python run.py --port 8080
    python run.py --no-open
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import webbrowser
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
# 打包成 exe 后，前端与数据被解到临时目录（_MEIPASS）；源码运行时就是项目根。
ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) if FROZEN else Path(__file__).resolve().parent
if FROZEN:
    # 数据是只读资源，跟着 exe 走；账号库是可写的，必须留在 exe 旁边，否则一关就没了。
    os.environ.setdefault("CHILI_DATA_DIR", str(ROOT / "backend" / "data"))
    DB_PATH = Path(sys.executable).resolve().parent / "data" / "app.db"
else:
    sys.path.insert(0, str(ROOT / "backend"))
    DB_PATH = None

from app.server import serve  # noqa: E402

BANNER = r"""
   ______  __    __       __
  / ____/ / /   / /      / /
 / /     / /   / /      / /
/ /___  / /___/ /___   / /___
\____/ /_____/_____/  /_____/   ChiLi · 赤鲤
"""


def free_port(host: str, start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise SystemExit(f"端口 {start}-{start + 49} 都被占用了，请用 --port 指定。")


def main() -> None:
    parser = argparse.ArgumentParser(description="赤鲤 · 院校录取概率预测 demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--lan", action="store_true", help="允许同一 Wi-Fi 下的手机访问")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument(
        "--data",
        choices=("auto", "mock", "real"),
        default="auto",
        help="auto = 有真实数据就用真实数据（默认）；mock = 合成演示数据；real = 真实投档线",
    )
    args = parser.parse_args()

    if args.lan:
        args.host = "0.0.0.0"

    if hasattr(sys.stdout, "reconfigure"):
        try:
            # 打包成 exe 后 stdout 默认是块缓冲，双击时黑窗口会一片空白，改成行缓冲。
            sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass

    source = args.data
    if source == "auto":
        # 有真实数据就默认用它，别让人以为「只有三个省」——mock 是给没数据时的兜底。
        source = "real" if (ROOT / "backend" / "data" / "js" / "toudang_2026_physics.csv").exists() else "mock"

    port = free_port(args.host, args.port)
    if port != args.port:
        print(f"  端口 {args.port} 被占用，改用 {port}")

    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{port}/"
    print(BANNER)
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        serve(
            host=args.host,
            port=port,
            frontend_dir=ROOT / "frontend",
            source=source,
            db_path=DB_PATH,
        )
    except OSError as exc:
        raise SystemExit(f"启动失败：{exc}") from exc


if __name__ == "__main__":
    main()
