"""充电站 / 超充站投资收益测算：假设 JSON → 测算章节 Markdown（表格 + ```chart）+ 结论 JSON。

用法：
    python finance.py assumptions.json -o finance.md
然后在 proposal.md 里写一行 <!-- include: finance.md -->，build 时会把测算章节原样插进去。
改了假设就重跑 finance.py 再 build，正文里的数字、表、图会一起更新。

字段和默认值见 references/industry/supercharging-finance.md。金额单位：万元；电量：kWh；电价：元/kWh。
"""
import argparse
import copy
import json
import math
import os
import sys

DEFAULTS = {
    "name": "本站",
    "power_kw": 2400,            # 总装机
    "days": 365,
    "util": [0.06, 0.09, 0.12],  # 站级功率利用率，逐年爬坡，之后保持最后一个值
    "service_fee": 0.20,
    "markup": 0.0,               # 电费加价
    "kwh_subsidy": 0.0,          # 度电运营补贴
    "buy_price": 0.70,           # 购电均价
    "eff": 0.92,                 # 充电效率（线损）
    "channel_share": 0.30,       # 经聚合平台的电量占比
    "channel_rate": 0.20,        # 聚合平台抽佣（占服务费）
    "owner_share": 0.0,          # 场地方按服务费分成比例
    "invest": {"超充设备": 72, "电力接入与增容": 60, "土建与雨棚": 40, "平台、监控与其他": 18},
    "subsidy_build": 0.0,        # 一次性建设补贴（万元）
    "fixed": {"场地租金": 8, "人工与运维": 10, "设备维保": 1.8, "平台、保险与其他": 4},
    "storage_income": 0.0,       # 储能峰谷套利等年收益（万元）
    "years": 8,
    "salvage": 0.05,
    "discount": 0.08,
    "tax": 0.25,
    "lease_years": None,
    "target_payback": 7,
    "per_session_kwh": 30,
    "notes": {},                 # 参数依据：{"service_fee": "周边 3 座竞品实收均价（用户提供）"}
    "benchmarks": [
        {"name": "深圳会展中心全液冷站（推算）", "kwh": 3950},
        {"name": "中石化临汾尧庙站（开业四天日均）", "kwh": 7000},
        {"name": "深圳莲花山超充站（日均）", "kwh": 20000},
    ],
    "scenarios": {
        "悲观": {"util_scale": 0.67, "service_fee_delta": -0.05, "invest_scale": 1.2},
        "乐观": {"util_scale": 1.25, "service_fee_delta": 0.05, "invest_scale": 0.9},
    },
}

LABELS = {
    "power_kw": ("总装机", "kW"), "util": ("站级功率利用率（逐年）", "%"), "service_fee": ("服务费", "元/kWh"),
    "markup": ("电费加价", "元/kWh"), "kwh_subsidy": ("度电运营补贴", "元/kWh"), "buy_price": ("购电均价", "元/kWh"),
    "eff": ("充电效率", "%"), "channel_share": ("聚合平台电量占比", "%"), "channel_rate": ("聚合平台抽佣", "占服务费 %"),
    "owner_share": ("场地方服务费分成", "%"), "subsidy_build": ("一次性建设补贴", "万元"),
    "storage_income": ("储能等其他年收益", "万元/年"), "years": ("测算期", "年"), "salvage": ("残值率", "%"),
    "discount": ("折现率", "%"), "tax": ("所得税率", "%"), "lease_years": ("场地租期", "年"),
}
PCT = {"util", "eff", "channel_share", "channel_rate", "owner_share", "salvage", "discount", "tax"}


def margin(a):
    """度电净收益：服务费 + 加价 + 度电补贴 − 线损 − 渠道抽佣 − 场地分成。"""
    f = a["service_fee"]
    return (f + a["markup"] + a["kwh_subsidy"] - a["buy_price"] * (1 / a["eff"] - 1)
            - f * a["channel_share"] * a["channel_rate"] - f * a["owner_share"])


def run(a):
    inv = sum(a["invest"].values())
    net_inv = inv - a["subsidy_build"]
    fixed = sum(a["fixed"].values())
    dep = net_inv * (1 - a["salvage"]) / a["years"]
    m = margin(a)
    rows, cash = [], [-net_inv]
    for y in range(1, a["years"] + 1):
        u = a["util"][min(y - 1, len(a["util"]) - 1)]
        q = a["power_kw"] * 24 * u
        e = q * a["days"]
        gross = e * m / 1e4 + a["storage_income"]
        tax = max(0.0, gross - fixed - dep) * a["tax"]
        ncf = gross - fixed - tax
        if y == a["years"]:
            ncf += inv * a["salvage"]
        cash.append(ncf)
        rows.append({"year": y, "util": u, "q": q, "e": e, "gross": gross, "fixed": fixed, "tax": tax, "ncf": ncf})
    cum, acc = [], 0.0
    for c in cash:
        acc += c
        cum.append(acc)
    return {"invest": inv, "net_invest": net_inv, "fixed": fixed, "dep": dep, "m": m, "rows": rows,
            "cash": cash, "cum": cum, "payback": payback(cash, cash[-1] - inv * a["salvage"]), "npv": npv(cash, a["discount"]), "irr": irr(cash),
            "q_break": (fixed + dep) * 1e4 / (365 * m) if m > 0 else math.inf,
            "q_target": (net_inv / a["target_payback"] + fixed) * 1e4 / (365 * m) if m > 0 else math.inf}


def payback(cash, tail):
    """静态回收期；测算期内没回本就按最后一年现金流外推（最多 30 年），现金流不为正返回 inf。"""
    acc = cash[0]
    for t in range(1, 31):
        c = cash[t] if t < len(cash) else tail  # 外推用最后一年不含残值的现金流
        if c <= 0 and t >= len(cash):
            return math.inf
        if acc + c >= 0:
            return t - 1 + (-acc / c if c else 0)
        acc += c
    return math.inf


def npv(cash, r):
    return sum(c / (1 + r) ** t for t, c in enumerate(cash))


def irr(cash):
    lo, hi = -0.99, 1.0
    if npv(cash, lo) * npv(cash, hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(cash, lo) * npv(cash, mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def variant(a, util_scale=1.0, service_fee_delta=0.0, invest_scale=1.0, fixed_scale=1.0, **over):
    b = copy.deepcopy(a)
    b["util"] = [u * util_scale for u in b["util"]]
    b["service_fee"] = max(0.0, b["service_fee"] + service_fee_delta)
    b["invest"] = {k: v * invest_scale for k, v in b["invest"].items()}
    b["fixed"] = {k: v * fixed_scale for k, v in b["fixed"].items()}
    b.update(over)
    return b


def fy(v, nd=1):
    return "无法回本" if v is None or v == math.inf else f"{v:.{nd}f}"


def pct(v):
    return "—" if v is None else f"{v * 100:.1f}%"


def money(v):
    return f"{v:,.1f}"


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def chart(spec):
    return "```chart\n" + json.dumps(spec, ensure_ascii=False) + "\n```"


def param_value(k, v):
    if k == "util":
        return " → ".join(f"{u * 100:g}%" for u in v)
    if k in PCT:
        return f"{v * 100:g}%"
    return "—" if v is None else f"{v:g}"


def build_md(a, base, scen, sens, warnings):
    P = a["power_kw"]
    lines = []
    pb = base["payback"]
    util_break = base["q_break"] / (P * 24)
    util_target = base["q_target"] / (P * 24)
    steady = base["rows"][-1]
    lease = a["lease_years"]
    concl = [
        f"总投资 {money(base['invest'])} 万元"
        + (f"（扣除建设补贴后 {money(base['net_invest'])} 万元）" if a["subsidy_build"] else "")
        + f"，静态回收期 {fy(pb)} 年，FIRR {pct(base['irr'])}，FNPV（{a['discount'] * 100:g}%）{money(base['npv'])} 万元。",
        f"度电净收益 {base['m']:.3f} 元/kWh；保本日电量 {base['q_break']:,.0f} kWh（功率利用率 {util_break * 100:.1f}%），"
        f"{a['target_payback']} 年回本需要日电量 {base['q_target']:,.0f} kWh（利用率 {util_target * 100:.1f}%）。",
        f"稳定期日电量 {steady['q']:,.0f} kWh，约 {steady['q'] / a['per_session_kwh']:,.0f} 车次/日（按单次 {a['per_session_kwh']} kWh 推算）。",
    ]
    if lease:
        concl.append(f"场地租期 {lease} 年，" + ("覆盖回收期。" if pb <= lease else "**短于回收期，需要续租保障或改合作模式。**"))
    lines += ["## 测算结论", "", "> [!测算结论（推算，以下数字均由本章假设算出）]"] + [f"> {c}" for c in concl] + [""]

    lines += ["表：主要技术经济指标", "", table(["序号", "指标", "单位", "指标值", "备注"], [
        [1, "总装机", "kW", f"{P:,.0f}", ""],
        [2, "总投资", "万元", money(base["invest"]), "见投资构成"],
        [3, "一次性建设补贴", "万元", money(a["subsidy_build"]), "以当年当地申报文件为准" if a["subsidy_build"] else "未计入"],
        [4, "稳定期日电量", "kWh", f"{steady['q']:,.0f}", f"功率利用率 {steady['util'] * 100:g}%"],
        [5, "度电净收益", "元/kWh", f"{base['m']:.3f}", "扣线损、渠道抽佣、场地分成"],
        [6, "保本日电量", "kWh", f"{base['q_break']:,.0f}", f"利用率 {util_break * 100:.1f}%"],
        [7, "静态回收期", "年", fy(pb), "含建设期 0 年"],
        [8, "FIRR", "%", pct(base["irr"]), "税后"],
        [9, "FNPV", "万元", money(base["npv"]), f"折现率 {a['discount'] * 100:g}%"],
    ]), ""]

    inv_items = sorted(a["invest"].items(), key=lambda kv: -kv[1])
    lines += ["## 投资构成", "", chart({"type": "hbar", "categories": [k for k, _ in inv_items],
                                       "series": [{"name": "投资", "data": [round(v, 1) for _, v in inv_items]}],
                                       "unit": "万", "width": 13,
                                       "caption": f"总投资 {money(base['invest'])} 万元，{inv_items[0][0]}占比最高"}), ""]

    rows = []
    for k, (label, unit) in LABELS.items():
        if k not in a or (a[k] in (0, 0.0, None) and k not in ("service_fee",)):
            continue
        rows.append([label, param_value(k, a[k]), unit, a["notes"].get(k, "默认假设，待确认")])
    rows.append(["年固定成本", money(base["fixed"]), "万元/年",
                 a["notes"].get("fixed", "、".join(f"{k} {v:g}" for k, v in a["fixed"].items()))])
    lines += ["## 关键假设", "", "表：关键假设（依据写「默认假设，待确认」的项需要用户核实）", "",
              table(["参数", "取值", "单位", "依据"], rows), ""]

    yr = [[f"第 {r['year']} 年", f"{r['util'] * 100:g}%", f"{r['q']:,.0f}", f"{r['e'] / 1e4:,.1f}", money(r["gross"]),
           money(r["fixed"]), money(r["tax"]), money(r["ncf"]), money(base["cum"][r["year"]])] for r in base["rows"]]
    lines += ["## 分年测算", "", "表：分年收益测算（万元；电量为售电口径）", "",
              table(["年份", "利用率", "日电量 kWh", "年电量 万kWh", "毛利", "固定成本", "所得税", "净现金流", "累计现金流"], yr), ""]
    x = ["建设期"] + [f"第{r['year']}年" for r in base["rows"]]
    spec = {"type": "line", "x": x, "series": [{"name": "累计现金流", "data": [round(c, 1) for c in base["cum"]]}],
            "unit": "万", "hline": [{"value": 0, "label": "回本线"}],
            "caption": f"累计现金流在第 {math.ceil(pb)} 年转正" if pb != math.inf and pb <= a["years"] else
            f"测算期 {a['years']} 年内累计现金流未转正"}
    if pb != math.inf and pb <= a["years"]:
        spec["vline"] = [{"at": f"第{math.ceil(pb)}年", "label": f"回本 {pb:.1f} 年"}]
    lines += [chart(spec), ""]

    lines += ["## 情景与敏感性", "", "表：情景对比", "", table(["情景", "说明", "静态回收期（年）", "FIRR", "FNPV（万元）"],
              [[n, d, fy(r["payback"]), pct(r["irr"]), money(r["npv"])] for n, d, r in scen]), ""]
    cap = a["years"] * 2
    items, note = [], False
    for name, lo, hi in sens:
        lv, hv = lo["payback"], hi["payback"]
        if lv == math.inf or hv == math.inf:
            note = True
        items.append({"name": name, "low": round(min(lv, cap), 1), "high": round(min(hv, cap), 1)})
    top = max(items, key=lambda it: abs(it["high"] - it["low"]))
    lines += [chart({"type": "tornado", "base": round(pb, 1) if pb != math.inf else cap, "unit": " 年",
                     "lower_is_better": True, "items": items,
                     "caption": f"回收期对「{top['name']}」最敏感" + (f"（超过 {cap} 年的按 {cap} 年画）" if note else "")}), ""]

    bm = sorted(a["benchmarks"], key=lambda b: b["kwh"])
    cats = [b["name"] for b in bm] + [f"{a['name']} {a['target_payback']} 年回本所需"]
    lines += [chart({"type": "hbar", "categories": cats, "series": [{"name": "日电量", "data": [b["kwh"] for b in bm] + [round(base["q_target"])]}],
                     "unit": " kWh", "highlight": cats[-1],
                     "caption": "回本所需日电量与可核实站点对比（对比站点规模不同，仅作量级参考）"}), ""]
    if warnings:
        lines += ["> [!风险提示]"] + [f"> {w}" for w in warnings] + [""]
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="充电站投资收益测算 → 测算章节 Markdown")
    ap.add_argument("json")
    ap.add_argument("-o", "--out", help="输出 Markdown，默认与 json 同目录的 finance.md")
    ap.add_argument("--print-defaults", action="store_true", help="打印全部字段和默认值")
    a_ = ap.parse_args()
    if a_.print_defaults:
        print(json.dumps(DEFAULTS, ensure_ascii=False, indent=2))
        return
    with open(a_.json, encoding="utf-8") as f:
        user = json.load(f)
    a = copy.deepcopy(DEFAULTS)
    a.update(user)
    base = run(a)

    nosub = variant(a, subsidy_build=0.0, kwh_subsidy=0.0)
    scen = [("基准", "本章假设", base)]
    if a["subsidy_build"] or a["kwh_subsidy"]:
        scen.append(("无补贴", "去掉建设补贴和度电补贴", run(nosub)))
    for n, ov in a["scenarios"].items():
        desc = []
        if ov.get("util_scale", 1) != 1:
            desc.append(f"利用率 ×{ov['util_scale']:g}")
        if ov.get("service_fee_delta"):
            desc.append(f"服务费 {ov['service_fee_delta']:+g} 元")
        if ov.get("invest_scale", 1) != 1:
            desc.append(f"投资 ×{ov['invest_scale']:g}")
        scen.append((n, "，".join(desc) or "自定", run(variant(a, **ov))))

    sens = [
        ("日电量 ±30%", run(variant(a, util_scale=0.7)), run(variant(a, util_scale=1.3))),
        ("服务费 ±0.1 元", run(variant(a, service_fee_delta=-0.1)), run(variant(a, service_fee_delta=0.1))),
        ("总投资 ±20%", run(variant(a, invest_scale=1.2)), run(variant(a, invest_scale=0.8))),
        ("固定成本 ±20%", run(variant(a, fixed_scale=1.2)), run(variant(a, fixed_scale=0.8))),
        ("购电价 ±0.1 元", run(variant(a, buy_price=a["buy_price"] + 0.1)), run(variant(a, buy_price=a["buy_price"] - 0.1))),
    ]
    if a["subsidy_build"]:
        sens.append(("建设补贴 无 / 有", run(variant(a, subsidy_build=0.0)), base))

    warnings = []
    pb = base["payback"]
    if base["m"] <= 0:
        warnings.append("度电净收益 ≤ 0：服务费不足以覆盖线损和渠道抽佣，按当前定价项目不成立。")
    if pb == math.inf or pb > a["years"]:
        warnings.append(f"测算期 {a['years']} 年内无法回本。")
    if a["lease_years"] and pb > a["lease_years"]:
        warnings.append(f"回收期 {fy(pb)} 年超过场地租期 {a['lease_years']} 年，需要续租条款或改为分成 / 共建模式。")
    top_bm = max((b["kwh"] for b in a["benchmarks"]), default=0)
    if top_bm and base["q_target"] > top_bm:
        warnings.append("目标回本日电量超过可核实的同类站点水平，回本依赖超出可比站点的流量假设。")
    if (a["subsidy_build"] or a["kwh_subsidy"]) and run(nosub)["payback"] > a["years"]:
        warnings.append("无补贴情景下测算期内无法回本，项目对补贴依赖大。")
    for n, _, r in scen:
        if n == "悲观" and (r["payback"] == math.inf or r["payback"] > a["years"]):
            warnings.append(f"悲观情景下测算期内无法回本（回收期 {fy(r['payback'])} 年），项目对利用率爬坡依赖较大。")
    defaults_used = [LABELS[k][0] for k in ("service_fee", "buy_price", "util") if k not in user]
    need_input = ["以下参数用的是默认值，需要用户提供本地数据：" + "、".join(defaults_used)] if defaults_used else []

    out = a_.out or os.path.join(os.path.dirname(os.path.abspath(a_.json)), "finance.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_md(a, base, scen, sens, warnings) + "\n")
    summary = {"out": out, "invest": round(base["invest"], 1), "payback_years": None if pb == math.inf else round(pb, 2),
               "firr": None if base["irr"] is None else round(base["irr"], 4), "fnpv": round(base["npv"], 1),
               "margin_per_kwh": round(base["m"], 4), "break_even_kwh_per_day": round(base["q_break"]),
               "target_kwh_per_day": round(base["q_target"]),
               "scenarios": {n: fy(r["payback"]) for n, _, r in scen}, "warnings": warnings, "need_input": need_input}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
