"""把企划书源文件 proposal.md 解析成块列表。

只支持企划书用得到的 Markdown 子集，语法见 references/source-format.md：
frontmatter、# / ## / ###、段落、- / 1. 列表、| 表格、![图注|宽cm](路径)、
> 提示框、```chart / ```image JSON 块、<!-- pagebreak -->。
"""
import json
import re

FENCE_RE = re.compile(r"^```\s*(\w+)?\s*$")
IMG_RE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)\s*$")
OL_RE = re.compile(r"^(\s*)(\d+)[.、)]\s+(.*)$")
UL_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
HEAD_RE = re.compile(r"^(#{1,3})\s+(.*?)\s*#*\s*$")


def parse_frontmatter(text):
    meta = {}
    if not text.startswith("---"):
        return meta, text
    end = text.find("\n---", 3)
    if end < 0:
        return meta, text
    for line in text[3:end].splitlines():
        line = line.split(" #", 1)[0].rstrip()
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip('"').strip("'")
    rest = text[end + 4:]
    return meta, rest.lstrip("\n")


def _table_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_sep_row(cells):
    return all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells if c) and any(cells)


def parse(text):
    meta, body = parse_frontmatter(text.replace("\r\n", "\n"))
    lines = body.split("\n")
    blocks = []
    i, n = 0, len(lines)
    para = []

    def flush_para():
        if para:
            blocks.append({"type": "para", "text": " ".join(s.strip() for s in para)})
            para.clear()

    while i < n:
        line = lines[i]
        s = line.strip()

        if not s:
            flush_para()
            i += 1
            continue

        if s in ("<!-- pagebreak -->", "---pagebreak---"):
            flush_para()
            blocks.append({"type": "pagebreak"})
            i += 1
            continue

        m = FENCE_RE.match(s)
        if m:
            flush_para()
            lang = (m.group(1) or "").lower()
            j = i + 1
            buf = []
            while j < n and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            raw = "\n".join(buf)
            i = j + 1
            if lang in ("chart", "image"):
                try:
                    spec = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValueError(f"```{lang} 块 JSON 解析失败（第 {e.lineno} 行）：{e.msg}\n{raw[:200]}")
                blocks.append({"type": lang, "spec": spec})
            else:
                blocks.append({"type": "code", "text": raw})
            continue

        m = HEAD_RE.match(s)
        if m:
            flush_para()
            blocks.append({"type": "heading", "level": len(m.group(1)), "text": m.group(2)})
            i += 1
            continue

        m = IMG_RE.match(s)
        if m:
            flush_para()
            alt = m.group("alt")
            width = None
            if "|" in alt:
                alt, w = alt.rsplit("|", 1)
                try:
                    width = float(w)
                except ValueError:
                    alt = alt + "|" + w
            blocks.append({"type": "image", "spec": {"file": m.group("src").strip(), "caption": alt.strip(), "width": width}})
            i += 1
            continue

        if s.startswith("|"):
            flush_para()
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                cells = _table_row(lines[i])
                if not _is_sep_row(cells):
                    rows.append(cells)
                i += 1
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [""] * (width - len(r)) for r in rows]
                blocks.append({"type": "table", "rows": rows})
            continue

        if s.startswith(">"):
            flush_para()
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            title = ""
            if buf:
                first = buf[0]
                mt = re.fullmatch(r"\[!(.+?)\]\s*(.*)", first) or re.fullmatch(r"\*\*(.+?)\*\*\s*(.*)", first)
                if mt:
                    title = mt.group(1).strip()
                    buf[0] = mt.group(2).strip()
            items = [b for b in buf if b]
            blocks.append({"type": "callout", "title": title, "lines": items})
            continue

        if UL_RE.match(line) or OL_RE.match(line):
            flush_para()
            items = []
            ordered = bool(OL_RE.match(line))
            while i < n:
                cur = lines[i]
                mu, mo = UL_RE.match(cur), OL_RE.match(cur)
                if mu:
                    items.append({"level": len(mu.group(1).replace("\t", "  ")) // 2, "text": mu.group(2), "ordered": False})
                elif mo:
                    items.append({"level": len(mo.group(1).replace("\t", "  ")) // 2, "text": mo.group(3), "ordered": True, "num": int(mo.group(2))})
                elif cur.strip() and cur.startswith("  ") and items:
                    items[-1]["text"] += " " + cur.strip()
                else:
                    break
                i += 1
            blocks.append({"type": "list", "ordered": ordered, "items": items})
            continue

        if re.fullmatch(r"-{3,}|\*{3,}", s):
            flush_para()
            i += 1
            continue

        para.append(s)
        i += 1

    flush_para()
    return meta, blocks
