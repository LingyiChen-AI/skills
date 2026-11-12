"""配图工具：把生图结果存到指定路径 + 占位图兜底。

图片由运行本技能的 Agent 用自己的生图能力生成（千问办公：生图任务），本脚本不调任何生图接口。

存图：python images.py save <图片链接或本地文件> <目标路径>
      生图结果是 URL 就下载，是本地文件就复制；统一转成 PNG，过大的图缩到长边 2400px。
"""
import argparse
import os
import shutil
import sys
import tempfile
import textwrap
import urllib.request

RATIO_SIZE = {"16:9": (1664, 928), "4:3": (1472, 1104), "1:1": (1328, 1328), "3:4": (1104, 1472), "9:16": (928, 1664)}

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
]


def save(src, out_path, max_side=2400):
    """src 可以是 http(s) 链接或本地路径；保存为 PNG 到 out_path。"""
    from PIL import Image

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = None
    if src.startswith(("http://", "https://")):
        fd, tmp = tempfile.mkstemp(suffix=".img")
        os.close(fd)
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        src = tmp
    try:
        im = Image.open(src)
        im.load()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        if max(im.size) > max_side:
            im.thumbnail((max_side, max_side))
        im.save(out_path, "PNG")
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
    return out_path


def placeholder(out_path, caption, prompt="", ratio="16:9"):
    """画一张浅灰占位图，写明图注和提示词，提醒后续补图。"""
    from PIL import Image, ImageDraw, ImageFont

    w, h = RATIO_SIZE.get(ratio, RATIO_SIZE["16:9"])
    img = Image.new("RGB", (w, h), "#f0efec")
    d = ImageDraw.Draw(img)
    font_path = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)

    def font(size):
        return ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()

    d.rectangle([24, 24, w - 24, h - 24], outline="#c3c2b7", width=4)
    d.text((w / 2, h * 0.36), "配图待生成", fill="#52514e", font=font(64), anchor="mm")
    d.text((w / 2, h * 0.48), caption or "", fill="#0b0b0b", font=font(44), anchor="mm")
    y = h * 0.60
    for ln in textwrap.wrap(prompt, 38)[:5]:
        d.text((w / 2, y), ln, fill="#7a7974", font=font(30), anchor="mm")
        y += 44
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path)
    return out_path


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="把生图结果存到企划书指定路径")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save", help="下载 / 复制图片并转成 PNG")
    s.add_argument("src", help="图片链接或本地文件路径")
    s.add_argument("out", help="目标路径（```image 块的 file，相对 proposal.md 所在目录）")
    a = ap.parse_args()
    try:
        print("已保存：" + save(a.src, a.out))
    except Exception as e:  # noqa: BLE001
        print(f"保存失败：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
