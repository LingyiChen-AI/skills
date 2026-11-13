"""把产品视频抽帧拼成联系表，供 Read 看图理解内容。

用法：python 看视频.py <视频> <输出目录> [--every 6]
输出：<输出目录>/sheet_01.jpg ...（每张 3x5=15 帧，每帧左上角标原片时间）
"""
import argparse
import math
from pathlib import Path

import sys as _sys; from pathlib import Path as _P; _sys.path.insert(0, str(_P(__file__).resolve().parent))  # 兼容 python -I
from common import ffmpeg, probe_duration

p = argparse.ArgumentParser()
p.add_argument("video")
p.add_argument("outdir")
p.add_argument("--every", type=float, default=6, help="每隔几秒抽一帧")
a = p.parse_args()

out = Path(a.outdir)
out.mkdir(parents=True, exist_ok=True)
dur = probe_duration(a.video)
per_sheet = 15
n_frames = math.ceil(dur / a.every)
n_sheets = math.ceil(n_frames / per_sheet)
font = "C\\:/Windows/Fonts/msyh.ttc"
for i in range(n_sheets):
    start = i * per_sheet * a.every
    vf = (f"fps=1/{a.every},scale=640:-1,"
          f"drawtext=fontfile='{font}':text='%{{pts\\:hms}}':x=6:y=6:fontsize=18:"
          f"fontcolor=yellow:box=1:boxcolor=black@0.6:boxborderw=6,"
          f"tile=3x5")
    ffmpeg(["-ss", str(start), "-t", str(per_sheet * a.every), "-copyts", "-i", a.video,
            "-vf", vf, "-frames:v", "1", str(out / f"sheet_{i + 1:02d}.jpg")])
print(f"时长 {dur:.1f}s，{n_frames} 帧，联系表 {n_sheets} 张 → {out}")
