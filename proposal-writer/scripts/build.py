"""企划书一键成稿：proposal.md → 统计图 + 配图 → docx → pdf。

用法：
  python build.py --check                       # 检查运行环境（第一次用先跑）
  python build.py proposal.md --list-images     # 列出要画的配图（提示词、比例、存放路径、是否已画）
  python build.py proposal.md                   # 出 docx + pdf，放在 md 同目录
  python build.py proposal.md -o out --format docx

配图由运行本技能的 Agent 用自己的生图能力生成，存到 ```image 块的 file 路径后再 build。
build 时还缺的图会放占位图（存在 _placeholders/，不占正式路径），并在输出 JSON 的 placeholders 里列出。
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def check_env():
    ok = True
    rows = []
    for mod, pip_name in (("docx", "python-docx"), ("matplotlib", "matplotlib"), ("PIL", "pillow")):
        try:
            __import__(mod)
            rows.append((pip_name, "OK"))
        except ImportError:
            rows.append((pip_name, f"缺失 → pip install {pip_name}"))
            ok = False
    try:
        from matplotlib import font_manager
        import charts  # noqa: F401
        have = {f.name for f in font_manager.fontManager.ttflist}
        cjk = next((n for n in charts.CJK_FONTS if n in have), None)
        rows.append(("中文字体（统计图）", cjk or "没有 → 图中中文会变方块，装 Noto Sans CJK / 思源黑体"))
    except Exception as e:  # noqa: BLE001
        rows.append(("中文字体（统计图）", f"检查失败：{e}"))
    soffice = find_soffice()
    rows.append(("LibreOffice（转 PDF）", soffice or "没有 → 只能出 docx（见 workflow.md「没有 LibreOffice」）"))
    for k, v in rows:
        print(f"  {k:<24} {v}")
    return ok


def find_soffice():
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    cands = ["C:/Program Files/LibreOffice/program/soffice.exe", "C:/Program Files (x86)/LibreOffice/program/soffice.exe",
             "/Applications/LibreOffice.app/Contents/MacOS/soffice", "/usr/bin/soffice", "/opt/libreoffice/program/soffice"]
    cands += glob.glob("/opt/libreoffice*/program/soffice")
    return next((c for c in cands if os.path.exists(c)), None)


def to_pdf(docx_path, out_dir):
    soffice = find_soffice()
    if not soffice:
        return None, "没找到 LibreOffice"
    # 独立的用户配置目录，避免和正在运行的 LibreOffice 抢锁
    profile = tempfile.mkdtemp(prefix="lo_profile_")
    uri = "file:///" + profile.replace("\\", "/").lstrip("/")
    cmd = [soffice, f"-env:UserInstallation={uri}", "--headless", "--convert-to", "pdf", "--outdir", out_dir, docx_path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
    except subprocess.TimeoutExpired:
        return None, "LibreOffice 转换超时"
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    pdf = os.path.join(out_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
    if os.path.exists(pdf):
        return pdf, None
    return None, (r.stderr or r.stdout or "未知错误").strip()[:400]


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_") or "企划书"


INCLUDE_RE = re.compile(r"^<!--\s*include:\s*(.+?)\s*-->\s*$", re.M)


def read_source(md_path):
    """读 proposal.md，并把 <!-- include: 文件.md --> 替换成该文件内容（如 finance.py 生成的测算章节）。"""
    base = os.path.dirname(os.path.abspath(md_path))
    with open(md_path, encoding="utf-8") as f:
        text = f.read()

    def sub(m):
        p = os.path.join(base, m.group(1))
        if not os.path.exists(p):
            return f"【缺少引用文件：{m.group(1)}】"
        with open(p, encoding="utf-8") as g:
            return g.read().strip("\n")

    return INCLUDE_RE.sub(sub, text)


def image_specs(meta, blocks):
    """封面 + 正文所有 ```image / ![]() 配图，按出现顺序。"""
    specs = []
    if meta.get("cover_image"):
        specs.append({"file": meta["cover_image"], "prompt": meta.get("cover_prompt", ""),
                      "caption": "封面主视觉", "ratio": meta.get("cover_ratio", "16:9")})
    for b in blocks:
        if b["type"] == "image":
            specs.append(b["spec"])
    return specs


def list_images(md_path):
    import mdparse

    base = os.path.dirname(os.path.abspath(md_path))
    meta, blocks = mdparse.parse(read_source(md_path))
    out = []
    for s in image_specs(meta, blocks):
        path = os.path.join(base, s["file"])
        out.append({"file": s["file"], "save_to": path, "ratio": s.get("ratio", "16:9"),
                    "caption": s.get("caption", ""), "prompt": s.get("prompt", ""), "done": os.path.exists(path)})
    todo = sum(1 for x in out if not x["done"])
    return {"total": len(out), "todo": todo, "images": out}


def resolve_image(spec, base, report):
    import images

    path = os.path.join(base, spec["file"])
    report["images"].append(spec["file"])
    if os.path.exists(path):
        return path
    # 占位图放在单独目录，不占正式路径：补画到 file 路径后重跑 build 就会用上真图
    ph = os.path.join(base, "_placeholders", spec["file"].replace("/", "_").replace("\\", "_"))
    images.placeholder(ph, spec.get("caption", ""), spec.get("prompt", ""), spec.get("ratio", "16:9"))
    report["placeholders"].append(spec["file"])
    return ph


def build(md_path, out_dir=None, formats=("docx", "pdf")):
    import charts
    import mdparse
    from render_docx import Renderer

    md_path = os.path.abspath(md_path)
    base = os.path.dirname(md_path)
    out_dir = os.path.abspath(out_dir or base)
    os.makedirs(out_dir, exist_ok=True)
    meta, blocks = mdparse.parse(read_source(md_path))

    report = {"chapters": 0, "charts": 0, "tables": 0, "images": [], "placeholders": [], "warnings": []}
    r = Renderer(meta, base)
    theme = "#" + meta.get("theme", "#1F5FBF").lstrip("#")

    cover = None
    if meta.get("cover_image"):
        cover = resolve_image(image_specs(meta, [])[0], base, report)
    r.cover(cover)
    r.toc(blocks)
    r.start_body()

    chart_no = 0
    pending_table_caption = None
    for b in blocks:
        t = b["type"]
        if t == "para":
            m = re.fullmatch(r"表[:：]\s*(.+)", b["text"])
            if m:
                pending_table_caption = m.group(1)
                continue
        if pending_table_caption and t != "table":
            r.para("表：" + pending_table_caption)
            pending_table_caption = None
        if t == "heading":
            if b["level"] == 1:
                report["chapters"] += 1
            r.heading(b["level"], b["text"])
        elif t == "para":
            r.para(b["text"])
        elif t == "list":
            r.bullets(b["items"])
        elif t == "table":
            r.table(b["rows"], pending_table_caption)
            pending_table_caption = None
            report["tables"] += 1
        elif t == "callout":
            r.callout(b["title"], b["lines"])
        elif t == "chart":
            chart_no += 1
            spec = b["spec"]
            png = os.path.join(base, "charts", f"chart-{chart_no:02d}-{spec.get('type', 'x')}.png")
            try:
                charts.render(spec, png, theme)
                r.image(png, spec.get("caption") or spec.get("title"), spec.get("width"))
                report["charts"] += 1
            except Exception as e:  # noqa: BLE001
                report["warnings"].append(f"第 {chart_no} 张统计图失败：{e}")
                r.para(f"【统计图生成失败：{e}】")
        elif t == "image":
            spec = b["spec"]
            path = resolve_image(spec, base, report)
            r.image(path, spec.get("caption"), spec.get("width"))
        elif t == "code":
            r.code(b["text"])
        elif t == "pagebreak":
            r.pagebreak()

    name = safe_name(meta.get("filename") or meta.get("title", "企划书"))
    outputs = {}
    docx_path = r.save(os.path.join(out_dir, name + ".docx"))
    outputs["docx"] = docx_path
    if "pdf" in formats:
        pdf, err = to_pdf(docx_path, out_dir)
        if pdf:
            outputs["pdf"] = pdf
        else:
            report["warnings"].append(f"PDF 没生成：{err}")
    if "docx" not in formats and "pdf" in outputs:
        os.remove(docx_path)
        outputs.pop("docx")
    if report["placeholders"]:
        report["warnings"].append(f"{len(report['placeholders'])} 张配图还没画，用了占位图：先生图存到对应路径，再重跑 build")
    report["outputs"] = outputs
    return report


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="企划书 proposal.md → docx / pdf")
    ap.add_argument("md", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--format", default="docx,pdf", help="docx、pdf 或 docx,pdf")
    ap.add_argument("--list-images", action="store_true", help="只列出需要画的配图，不出稿")
    ap.add_argument("--check", action="store_true", help="只检查运行环境")
    a = ap.parse_args()
    if a.check or not a.md:
        sys.exit(0 if check_env() else 1)
    if a.list_images:
        print(json.dumps(list_images(a.md), ensure_ascii=False, indent=2))
        return
    rep = build(a.md, a.out, tuple(x.strip() for x in a.format.split(",")))
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
