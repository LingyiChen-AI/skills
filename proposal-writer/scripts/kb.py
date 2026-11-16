"""知识库：用户指定一个文件夹，写需求单 / 企划书前到里面查资料、数据和素材。没配置就跳过。

用法：
  python kb.py status                   # 看是否配置；输出 JSON，remind=true 表示要在交付消息末尾提醒用户配置
  python kb.py set <文件夹路径>          # 配置知识库目录
  python kb.py unset                    # 取消配置
  python kb.py list [--limit 200]       # 列出知识库里的文件（相对路径、类型、大小）
  python kb.py search 关键词1 关键词2 …  # 按文件名和正文搜索，返回命中文件和上下文片段
  python kb.py read <相对路径> [--max 20000]   # 尽量抽出文字；抽不出时返回 abs_path，用自己的能力打开分析

配置读取顺序：环境变量 PROPOSAL_KB_DIR → <skill_dir>/config.json → ~/.proposal-writer/config.json。
不限文件类型：所有文件都按文件名匹配；docx / pptx / xlsx / pdf / 纯文本还会搜正文。
其他格式（图片、视频、旧版 doc/ppt、设计源文件……）由 Agent 自己打开分析。稿子里用 kb:相对路径 引用素材。
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SKILL_CFG = os.path.join(SKILL, "config.json")
HOME_CFG = os.path.join(os.path.expanduser("~"), ".proposal-writer", "config.json")

# 不限文件类型：所有文件都参与列出和文件名搜索；能抽出文字的（docx / pptx / xlsx / pdf / 各种纯文本）再搜正文。
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".svn"}


# ---------- 配置 ----------

def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def config():
    """返回 (配置字典, 配置文件路径)。"""
    for p in (SKILL_CFG, HOME_CFG):
        if os.path.exists(p):
            return _load(p), p
    return {}, None


def kb_dir():
    env = os.environ.get("PROPOSAL_KB_DIR", "").strip()
    if env:
        return env
    cfg, _ = config()
    return (cfg.get("knowledge_dir") or "").strip()


def _write_cfg(update):
    cfg, path = config()
    cfg.update(update)
    for p in ([path] if path else []) + [SKILL_CFG, HOME_CFG]:
        try:
            _save(p, cfg)
            return p
        except OSError:
            continue
    raise SystemExit("配置写不进去：skill 目录和用户目录都不可写，改用环境变量 PROPOSAL_KB_DIR")


def status():
    d = kb_dir()
    if d and os.path.isdir(d):
        return {"configured": True, "dir": os.path.abspath(d), "files": sum(1 for _ in walk(d))}
    cfg, _ = config()
    first = not cfg.get("reminded")
    if first:
        try:
            _write_cfg({"reminded": True})
        except SystemExit:
            pass
    out = {"configured": False, "remind": first,
           "hint": "知识库未配置。需要时告诉我一个文件夹路径（放品牌资料、往期方案、价格表、logo、二维码等），"
                   "或运行：python <skill_dir>/scripts/kb.py set <文件夹路径>"}
    if d:
        out["error"] = f"配置的目录不存在：{d}"
        out["remind"] = True
    return out


# ---------- 读文件 ----------

def walk(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
        for f in files:
            if f.startswith(("~$", ".")):
                continue
            yield os.path.join(d, f)


def _docx_text(path):
    x = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8", "ignore")
    paras = re.findall(r"<w:p[ >].*?</w:p>", x, re.S)
    return "\n".join("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)) for p in paras)


def _xlsx_text(path):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            out.append(f"## {ws.title}")
            for row in ws.iter_rows(values_only=True):
                if any(v is not None for v in row):
                    out.append("\t".join("" if v is None else str(v) for v in row))
        return "\n".join(out)
    except ImportError:
        z = zipfile.ZipFile(path)
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            sx = z.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
            shared = ["".join(re.findall(r"<t[^>]*>([^<]*)</t>", si)) for si in re.findall(r"<si>.*?</si>", sx, re.S)]
        out = []
        for n in sorted(x for x in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", x)):
            out.append(f"## {n.split('/')[-1]}")
            sx = z.read(n).decode("utf-8", "ignore")
            for row in re.findall(r"<row[^>]*>(.*?)</row>", sx, re.S):
                cells = []
                for attrs, body in re.findall(r"<c([^>]*)>(.*?)</c>", row, re.S):
                    v = re.search(r"<v>([^<]*)</v>", body)
                    t = re.search(r"<t[^>]*>([^<]*)</t>", body)
                    if 't="s"' in attrs and v:
                        cells.append(shared[int(v.group(1))] if int(v.group(1)) < len(shared) else "")
                    else:
                        cells.append((v or t).group(1) if (v or t) else "")
                if any(cells):
                    out.append("\t".join(cells))
        return "\n".join(out)


def _pdf_text(path):
    import fitz
    with fitz.open(path) as doc:
        return "\n".join(p.get_text() for p in doc)


def _pptx_text(path):
    z = zipfile.ZipFile(path)
    slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                    key=lambda n: int(re.search(r"(\d+)", n.split("/")[-1]).group(1)))
    out = []
    for i, n in enumerate(slides, 1):
        x = z.read(n).decode("utf-8", "ignore")
        paras = re.findall(r"<a:p>.*?</a:p>|<a:p .*?</a:p>", x, re.S)
        lines = ["".join(re.findall(r"<a:t>([^<]*)</a:t>", q)) for q in paras]
        out.append(f"## 第 {i} 页\n" + "\n".join(l for l in lines if l.strip()))
    return "\n".join(out)


def _plain_text(path):
    """不认识的扩展名：前 4KB 没有 NUL 字节就当文本读（utf-8 / gbk）。"""
    with open(path, "rb") as f:
        head = f.read(4096)
    if not head or b"\x00" in head:
        return None
    with open(path, "rb") as f:
        raw = f.read(2_000_000)
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def read_text(path, limit=None):
    """尽量抽出文字。返回 None 表示脚本读不出（图片、视频、旧版 doc/ppt、设计源文件……），要用你自己的能力打开分析。"""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in IMG_EXT:
            return None
        if ext in (".docx", ".docm", ".dotx"):
            s = _docx_text(path)
        elif ext in (".pptx", ".pptm", ".ppsx", ".potx"):
            s = _pptx_text(path)
        elif ext in (".xlsx", ".xlsm"):
            s = _xlsx_text(path)
        elif ext == ".pdf":
            s = _pdf_text(path)
        elif ext == ".csv":
            with open(path, encoding="utf-8-sig", errors="ignore") as f:
                s = "\n".join("\t".join(r) for r in csv.reader(f))
        else:
            s = _plain_text(path)
            if s is None:
                return None
    except Exception:  # noqa: BLE001
        return None
    return s[:limit] if limit else s


def kind(path):
    return "图片" if os.path.splitext(path)[1].lower() in IMG_EXT else "文件"


# ---------- 命令 ----------

def need_dir():
    d = kb_dir()
    if not d or not os.path.isdir(d):
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        sys.exit(0)
    return d


def cmd_list(limit):
    d = need_dir()
    rows = []
    for p in walk(d):
        rel = os.path.relpath(p, d).replace("\\", "/")
        rows.append({"path": rel, "ext": os.path.splitext(p)[1].lower() or "(无)", "type": kind(p), "kb_ref": "kb:" + rel,
                     "kb": os.path.getsize(p) // 1024})
    rows.sort(key=lambda r: r["path"])
    return {"dir": os.path.abspath(d), "total": len(rows), "files": rows[:limit]}


def cmd_search(words, per_file=3, max_files=30):
    d = need_dir()
    words = [w for w in words if w.strip()]
    hits = []
    for p in walk(d):
        rel = os.path.relpath(p, d).replace("\\", "/")
        name_hit = [w for w in words if w.lower() in rel.lower()]
        snippets, body_hit = [], []
        text = read_text(p, 400000)
        if text:
            low = text.lower()
            for w in words:
                i = low.find(w.lower())
                if i >= 0:
                    body_hit.append(w)
                    if len(snippets) < per_file:
                        snippets.append(re.sub(r"\s+", " ", text[max(0, i - 80): i + 160]).strip())
        matched = sorted(set(name_hit) | set(body_hit))
        if matched:
            hits.append({"path": rel, "type": kind(p), "kb_ref": "kb:" + rel, "matched": matched,
                         "score": len(matched) * 2 + len(name_hit), "snippets": snippets,
                         "text_extracted": text is not None})
    hits.sort(key=lambda h: -h["score"])
    return {"dir": os.path.abspath(d), "words": words, "total": len(hits), "hits": hits[:max_files]}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="知识库目录：配置、列出、搜索、读取")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("status")
    s = sub.add_parser("set"); s.add_argument("dir")
    sub.add_parser("unset")
    s = sub.add_parser("list"); s.add_argument("--limit", type=int, default=200)
    s = sub.add_parser("search"); s.add_argument("words", nargs="+")
    s = sub.add_parser("read"); s.add_argument("path"); s.add_argument("--max", type=int, default=20000)
    a = ap.parse_args()
    if a.cmd == "set":
        d = os.path.abspath(os.path.expanduser(a.dir))
        if not os.path.isdir(d):
            raise SystemExit(f"目录不存在：{d}")
        p = _write_cfg({"knowledge_dir": d, "reminded": True})
        out = {"configured": True, "dir": d, "config_file": p, "files": sum(1 for _ in walk(d))}
    elif a.cmd == "unset":
        out = {"configured": False, "config_file": _write_cfg({"knowledge_dir": ""})}
    elif a.cmd == "list":
        out = cmd_list(a.limit)
    elif a.cmd == "search":
        out = cmd_search(a.words)
    elif a.cmd == "read":
        d = need_dir()
        p = os.path.normpath(os.path.join(d, a.path[3:] if a.path.startswith("kb:") else a.path))
        if not p.startswith(os.path.normpath(d)) or not os.path.isfile(p):
            raise SystemExit(f"知识库里没有这个文件：{a.path}")
        text = read_text(p, a.max)
        if text is None:
            print(json.dumps({"path": a.path, "abs_path": p, "text_extracted": False,
                              "note": "脚本抽不出文字（图片、视频、旧版 doc/ppt/xls、设计源文件等）。"
                                      "用你自己的能力打开这个文件分析：图片直接看，其他格式用平台的文件读取 / 转换能力。"},
                             ensure_ascii=False, indent=2))
        else:
            print(text)
        return
    else:
        out = status()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
