"""设计需求单一键出稿：brief.md → docx（+ pdf）。

用法：
  python brief.py --check                    # 检查运行环境（同 build.py --check）
  python brief.py brief.md --list-images     # 列出要生成的参考示意图（```image 块）
  python brief.py brief.md                   # 出 docx + pdf，放在 md 同目录
  python brief.py brief.md --format docx

图片路径可以写 brand:logo.png，指向 brands/<frontmatter 的 brand>/logo.png。
输出 JSON：outputs（文件）、todos（文中的【待补】）、warnings（品牌规则检查、缺图、PDF 失败）。
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, HERE)

PHONE_RE = re.compile(r"1[3-9]\d[\s-]?\d{4}[\s-]?\d{4}|0\d{2,3}-\d{7,8}")


def read_brief(md_path):
    """读 brief.md；把每行 !! 大字文案前后补空行，保证各自成段。"""
    with open(md_path, encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n")
    out = []
    for line in text.split("\n"):
        if line.strip().startswith("!!"):
            out += ["", line.strip(), ""]
        else:
            out.append(line)
    return "\n".join(out)


def brand_dir(meta):
    return os.path.join(SKILL, "brands", meta.get("brand", "runjie"))


def resolve_src(src, meta, base):
    if src.startswith("brand:"):
        return os.path.join(brand_dir(meta), src[len("brand:"):])
    return os.path.join(base, src)


def lint(meta, raw, report):
    path = os.path.join(brand_dir(meta), "rules.json")
    if not os.path.exists(path):
        report["warnings"].append(f"没找到品牌档案 {path}，跳过品牌规则检查")
        return
    with open(path, encoding="utf-8") as f:
        rules = json.load(f)
    body = raw.split("\n---", 1)[-1] if raw.startswith("---") else raw
    for r in rules.get("forbidden", []):
        if r["text"] in body:
            report["warnings"].append(f"出现「{r['text']}」：{r['why']}")
    typ = meta.get("type", "")
    for need in rules.get("required_by_type", {}).get(typ, []):
        if need not in body:
            report["warnings"].append(f"{typ}缺少「{need}」")
    if typ in rules.get("phone_blank_types", []) and PHONE_RE.search(body):
        report["warnings"].append(f"{typ}里写了电话号码：{rules.get('phone_blank_why', '号码应留白')}")


def image_specs(blocks):
    return [b["spec"] for b in blocks if b["type"] == "image" and b["spec"].get("prompt")]


def list_images(md_path):
    import mdparse

    base = os.path.dirname(os.path.abspath(md_path))
    meta, blocks = mdparse.parse(read_brief(md_path))
    out = []
    for s in image_specs(blocks):
        p = resolve_src(s["file"], meta, base)
        out.append({"file": s["file"], "save_to": p, "ratio": s.get("ratio", "4:3"), "caption": s.get("caption", ""),
                    "prompt": s.get("prompt", ""), "done": os.path.exists(p)})
    return {"total": len(out), "todo": sum(1 for x in out if not x["done"]), "images": out}


def build(md_path, out_dir=None, formats=("docx", "pdf")):
    import images
    import mdparse
    from build import safe_name, to_pdf
    from render_brief import BriefRenderer

    md_path = os.path.abspath(md_path)
    base = os.path.dirname(md_path)
    out_dir = os.path.abspath(out_dir or base)
    os.makedirs(out_dir, exist_ok=True)
    raw = read_brief(md_path)
    meta, blocks = mdparse.parse(raw)
    report = {"type": meta.get("type", ""), "brand": meta.get("brand", "runjie"), "todos": [],
              "placeholders": [], "warnings": []}
    lint(meta, raw, report)

    r = BriefRenderer(meta, base)
    r.header()
    pending = []

    def flush_images():
        if pending:
            r.images(pending)
            pending.clear()

    for b in blocks:
        t = b["type"]
        if t != "image":
            flush_images()
        if t == "heading":
            r.heading(b["level"], b["text"])
        elif t == "para":
            r.para(b["text"])
        elif t == "list":
            r.bullets(b["items"])
        elif t == "table":
            r.table(b["rows"])
        elif t == "callout":
            r.callout(b["title"], b["lines"])
        elif t == "image":
            s = b["spec"]
            path = resolve_src(s["file"], meta, base)
            if not os.path.exists(path):
                if s.get("prompt"):
                    ph = os.path.join(base, "_placeholders", s["file"].replace("/", "_").replace(":", "_"))
                    images.placeholder(ph, s.get("caption", ""), s.get("prompt", ""), s.get("ratio", "4:3"))
                    report["placeholders"].append(s["file"])
                    path = ph
                else:
                    report["warnings"].append(f"图片不存在：{s['file']}")
            pending.append((path, s.get("caption", ""), s.get("width")))
        elif t == "code":
            r.para(b["text"])
    flush_images()

    report["todos"] = list(dict.fromkeys(x.strip() for x in r.todos if x.strip()))
    name = safe_name(meta.get("filename") or meta.get("title", "设计需求单"))
    outputs = {"docx": r.save(os.path.join(out_dir, name + ".docx"))}
    if "pdf" in formats:
        pdf, err = to_pdf(outputs["docx"], out_dir)
        if pdf:
            outputs["pdf"] = pdf
        else:
            report["warnings"].append(f"PDF 没生成：{err}")
    if "docx" not in formats and "pdf" in outputs:
        os.remove(outputs.pop("docx"))
    report["outputs"] = outputs
    return report


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="设计需求单 brief.md → docx / pdf")
    ap.add_argument("md", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--format", default="docx,pdf")
    ap.add_argument("--list-images", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check or not a.md:
        from build import check_env
        sys.exit(0 if check_env() else 1)
    if a.list_images:
        print(json.dumps(list_images(a.md), ensure_ascii=False, indent=2))
        return
    print(json.dumps(build(a.md, a.out, tuple(x.strip() for x in a.format.split(","))), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
