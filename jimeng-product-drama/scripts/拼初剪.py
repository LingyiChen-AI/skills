"""把 <项目>/视频段/段XX.mp4 按序拼成 <项目>/初剪.mp4。

- 统一 720x1280 / 30fps / 44.1k 立体声，保留原声（Seedance 自带对白和环境声）
- 右上角全程「AI生成」角标 + 元数据 AIGC 标识（2026-09-01 起微短剧每集必须有）
- 分镜.json 的段里如果有 "subtitles": [[开始秒, 结束秒, "文字"], ...]（段内相对时间），会烧进画面底部

用法：python 拼初剪.py <项目目录>
"""
import json
import sys
from pathlib import Path

import sys as _sys; from pathlib import Path as _P; _sys.path.insert(0, str(_P(__file__).resolve().parent))  # 兼容 python -I
from common import ffmpeg, probe_duration

root = Path(sys.argv[1]).resolve()
cfg = json.loads((root / "分镜.json").read_text(encoding="utf-8"))
segs = sorted((root / "视频段").glob("段*.mp4"))
if not segs:
    raise SystemExit("视频段/ 里没有视频")
expected = {f"段{s['id']:02d}" for s in cfg["segments"]}
missing = sorted(expected - {v.stem for v in segs})
if missing:
    print("注意：缺少", "、".join(missing), "，先拼已有的")

# 字幕：段内相对时间换算成全片时间，写 SRT
srt, offset, idx = [], 0.0, 1
sub_of = {f"段{s['id']:02d}": s.get("subtitles", []) for s in cfg["segments"]}
fmt = lambda t: f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d},{int(t * 1000 % 1000):03d}"
for v in segs:
    for st, en, text in sub_of.get(v.stem, []):
        srt.append(f"{idx}\n{fmt(offset + st)} --> {fmt(offset + en)}\n{text}\n")
        idx += 1
    offset += probe_duration(v)
srt_path = root / "初剪.srt"
if srt:
    srt_path.write_text("\n".join(srt), encoding="utf-8")

font = "C\\:/Windows/Fonts/msyh.ttc"
inputs, parts = [], []
for i, v in enumerate(segs):
    inputs += ["-i", str(v)]
    parts.append(f"[{i}:v]scale=720:1280:force_original_aspect_ratio=decrease,"
                 f"pad=720:1280:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1[v{i}];"
                 f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}];")
n = len(segs)
fc = "".join(parts) + "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac];"
chain = "[vc]"
if srt:
    rel = srt_path.as_posix().replace(":", "\\:")
    fc += (f"{chain}subtitles='{rel}':force_style='FontName=Microsoft YaHei,FontSize=11,"
           f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=1.5,MarginV=60'[vs];")
    chain = "[vs]"
fc += (f"{chain}drawtext=fontfile='{font}':text='AI生成':fontsize=26:fontcolor=white@0.85:"
       f"box=1:boxcolor=black@0.35:boxborderw=8:x=w-tw-28:y=36[vout]")
ffmpeg([*inputs, "-filter_complex", fc, "-map", "[vout]", "-map", "[ac]",
        "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-c:a", "aac", "-b:a", "160k",
        "-metadata", "comment=AIGC: AI生成内容（即梦 Seedance）", str(root / "初剪.mp4")])
print(f"初剪.mp4：{probe_duration(root / '初剪.mp4'):.1f}s，{n} 段" + ("，含字幕" if srt else ""))
