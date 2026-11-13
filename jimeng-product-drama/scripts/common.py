"""公共工具：定位 dreamina、调用并解析 JSON。"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def dreamina_bin() -> str:
    found = shutil.which("dreamina")
    if found:
        return found
    for cand in (Path.home() / "bin" / "dreamina.exe", Path.home() / ".local" / "bin" / "dreamina"):
        if cand.exists():
            return str(cand)
    sys.exit("找不到 dreamina：先装即梦 CLI（见 SKILL.md「0. 前置检查」）")


def dreamina(args, timeout=300):
    """返回 (解析后的 JSON 或 None, 原始输出)。用参数列表调用，避免中文 prompt 被 shell 转义坏。"""
    r = subprocess.run([dreamina_bin(), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    raw = (r.stdout or "") + (r.stderr or "")
    try:
        return json.loads(r.stdout), raw
    except Exception:
        return None, raw


def ffmpeg(args, timeout=600):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, timeout=timeout)


def probe_duration(path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)
