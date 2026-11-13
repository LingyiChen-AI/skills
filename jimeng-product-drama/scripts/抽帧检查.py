"""每段视频每秒抽一帧拼成联系表，供 Read 看图逐段验收；同时报告时长和平均音量。

用法：python 抽帧检查.py <项目目录> [段号 ...]
输出：<项目>/检查/段XX.jpg
"""
import re
import subprocess
import sys
from pathlib import Path

import sys as _sys; from pathlib import Path as _P; _sys.path.insert(0, str(_P(__file__).resolve().parent))  # 兼容 python -I
from common import ffmpeg, probe_duration

root = Path(sys.argv[1]).resolve()
ids = sys.argv[2:]
chk = root / "检查"
chk.mkdir(exist_ok=True)
for v in sorted((root / "视频段").glob("段*.mp4")):
    if ids and str(int(v.stem[1:])) not in ids:
        continue
    ffmpeg(["-i", str(v), "-vf", "fps=1,scale=300:-1,tile=6x3", "-frames:v", "1", str(chk / f"{v.stem}.jpg")])
    r = subprocess.run(["ffmpeg", "-i", str(v), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    vol = f"{m.group(1)} dB" if m else "无音轨"
    print(f"{v.stem}: {probe_duration(v):.1f}s，平均音量 {vol} → 检查/{v.stem}.jpg")
