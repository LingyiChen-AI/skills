"""把 ```chart JSON 规格画成 PNG。支持 gantt / bar / hbar / donut / line / funnel / tornado / radar。

规格字段见 references/charts.md。配色按固定顺序取色（不循环、不按排名变色），
数值直接标在图上，网格线尽量少。
"""
import datetime as dt
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

# dataviz 默认色板（已过色盲校验），按顺序分配给类别
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
ACTIVE = list(PALETTE)  # 当前文档用的色板：主色排第一，其余按固定顺序跟上


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def set_theme(theme):
    """主色作为第 1 个类别色，让图和文档同色系；色板里和主色太接近的颜色去掉，避免两类分不清。"""
    global ACTIVE
    if not theme:
        ACTIVE = list(PALETTE)
        return
    t = _rgb(theme)
    rest = [c for c in PALETTE if sum((a - b) ** 2 for a, b in zip(_rgb(c), t)) ** 0.5 > 110]
    ACTIVE = ["#" + theme.lstrip("#")] + rest


INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e6e5e1"

CJK_FONTS = ["Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC",
             "WenQuanYi Micro Hei", "SimHei", "Heiti SC", "Arial Unicode MS"]


def _setup_font():
    have = {f.name for f in font_manager.fontManager.ttflist}
    for name in CJK_FONTS:
        if name in have:
            plt.rcParams["font.family"] = [name]
            break
    else:
        print("[charts] 警告：没找到中文字体，图里的中文可能显示成方块。可装 Noto Sans CJK / 思源黑体。")
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 11


_setup_font()


def _fmt(v, unit=""):
    if not unit and abs(v) >= 1e8:
        return f"{v / 1e8:.4g} 亿"
    if not unit and abs(v) >= 1e4:
        return f"{v / 1e4:.4g} 万"
    if isinstance(v, float) and not v.is_integer():
        s = f"{v:,.1f}"
    else:
        s = f"{int(v):,}"
    return s + unit


def _clean_axes(ax, keep_left=True):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_visible(keep_left)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, length=0)


def _title(ax, spec):
    if spec.get("title"):
        ax.set_title(spec["title"], loc="left", fontsize=13, fontweight="bold", color=INK, pad=14)


def _legend(fig, ax, n):
    if n >= 2:
        ax.legend(loc="upper left", bbox_to_anchor=(0, 1.02, 1, 0.1), ncol=min(n, 5), frameon=False,
                  fontsize=10, labelcolor=INK2, borderaxespad=0, mode=None)


def _parse_date(s):
    return dt.datetime.strptime(str(s)[:10], "%Y-%m-%d")


def gantt(spec):
    tasks = spec["tasks"]
    groups = []
    for t in tasks:
        g = t.get("group", "")
        if g not in groups:
            groups.append(g)
    color_of = {g: ACTIVE[i % len(ACTIVE)] for i, g in enumerate(groups)}
    h = max(2.4, 0.36 * len(tasks) + 1.0)
    fig, ax = plt.subplots(figsize=(7.2, h))
    for idx, t in enumerate(tasks):
        s, e = _parse_date(t["start"]), _parse_date(t["end"])
        ax.barh(idx, (e - s).days + 1, left=s, height=0.56, color=color_of[t.get("group", "")], edgecolor="white", linewidth=1)
        ax.text(e + dt.timedelta(days=0.6), idx, f"{s:%m/%d}–{e:%m/%d}", va="center", fontsize=9, color=INK2)
    for m in spec.get("milestones", []):
        d = _parse_date(m["date"])
        ax.axvline(d, color="#d03b3b", lw=1.2, ls="--")
        ax.text(d, -0.75, "◆ " + m["name"], color="#d03b3b", fontsize=9, ha="center", va="bottom")
    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels([t["name"] for t in tasks], color=INK)
    # 上方留出里程碑文字的位置（y 轴倒置：上边界是负数）
    ax.set_ylim(len(tasks) - 0.5, -1.0 if spec.get("milestones") else -0.6)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    _clean_axes(ax, keep_left=False)
    if len(groups) >= 2 or (groups and groups[0]):
        from matplotlib.patches import Patch
        handles = [Patch(color=color_of[g], label=g) for g in groups if g]
        # 图例放在图下方，避免和顶部的里程碑文字打架
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, -0.08), ncol=min(len(handles), 6), frameon=False, fontsize=10)
    _title(ax, spec)
    return fig


def _bar_like(spec, horizontal):
    cats = spec["categories"]
    series = spec["series"]
    unit = spec.get("unit", "")
    stacked = spec.get("stacked", False)
    k = len(series)
    if horizontal:
        fig, ax = plt.subplots(figsize=(7.2, max(2.2, 0.4 * len(cats) * (1 if stacked else max(1, k * 0.7)) + 1.2)))
    else:
        fig, ax = plt.subplots(figsize=(7.2, 3.4))
    width = 0.7 if stacked or k == 1 else 0.8 / k
    base = [0.0] * len(cats)
    for si, s in enumerate(series):
        color = ACTIVE[si % len(ACTIVE)]
        hl = spec.get("highlight")
        if hl and k == 1:  # 单系列可突出一项：被强调的用主色，其余灰
            color = [ACTIVE[0] if c == hl else "#c3c2b7" for c in cats]
        data = s["data"]
        if stacked:
            pos = list(range(len(cats)))
        else:
            off = (si - (k - 1) / 2) * width
            pos = [p + off for p in range(len(cats))]
        if horizontal:
            bars = ax.barh(pos, data, height=width, left=base if stacked else None, color=color, label=s.get("name", ""),
                           edgecolor="white", linewidth=1.5)
        else:
            bars = ax.bar(pos, data, width=width, bottom=base if stacked else None, color=color, label=s.get("name", ""),
                          edgecolor="white", linewidth=1.5)
        if not stacked:
            for b, v in zip(bars, data):
                if horizontal:
                    ax.text(b.get_width(), b.get_y() + b.get_height() / 2, " " + _fmt(v, unit), va="center", fontsize=9.5, color=INK)
                else:
                    ax.text(b.get_x() + b.get_width() / 2, b.get_height(), _fmt(v, unit), ha="center", va="bottom", fontsize=9.5, color=INK)
        if stacked:
            base = [a + b for a, b in zip(base, data)]
    if stacked:
        for p, total in enumerate(base):
            if horizontal:
                ax.text(total, p, " " + _fmt(total, unit), va="center", fontsize=9.5, color=INK, fontweight="bold")
            else:
                ax.text(p, total, _fmt(total, unit), ha="center", va="bottom", fontsize=9.5, color=INK, fontweight="bold")
    if horizontal:
        ax.set_yticks(range(len(cats)))
        ax.set_yticklabels(cats, color=INK)
        ax.invert_yaxis()
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        ax.margins(x=0.12)
    else:
        ax.set_xticks(range(len(cats)))
        ax.set_xticklabels(cats, color=INK)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.margins(y=0.15)
        _ref_lines(ax, spec, cats, unit)
    _clean_axes(ax, keep_left=horizontal)
    _legend(fig, ax, k)
    _title(ax, spec)
    return fig


def donut(spec):
    items = spec["items"]
    unit = spec.get("unit", "")
    vals = [it["value"] for it in items]
    total = sum(vals)
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    colors = [ACTIVE[i % len(ACTIVE)] for i in range(len(items))]
    wedges, _ = ax.pie(vals, colors=colors, startangle=90, counterclock=False,
                       wedgeprops={"width": 0.36, "edgecolor": "white", "linewidth": 2})
    ax.text(0, 0.08, _fmt(total, unit), ha="center", va="center", fontsize=17, fontweight="bold", color=INK)
    ax.text(0, -0.16, spec.get("center_label", "合计"), ha="center", va="center", fontsize=10, color=INK2)
    labels = [f"{it['name']}  {_fmt(it['value'], unit)}（{it['value'] / total * 100:.1f}%）" for it in items]
    ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False, fontsize=10.5, labelcolor=INK)
    ax.set_aspect("equal")
    _title(ax, spec)
    return fig


def line(spec):
    x = spec["x"]
    unit = spec.get("unit", "")
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    for si, s in enumerate(spec["series"][:5]):
        color = ACTIVE[si % len(ACTIVE)]
        ax.plot(range(len(x)), s["data"], color=color, lw=2, marker="o", ms=5, label=s.get("name", ""))
        ax.text(len(x) - 1 + 0.08, s["data"][-1], _fmt(s["data"][-1], unit), color=INK, fontsize=9.5, va="center")
    ax.set_xticks(range(len(x)))
    ax.set_xticklabels(x, color=INK)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    _clean_axes(ax, keep_left=False)
    ax.margins(x=0.06)
    _ref_lines(ax, spec, x, unit)
    _legend(fig, ax, len(spec["series"]))
    _title(ax, spec)
    return fig


def _ref_lines(ax, spec, x, unit):
    """参考线：hline 横线（如累计现金流 0 线、盈亏利用率），vline 竖线（如回本年，at 写 x 里的标签）。"""
    for h in spec.get("hline", []):
        ax.axhline(h["value"], color=INK2, lw=1, ls="--")
        ax.text(len(x) - 1, h["value"], h.get("label", _fmt(h["value"], unit)) + " ", color=INK2, fontsize=9,
                ha="right", va="bottom")
    for v in spec.get("vline", []):
        if v["at"] not in x:
            continue
        i = x.index(v["at"])
        ax.axvline(i, color="#d03b3b", lw=1.2, ls="--")
        ax.text(i, ax.get_ylim()[1], " ◆ " + v.get("label", ""), color="#d03b3b", fontsize=9, ha="left", va="top")


def tornado(spec):
    """敏感性龙卷风图：每个变量一行，左边是不利情景、右边是有利情景对指标的影响，中线是基准值。
    items: [{"name":"日电量 ±30%","low":7.9,"high":4.6}]，base: 基准值，unit: 单位（如 "年"）。
    按影响幅度从大到小自动排序；lower_is_better=true（回本年数）时数值小的一侧算有利。"""
    base = spec["base"]
    unit = spec.get("unit", "")
    items = sorted(spec["items"], key=lambda it: abs(it["high"] - it["low"]), reverse=True)
    lib = spec.get("lower_is_better", False)
    good, bad = ACTIVE[0], "#c3c2b7"
    fig, ax = plt.subplots(figsize=(7.2, max(2.2, 0.48 * len(items) + 1.0)))
    for i, it in enumerate(items):
        for v in (it["low"], it["high"]):
            favorable = (v < base) if lib else (v > base)
            ax.barh(i, v - base, left=base, height=0.6, color=good if favorable else bad, edgecolor="white", linewidth=1.5)
            ax.text(v, i, (" " if v >= base else "") + _fmt(v, unit) + (" " if v < base else ""), va="center",
                    ha="left" if v >= base else "right", fontsize=9.5, color=INK)
    ax.axvline(base, color=INK, lw=1)
    ax.set_yticks(range(len(items)))
    ax.set_yticklabels([it["name"] for it in items], color=INK)
    ax.set_ylim(len(items) - 0.5, -0.9)
    ax.text(base, -0.75, f"基准 {_fmt(base, unit)}", ha="center", va="center", fontsize=9.5, color=INK2,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5})
    ax.set_xticks([])
    ax.margins(x=0.18)
    _clean_axes(ax, keep_left=False)
    ax.spines["bottom"].set_visible(False)
    _title(ax, spec)
    return fig


def radar(spec):
    """雷达图：候选点 / 方案多维打分对比。axes: 维度名，series: [{"name","data"}]，max: 满分（默认 10）。最多 3 个系列。"""
    import math

    axes_names = spec["axes"]
    n = len(axes_names)
    top = spec.get("max", 10)
    ang = [2 * math.pi * i / n for i in range(n)] + [0]
    fig = plt.figure(figsize=(7.2, 3.6))
    ax = fig.add_subplot(111, polar=True)
    ax.set_theta_offset(math.pi / 2)
    ax.set_theta_direction(-1)
    for si, s in enumerate(spec["series"][:3]):
        d = list(s["data"]) + [s["data"][0]]
        c = ACTIVE[si % len(ACTIVE)]
        ax.plot(ang, d, color=c, lw=2, label=f"{s['name']}（{sum(s['data']):g}）")
        ax.fill(ang, d, color=c, alpha=0.12)
    ax.set_xticks(ang[:-1])
    ax.set_xticklabels(axes_names, color=INK, fontsize=10)
    ax.set_ylim(0, top)
    ax.set_yticks([top * k / 4 for k in range(1, 5)])
    ax.set_yticklabels([])
    ax.grid(color=GRID)
    ax.spines["polar"].set_color(GRID)
    if len(spec["series"]) >= 2:
        ax.legend(loc="upper left", bbox_to_anchor=(1.08, 1.0), frameon=False, fontsize=10, labelcolor=INK2)
    _title(ax, spec)
    return fig


def funnel(spec):
    """层宽按层级等步递减（不按数值，否则后几层细到看不见），数值和转化率标在右侧。"""
    items = spec["items"]
    unit = spec.get("unit", "")
    n = len(items)
    fig, ax = plt.subplots(figsize=(7.2, max(2.2, 0.5 * n + 0.6)))
    for i, it in enumerate(items):
        w = 1 - i * (0.62 / max(1, n - 1))
        ax.barh(i, w, left=(1 - w) / 2, height=0.78, color=ACTIVE[0], alpha=1 - i * (0.5 / max(1, n - 1)),
                edgecolor="white", linewidth=2)
        ax.text(0.5, i, it["name"], ha="center", va="center", fontsize=10.5, color="white", fontweight="bold")
        rate = "" if i == 0 else f"   转化率 {it['value'] / items[i - 1]['value'] * 100:.1f}%"
        ax.text(1.04, i, _fmt(it["value"], unit), va="center", fontsize=11, color=INK, fontweight="bold")
        ax.text(1.24, i, rate, va="center", fontsize=9.5, color=INK2)
    ax.set_xlim(0, 1.6)
    ax.set_ylim(n - 0.5, -0.5)
    ax.axis("off")
    _title(ax, spec)
    return fig


RENDERERS = {"gantt": gantt, "bar": lambda s: _bar_like(s, False), "hbar": lambda s: _bar_like(s, True),
             "donut": donut, "pie": donut, "line": line, "funnel": funnel, "tornado": tornado, "radar": radar}


def render(spec, out_path, theme=None):
    set_theme(theme)
    kind = spec.get("type")
    if kind not in RENDERERS:
        raise ValueError(f"不支持的图表类型 {kind!r}，可选：{', '.join(RENDERERS)}")
    fig = RENDERERS[kind](spec)
    fig.patch.set_facecolor("white")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    return out_path
