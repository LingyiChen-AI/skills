"""把 PDF 渲染成页面缩略总览图，用于出稿后自检版式（空白页、图表截断、表格挤压）。

用法：python preview.py 企划书.pdf [--out 目录] [--dpi 60] [--pages 3,7]
输出：contact.png（全部页面拼图），--pages 指定的页另存为 page-N.png（较高清晰度）。
依赖：pymupdf（pip install pymupdf）。
"""
import argparse
import os
import sys


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out")
    ap.add_argument("--dpi", type=int, default=60)
    ap.add_argument("--pages", default="", help="逗号分隔的页码（从 1 开始），另存高清单页")
    a = ap.parse_args()

    import pymupdf
    from PIL import Image

    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.pdf)), "_preview")
    os.makedirs(out, exist_ok=True)
    doc = pymupdf.open(a.pdf)
    thumbs = []
    blank = []
    sparse = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=a.dpi)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        thumbs.append(im)
        # 去掉页眉页脚后，看正文占了页面多高
        h = page.rect.height
        blocks = [b for b in page.get_text("blocks") if h * 0.07 < b[1] < h * 0.92]
        imgs = [r for img in page.get_images() for r in page.get_image_rects(img[0])]
        bottoms = [b[3] for b in blocks] + [r.y1 for r in imgs]
        footer = [b[4].strip() for b in page.get_text("blocks") if b[1] >= h * 0.92 and b[4].strip().isdigit()]
        label = f"PDF 第 {i + 1} 页（页脚 {footer[0]}）" if footer else f"PDF 第 {i + 1} 页"
        if not bottoms:
            blank.append(label)
            continue
        used = (max(bottoms) - h * 0.07) / (h * 0.85)
        is_last = i == len(doc) - 1
        if i >= 2 and used < 0.25 and not is_last:
            sparse.append(label)
    w, h = thumbs[0].size
    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols + 10 * (cols + 1), h * rows + 10 * (rows + 1)), "#888888")
    for i, im in enumerate(thumbs):
        sheet.paste(im, (10 + (i % cols) * (w + 10), 10 + (i // cols) * (h + 10)))
    sheet_path = os.path.join(out, "contact.png")
    sheet.save(sheet_path)
    for n in [int(x) for x in a.pages.split(",") if x.strip()]:
        if 1 <= n <= len(doc):
            doc[n - 1].get_pixmap(dpi=110).save(os.path.join(out, f"page-{n:02d}.png"))
    print(f"页数 {len(doc)}（封面、目录不计页脚页码，--pages 用 PDF 页序）；总览图 {sheet_path}")
    if blank:
        print(f"空白页：{'、'.join(blank)}（只有页眉页码，没有正文）")
    if sparse:
        print(f"孤页：{'、'.join(sparse)}（正文不到页面 1/4，多半是上一页的尾巴被挤过来了。"
              f"可以缩小前面的图（width 调小）、精简文字，或调整段落顺序）")
    if not blank and not sparse:
        print("版式检查：没有空白页和孤页")


if __name__ == "__main__":
    main()
