"""把设计需求单 brief.md 渲染成 docx，版式照润杰的「宣传页设计.docx」：

A4 单栏、无封面无目录；标题 18pt 加粗 → 头部信息（尺寸 / 视觉基调 ……）→ 分区文案。
正文分两种文字，排版上区分开：
  - 文案（要印到画面上的字）：黑色，大标题 18pt 加粗，正文 12pt，**加粗** = 要突出的关键词；
  - 设计说明（只给设计师看）：蓝色加粗、带「设计说明：」前缀；配图要求带「配图：」前缀；缺的信息红色。
语法见 references/brief/format.md。
"""
import os
import re

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from render_docx import _cell_margins, _col_widths, _set_font, _shade, _spacing, _style_font

INK = "1F1F1F"
NOTE = "1F4FA8"      # 设计说明
PIC = "2F6B3A"       # 配图要求
TODO = "D0101B"      # 待补
GRAY = "6B6B6B"
GRID = "BFBFBF"
PAGE_W_CM = 21.0
MARGIN_CM = 2.2
CONTENT_W_CM = PAGE_W_CM - 2 * MARGIN_CM

HEADER_FIELDS = [
    ("size", "尺寸"), ("material", "材质 / 工艺"), ("quantity", "数量"), ("tone", "视觉基调"),
    ("reference", "参考"), ("deliver", "交付"), ("deadline", "时间"),
]
CALLOUT_KIND = {
    "设计": ("设计说明：", NOTE), "设计说明": ("设计说明：", NOTE), "": ("设计说明：", NOTE),
    "配图": ("配图：", PIC), "待补": ("待补：", TODO), "注意": ("注意：", TODO), "备注": ("备注：", GRAY),
}
INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|【待补[:：][^】]*】|【[^】]*】)")


def _tbl_grid(table, color=GRID):
    tblpr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), color)
        borders.append(el)
    tblpr.append(borders)


def _tbl_none(table):
    tblpr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tblpr.append(borders)


class BriefRenderer:
    def __init__(self, meta, base_dir):
        self.meta = meta
        self.base = base_dir
        self.font = meta.get("font", "Microsoft YaHei")
        self.doc = Document()
        st = self.doc.styles
        _style_font(st["Normal"], self.font, 12, color=INK)
        st["Normal"].paragraph_format.line_spacing = 1.35
        st["Normal"].paragraph_format.space_after = Pt(4)
        sec = self.doc.sections[0]
        sec.page_width, sec.page_height = Cm(21), Cm(29.7)
        for side in ("left_margin", "right_margin"):
            setattr(sec, side, Cm(MARGIN_CM))
        sec.top_margin = Cm(2.2)
        sec.bottom_margin = Cm(2.0)
        self.todos = []

    # 行内：**关键词** 加粗；【待补：x】红色加粗；其他【…】灰底提示（如【留白：手填号码】）
    def _inline(self, p, text, size=12, color=INK, bold=False):
        for part in INLINE_RE.split(text):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                _set_font(p.add_run(part[2:-2]), self.font, size, True, color)
            elif part.startswith("【待补"):
                self.todos.append(part[1:-1].split("：", 1)[-1].split(":", 1)[-1])
                _set_font(p.add_run(part), self.font, size, True, TODO)
            elif part.startswith("【") and part.endswith("】"):
                r = p.add_run(part)
                _set_font(r, self.font, size, bold, GRAY)
                rpr = r._element.get_or_add_rPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), "EDEDED")
                rpr.append(shd)
            else:
                _set_font(p.add_run(part), self.font, size, bold, color)

    def header(self):
        m = self.meta
        p = self.doc.add_paragraph()
        _spacing(p, after=10, line=1.3)
        self._inline(p, m.get("title", "设计需求单"), 18, INK, True)
        for key, label in HEADER_FIELDS:
            v = m.get(key)
            if key == "deliver" and not v:
                v = "源文件 + JPG"
            if not v:
                continue
            p = self.doc.add_paragraph()
            _spacing(p, after=2, line=1.35)
            _set_font(p.add_run(label + "："), self.font, 12, True, INK)
            self._inline(p, v, 12)
        who = " → ".join(x for x in (m.get("from"), m.get("to")) if x)
        if who or m.get("date"):
            p = self.doc.add_paragraph()
            _spacing(p, before=2, after=8, line=1.2)
            txt = "　".join(x for x in (f"需求方 → 设计方：{who}" if who else "", f"日期：{m['date']}" if m.get("date") else "") if x)
            _set_font(p.add_run(txt), self.font, 10, False, GRAY)

    def heading(self, level, text):
        p = self.doc.add_paragraph()
        p.paragraph_format.keep_with_next = True
        if level == 1:
            _spacing(p, before=12, after=4, line=1.3)
            if not text.endswith(("：", ":")):
                text += "："
            self._inline(p, text, 14, INK, True)
        elif level == 2:
            _spacing(p, before=8, after=2, line=1.3)
            self._inline(p, text, 14, INK, True)
        else:
            _spacing(p, before=6, after=2, line=1.3)
            self._inline(p, text, 12, INK, True)

    def para(self, text):
        p = self.doc.add_paragraph()
        if text.startswith("!!"):
            _spacing(p, before=2, after=2, line=1.25)
            self._inline(p, text[2:].strip(), 18, INK, True)
        else:
            _spacing(p, after=4, line=1.35)
            self._inline(p, text, 12)

    def bullets(self, items):
        n = {}
        for it in items:
            lvl = min(it["level"], 2)
            p = self.doc.add_paragraph()
            _spacing(p, after=2, line=1.35)
            p.paragraph_format.left_indent = Cm(0.7 * lvl)
            if it.get("ordered"):
                n[lvl] = n.get(lvl, 0) + 1
                for k in [k for k in n if k > lvl]:
                    n.pop(k)
                mark = f"{n[lvl]}、"
            else:
                mark = "· "
            _set_font(p.add_run(mark), self.font, 12, False, INK)
            self._inline(p, it["text"], 12)

    def table(self, rows):
        ncol = len(rows[0])
        t = self.doc.add_table(rows=len(rows), cols=ncol)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        _tbl_grid(t)
        widths = _col_widths(rows, CONTENT_W_CM)
        for ci, col in enumerate(t.columns):
            col.width = Cm(widths[ci])
        for ri, row in enumerate(rows):
            for ci, val in enumerate(row):
                c = t.rows[ri].cells[ci]
                c.width = Cm(widths[ci])
                c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                _cell_margins(c, 60, 60, 100, 100)
                if ri == 0:
                    _shade(c, "F2F2F2")
                p = c.paragraphs[0]
                _spacing(p, after=0, line=1.2)
                self._inline(p, val, 10.5, INK, ri == 0)
        sp = self.doc.add_paragraph()
        _spacing(sp, after=2, line=1.0)

    def callout(self, title, lines):
        prefix, color = CALLOUT_KIND.get(title.strip(), (title.strip() + "：", NOTE))
        for i, ln in enumerate(lines or [""]):
            p = self.doc.add_paragraph()
            _spacing(p, before=2, after=3, line=1.35)
            if i == 0:
                _set_font(p.add_run(prefix), self.font, 11, True, color)
            else:
                p.paragraph_format.left_indent = Cm(0.4)
            self._inline(p, ln, 11, color, True)
            if title.strip() == "待补":
                self.todos.append(ln)

    def images(self, items):
        """items: [(path, label, width_cm)]。多张且总宽放得下时并排（如联名 logo），否则逐张居中。"""
        total = sum(w or CONTENT_W_CM for _, _, w in items)
        if len(items) > 1 and total <= CONTENT_W_CM:
            t = self.doc.add_table(rows=1, cols=len(items))
            t.alignment = WD_TABLE_ALIGNMENT.CENTER
            _tbl_none(t)
            trpr = t.rows[0]._tr.get_or_add_trPr()
            cant = OxmlElement("w:cantSplit")  # 图注和图不跨页
            cant.set(qn("w:val"), "true")
            trpr.append(cant)
            cw = CONTENT_W_CM / len(items)
            for ci, (path, label, w) in enumerate(items):
                cell = t.rows[0].cells[ci]
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
                lab = cell.paragraphs[0]
                _spacing(lab, after=2, line=1.2)
                _set_font(lab.add_run((label + "：") if label else ""), self.font, 9, False, GRAY)
                p = cell.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                self._pic(p, path, min(w or cw, cw - 0.3))
            sp = self.doc.add_paragraph()
            _spacing(sp, after=2, line=1.0)
            return
        for path, label, w in items:
            if label:
                lp = self.doc.add_paragraph()
                _spacing(lp, before=4, after=0, line=1.2)
                lp.paragraph_format.keep_with_next = True
                _set_font(lp.add_run(label + "："), self.font, 9, False, GRAY)
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _spacing(p, before=2, after=6, line=1.0)
            self._pic(p, path, min(w or 12, CONTENT_W_CM))

    def _pic(self, p, path, w):
        if not path or not os.path.exists(path):
            _set_font(p.add_run(f"【缺图：{os.path.basename(path or '')}】"), self.font, 10, True, TODO)
            return
        p.add_run().add_picture(path, width=Cm(w))

    def save(self, out):
        self.doc.core_properties.title = self.meta.get("title", "")
        self.doc.core_properties.author = self.meta.get("from", "")
        self.doc.save(out)
        return out
