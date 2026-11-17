# 打包「赤鲤」成免安装 exe：数据与前端一起打进去，账号库放 exe 同级 data/。
# 用法：python build_exe.py
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
DATA_SRC = ROOT / "backend" / "data"


def _prepare_data() -> Path:
    """复制一份干净的数据目录：账号库和备份文件不进包。

    账号库由程序在 exe 旁边新建，打包进去只会让每个用户拿到同一份测试账号；
    ``*.bak.json`` 是目录重建时留的旧备份，也不该占用包体积。
    """
    packed = Path(tempfile.mkdtemp(prefix="chili-data-"))

    def ignore(directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name == "app.db" or name.endswith(".bak.json")}

    shutil.copytree(DATA_SRC, packed, ignore=ignore, dirs_exist_ok=True)
    return packed


data_pack = _prepare_data()

# PyInstaller 在 Windows 上用 ; 分隔「源;目标」
add_data = [
    f"{ROOT / 'frontend'};frontend",
    f"{data_pack};backend/data",
]

cmd = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--console",
    "--name", "chili",
    "--paths", str(ROOT / "backend"),
    "--distpath", str(DIST),
    "--workpath", str(BUILD),
    "--specpath", str(BUILD),
    # 账号库由程序自己在 exe 旁边新建，不要打进包里
    "--exclude-module", "tkinter",
]
for item in add_data:
    cmd += ["--add-data", item]
cmd.append(str(ROOT / "run.py"))

print("运行:", " ".join(cmd[:8]), "...")
try:
    result = subprocess.run(cmd, cwd=ROOT)
finally:
    # 临时数据目录只在打包期间存在，别留给下一次构建
    shutil.rmtree(data_pack, ignore_errors=True)
if result.returncode != 0:
    raise SystemExit(f"打包失败，退出码 {result.returncode}")

exe = DIST / ("chili.exe" if sys.platform.startswith("win") else "chili")
size = exe.stat().st_size / 1024 / 1024
print(f"\n打包完成: {exe}  ({size:.1f} MB)")

# 附带一份说明，免得用户拿到 exe 不知道怎么用
readme = DIST / "使用说明.txt"
readme.write_text(
    "赤鲤 · 高考志愿辅助\n\n"
    "1. 双击 chili.exe，会弹出一个黑色窗口，里面有几行地址。\n"
    "2. 浏览器没自动打开的话，手动访问窗口里显示的那个 http://127.0.0.1:xxxx/ 地址。\n"
    "3. 第一次用会跳到登录页，用邮箱 + 密码注册一个本地账号即可（账号只存在这台电脑）。\n"
    "4. 关掉黑窗口就是停止服务；重新打开再来一次即可，账号和数据都还在。\n\n"
    "第一次启动可能要等 3-5 秒（程序在解压数据），之后秒开。\n"
    "如果杀毒软件拦了，选「允许运行」——这是 PyInstaller 打包的通用误报。\n",
    encoding="utf-8",
)
print(f"使用说明: {readme}")
