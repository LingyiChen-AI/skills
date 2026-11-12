"""把解析后的块渲染成企划书风格的 docx。

版式：封面 → 目录 → 正文（每个一级章节另起一页，页眉写标题、页脚写页码）。
主色由 frontmatter 的 theme 决定，标题、表头、提示框、分隔线都跟着主色走。
"""
import os
import re

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

INK = "1F1F1F"
INK2 = "5A5955"
MUTED = "8A8984"
LINE = "D9D8D3"
PAGE_W_CM = 21.0
MARGIN_CM = 2.2
CONTENT_W_CM = PAGE_W_CM - 2 * MARGIN_CM

CN_NUM = "零一二三四五六七八九十"


# ---------- 底层工具 ----------

def _hex(c):
    return RGBColor.from_string(c.lstrip("#").upper())


def _tint(hex_color, ratio):
    """把主色往白色混，ratio=0.9 表示 90% 白。"""
    c = hex_color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda v: int(v + (255 - v) * ratio)  # noqa: E731
    return f"{mix(r):02X}{mix(g):02X}{mix(b):02X}"


def _set_font(run, font, size=None, bold=None, color=None):
    run.font.name = font
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), font)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color:
        run.font.color.rgb = _hex(color)


def _style_font(style, font, size, bold=False, color=INK):
    style.font.name = font
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = _hex(color)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in list(rfonts.attrib):
        del rfonts.attrib[attr]
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), font)


def _p_border(p, side, color, sz=8, space=4):
    ppr = p._p.get_or_add_pPr()
    bdr = ppr.find(qn("w:pBdr"))
    if bdr is None:
        bdr = OxmlElement("w:pBdr")
        ppr.append(bdr)
    el = OxmlElement(f"w:{side}")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(sz))
    el.set(qn("w:space"), str(space))
    el.set(qn("w:color"), color.lstrip("#"))
    bdr.append(el)


def _shade(cell, fill):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill.lstrip("#"))
    tcpr.append(shd)


def _cell_borders(cell, **sides):
    """sides: top/bottom/left/right = (color, sz) 或 None(无边框)"""
    tcpr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        spec = sides.get(side)
        if spec is None:
            el.set(qn("w:val"), "nil")
        else:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(spec[1]))
            el.set(qn("w:color"), spec[0].lstrip("#"))
        borders.append(el)
    tcpr.append(borders)


def _cell_margins(cell, top=80, bottom=80, left=120, right=120):
    tcpr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for k, v in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        el = OxmlElement(f"w:{k}")
        el.set(qn("w:w"), str(v))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tcpr.append(mar)


def _table_no_borders(table):
    tblpr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tblpr.append(borders)


def _field(run, instr):
    for tag, text in (("begin", None), ("instr", instr), ("separate", None), ("text", "1"), ("end", None)):
        if tag == "instr":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        elif tag == "text":
            el = OxmlElement("w:t")
            el.text = text
        else:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), tag)
        run._r.append(el)


def _keep_with_next(p):
    p.paragraph_format.keep_with_next = True


def _spacing(p, before=0, after=6, line=1.5):
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line


def _text_len(s):
    s = s.replace("**", "")
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def _is_num(s):
    s = s.replace("**", "").replace(" ", "")
    return bool(re.fullmatch(r"[-+¥$￥]?[\d,.]+%?", s))


def _col_widths(rows, total):
    """按每列最长文字（中文算 2）分配列宽，短列不小于 2cm，长列封顶。"""
    lens = []
    for ci in range(len(rows[0])):
        longest = max(_text_len(r[ci]) for r in rows)
        lens.append(min(max(longest, 6), 60))
    s = sum(lens)
    w = [total * x / s for x in lens]
    w = [max(x, 2.0) for x in w]
    k = total / sum(w)
    return [x * k for x in w]


# ---------- 渲染器 ----------

class Renderer:
    def __init__(self, meta, base_dir):
        self.meta = meta
        self.base = base_dir
        self.theme = "#" + meta.get("theme", "#1F5FBF").lstrip("#")
        self.font = meta.get("font", "Microsoft YaHei")
        self.numbering = str(meta.get("numbering", "true")).lower() not in ("false", "no", "0", "off")
        self.doc = Document()
        self.h1 = 0
        self.h2 = 0
        self.fig = 0
        self.tab = 0
        self.first_h1 = True
        self._base_styles()

    # 样式
    def _base_styles(self):
        st = self.doc.styles
        _style_font(st["Normal"], self.font, 10.5, color=INK)
        pf = st["Normal"].paragraph_format
        pf.line_spacing = 1.5
        pf.space_after = Pt(6)
        _style_font(st["Heading 1"], self.font, 20, True, INK)
        _style_font(st["Heading 2"], self.font, 14, True, self.theme)
        _style_font(st["Heading 3"], self.font, 12, True, INK)
        for name in ("Heading 1", "Heading 2", "Heading 3"):
            st[name].paragraph_format.keep_with_next = True
        sec = self.doc.sections[0]
        sec.page_width, sec.page_height = Cm(21), Cm(29.7)
        for side in ("left_margin", "right_margin"):
            setattr(sec, side, Cm(MARGIN_CM))
        sec.top_margin = Cm(2.4)
        sec.bottom_margin = Cm(2.2)

    # 行内 **粗体**
    def _inline(self, p, text, size=10.5, color=INK, bold=False):
        parts = re.split(r"(\*\*[^*]+\*\*)", text)
        for part in parts:
            if not part:
                continue
            is_b = part.startswith("**") and part.endswith("**") and len(part) > 4
            run = p.add_run(part[2:-2] if is_b else part)
            _set_font(run, self.font, size, bold or is_b, self.theme.lstrip("#") if is_b and not bold else color)

    # 封面
    def cover(self, cover_img=None):
        d, m = self.doc, self.meta
        p = d.add_paragraph()
        _spacing(p, before=60 if not cover_img else 20, after=4, line=1.0)
        r = p.add_run(m.get("kicker", "企 划 书  ·  PROPOSAL"))
        _set_font(r, self.font, 11, True, self.theme)

        p = d.add_paragraph()
        _spacing(p, before=6, after=6, line=1.15)
        r = p.add_run(m.get("title", "企划书"))
        _set_font(r, self.font, 30, True, INK)

        if m.get("subtitle"):
            p = d.add_paragraph()
            _spacing(p, after=10, line=1.3)
            r = p.add_run(m["subtitle"])
            _set_font(r, self.font, 14, False, INK2)

        p = d.add_paragraph()
        _spacing(p, after=18, line=1.0)
        _p_border(p, "bottom", self.theme, sz=24, space=1)

        if cover_img and os.path.exists(cover_img):
            p = d.add_paragraph()
            _spacing(p, after=18, line=1.0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(cover_img, width=Cm(CONTENT_W_CM))

        fields = (("客户 / 项目方", "client"), ("编制单位", "author"), ("日期", "date"), ("版本", "version"))
        rows = [(k, m[f]) for k, f in fields if m.get(f)]
        if rows:
            p = d.add_paragraph()
            _spacing(p, before=0 if cover_img else 150, after=0, line=1.0)
            t = d.add_table(rows=len(rows), cols=2)
            _table_no_borders(t)
            t.columns[0].width, t.columns[1].width = Cm(3.2), Cm(CONTENT_W_CM - 3.2)
            for i, (k, v) in enumerate(rows):
                c0, c1 = t.rows[i].cells
                c0.width, c1.width = Cm(3.2), Cm(CONTENT_W_CM - 3.2)
                for c in (c0, c1):
                    _cell_borders(c, bottom=(LINE, 4))
                    _cell_margins(c, 60, 60, 0, 60)
                p0 = c0.paragraphs[0]
                _spacing(p0, after=0, line=1.2)
                _set_font(p0.add_run(k), self.font, 10, False, MUTED)
                p1 = c1.paragraphs[0]
                _spacing(p1, after=0, line=1.2)
                _set_font(p1.add_run(v), self.font, 11, True, INK)

        if m.get("confidential"):
            p = d.add_paragraph()
            _spacing(p, before=24, after=0, line=1.0)
            _set_font(p.add_run(m["confidential"]), self.font, 9, False, MUTED)

    # 目录（静态：列出章节，不带页码，避免依赖 Word 更新域）
    def toc(self, blocks):
        d = self.doc
        d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        p = d.add_paragraph()
        _spacing(p, after=4, line=1.0)
        _set_font(p.add_run("目录"), self.font, 22, True, INK)
        p = d.add_paragraph()
        _spacing(p, after=14, line=1.0)
        _set_font(p.add_run("CONTENTS"), self.font, 10, True, self.theme)
        _p_border(p, "bottom", self.theme, sz=12, space=6)
        h1 = h2 = 0
        heads = [b for b in blocks if b["type"] == "heading"]
        n1 = sum(1 for b in heads if b["level"] == 1)
        n2 = sum(1 for b in heads if b["level"] == 2)
        # 一页目录约放 30 行（一级标题约占 1.6 行），放不下就只列一级标题，免得目录溢出到第二页
        max_level = 2 if n1 * 1.6 + n2 <= 30 else 1
        for b in blocks:
            if b["type"] != "heading" or b["level"] > max_level:
                continue
            if b["level"] == 1:
                h1 += 1
                h2 = 0
                p = d.add_paragraph()
                _spacing(p, before=8, after=2, line=1.3)
                if self.numbering:
                    _set_font(p.add_run(f"{h1:02d}   "), self.font, 13, True, self.theme)
                _set_font(p.add_run(b["text"]), self.font, 13, True, INK)
            else:
                h2 += 1
                p = d.add_paragraph()
                _spacing(p, after=0, line=1.3)
                p.paragraph_format.left_indent = Cm(1.25 if self.numbering else 0.6)
                label = f"{h1}.{h2}  {b['text']}" if self.numbering else b["text"]
                _set_font(p.add_run(label), self.font, 10.5, False, INK2)

    # 正文节：页眉页脚、页码从 1 开始
    def start_body(self):
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        sec.header.is_linked_to_previous = False
        sec.footer.is_linked_to_previous = False
        pg = OxmlElement("w:pgNumType")
        pg.set(qn("w:start"), "1")
        sec._sectPr.append(pg)
        hp = sec.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _set_font(hp.add_run(self.meta.get("title", "")), self.font, 8.5, False, MUTED)
        _p_border(hp, "bottom", LINE, sz=4, space=4)
        fp = sec.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = fp.add_run()
        _set_font(r, self.font, 9, False, MUTED)
        _field(r, "PAGE")
        # 封面和目录节不要页眉页脚
        first = self.doc.sections[0]
        first.header.is_linked_to_previous = False
        first.footer.is_linked_to_previous = False

    def _drop_trailing_spacers(self):
        """删掉正文末尾的空段落：它们被挤到下一页后，再遇到章节换页就会多出一张空白页。"""
        body = self.doc.element.body
        while True:
            kids = [k for k in body if k.tag != qn("w:sectPr")]
            last = kids[-1] if kids else None
            if last is None or last.tag != qn("w:p"):
                return
            if last.find(qn("w:pPr") + "/" + qn("w:sectPr")) is not None:
                return  # 节分隔段落不能删
            text = "".join(t.text or "" for t in last.iter(qn("w:t")))
            if text.strip() or last.find(".//" + qn("w:drawing")) is not None or last.find(".//" + qn("w:br")) is not None:
                return
            body.remove(last)

    def heading(self, level, text):
        d = self.doc
        if level == 1:
            self.h1 += 1
            self.h2 = 0
            self.fig = self.tab = 0
            new_page = not self.first_h1
            self.first_h1 = False
            if new_page:
                self._drop_trailing_spacers()
            if self.numbering:
                p = d.add_paragraph()
                _spacing(p, before=0, after=0, line=1.0)
                p.paragraph_format.page_break_before = new_page
                new_page = False
                _set_font(p.add_run(f"{self.h1:02d}"), self.font, 36, True, self.theme)
                _keep_with_next(p)
            p = d.add_paragraph(style="Heading 1")
            p.paragraph_format.page_break_before = new_page
            _spacing(p, before=2, after=16, line=1.2)
            _set_font(p.add_run(text), self.font, 20, True, INK)
            _p_border(p, "bottom", self.theme, sz=12, space=8)
        elif level == 2:
            self.h2 += 1
            p = d.add_paragraph(style="Heading 2")
            _spacing(p, before=14, after=6, line=1.3)
            _p_border(p, "left", self.theme, sz=24, space=8)
            label = f"{self.h1}.{self.h2}  {text}" if self.numbering else text
            _set_font(p.add_run(label), self.font, 14, True, self.theme)
        else:
            p = d.add_paragraph(style="Heading 3")
            _spacing(p, before=8, after=4, line=1.3)
            _set_font(p.add_run(text), self.font, 12, True, INK)

    def para(self, text):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _spacing(p, after=6, line=1.6)
        self._inline(p, text)

    def bullets(self, items):
        counters = {}
        for it in items:
            lvl = min(it["level"], 2)
            p = self.doc.add_paragraph()
            _spacing(p, after=3, line=1.5)
            pf = p.paragraph_format
            pf.left_indent = Cm(0.75 + 0.7 * lvl)
            pf.first_line_indent = Cm(-0.5)
            if it.get("ordered"):
                counters[lvl] = counters.get(lvl, 0) + 1
                for deeper in [k for k in counters if k > lvl]:
                    counters.pop(deeper)
                mark = f"{counters[lvl]}. "
                _set_font(p.add_run(mark), self.font, 10.5, True, self.theme)
            else:
                mark = "●  " if lvl == 0 else "○  "
                _set_font(p.add_run(mark), self.font, 7 if lvl == 0 else 8, False, self.theme)
            self._inline(p, it["text"])

    def table(self, rows, caption=None):
        if caption:
            self._caption("表", caption, before_obj=True)
        ncol = len(rows[0])
        t = self.doc.add_table(rows=len(rows), cols=ncol)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        _table_no_borders(t)
        light = _tint(self.theme, 0.92)
        widths = _col_widths(rows, CONTENT_W_CM)
        numeric_col = [ci > 0 and all(_is_num(r[ci]) for r in rows[1:] if r[ci].strip()) for ci in range(ncol)]
        for ci, col in enumerate(t.columns):
            col.width = Cm(widths[ci])  # 写 gridCol，LibreOffice 只认这个
        for ri, row in enumerate(rows):
            for ci, val in enumerate(row):
                c = t.rows[ri].cells[ci]
                c.width = Cm(widths[ci])
                c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                _cell_margins(c, 70, 70, 110, 110)
                if ri == 0:
                    _shade(c, self.theme)
                    _cell_borders(c, bottom=(self.theme, 4))
                else:
                    if ri % 2 == 0:
                        _shade(c, light)
                    _cell_borders(c, bottom=(LINE, 4))
                p = c.paragraphs[0]
                _spacing(p, after=0, line=1.25)
                if numeric_col[ci]:
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                if ri == 0:
                    self._inline(p, val, 9.5, "FFFFFF", True)
                else:
                    self._inline(p, val, 9.5, INK)
        # 表头行重复
        trpr = t.rows[0]._tr.get_or_add_trPr()
        th = OxmlElement("w:tblHeader")
        th.set(qn("w:val"), "true")
        trpr.append(th)
        sp = self.doc.add_paragraph()
        _spacing(sp, after=4, line=1.0)

    def callout(self, title, lines):
        t = self.doc.add_table(rows=1, cols=1)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        _table_no_borders(t)
        t.columns[0].width = Cm(CONTENT_W_CM)
        trpr = t.rows[0]._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")  # 提示框整块不跨页
        cant.set(qn("w:val"), "true")
        trpr.append(cant)
        c = t.rows[0].cells[0]
        c.width = Cm(CONTENT_W_CM)
        _shade(c, _tint(self.theme, 0.9))
        _cell_borders(c, left=(self.theme, 24))
        _cell_margins(c, 140, 140, 220, 220)
        p = c.paragraphs[0]
        _spacing(p, after=2, line=1.4)
        if title:
            _set_font(p.add_run(title), self.font, 11, True, self.theme)
            p = c.add_paragraph()
            _spacing(p, after=2, line=1.5)
        for i, ln in enumerate(lines):
            if i:
                p = c.add_paragraph()
                _spacing(p, after=2, line=1.5)
            self._inline(p, ln, 10.5, INK)
        sp = self.doc.add_paragraph()
        _spacing(sp, after=4, line=1.0)

    def _caption(self, kind, text, before_obj=False):
        if kind == "图":
            self.fig += 1
            num = self.fig
        else:
            self.tab += 1
            num = self.tab
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _spacing(p, before=2 if not before_obj else 6, after=10 if not before_obj else 4, line=1.2)
        label = f"{kind} {self.h1}-{num}  " if self.h1 else f"{kind} {num}  "
        _set_font(p.add_run(label), self.font, 9, True, self.theme)
        _set_font(p.add_run(text), self.font, 9, False, INK2)
        if before_obj:
            _keep_with_next(p)

    def image(self, path, caption=None, width_cm=None):
        if not os.path.exists(path):
            self.para(f"【缺图：{os.path.basename(path)}】")
            return
        w = min(width_cm or CONTENT_W_CM, CONTENT_W_CM)
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _spacing(p, before=6, after=2, line=1.0)
        _keep_with_next(p)
        p.add_run().add_picture(path, width=Cm(w))
        if caption:
            self._caption("图", caption)

    def code(self, text):
        p = self.doc.add_paragraph()
        _spacing(p, after=6, line=1.2)
        _set_font(p.add_run(text), "Consolas", 9, False, INK2)

    def pagebreak(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def save(self, out):
        self.doc.core_properties.title = self.meta.get("title", "")
        self.doc.core_properties.author = self.meta.get("author", "")
        self.doc.save(out)
        return out
