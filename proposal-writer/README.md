# proposal-writer

一句话需求 → 带配图、统计图、排好版的企划书（Word + PDF）。
支持活动企划、营销方案、新品上市、通用企划；带**超充站 / 充电站行业包**（建站可研、补贴申报、场地合作提案、开业活动、年度运营营销，含投资收益测算）。
设计目标是放进千问办公「技能扩展」，经「IM 频道 · 飞书」在飞书里 @ 机器人出稿，也可以在 Claude Code 等 Agent 里直接用。

## 依赖

- Python 3.9+：`pip install -r scripts/requirements.txt`（python-docx、matplotlib、pillow、pymupdf）
- LibreOffice（`soffice`）：转 PDF 用，没有就只出 docx
- 中文字体：微软雅黑 / 思源黑体 / Noto Sans CJK 任一

## 命令

```bash
python scripts/build.py --check                      # 检查环境
python scripts/build.py 工作目录/proposal.md --list-images   # 列出要生成的配图（提示词、比例、存放路径）
python scripts/images.py save <图片链接或文件> <save_to>     # 把生图结果存到指定路径
python scripts/finance.py 工作目录/assumptions.json          # 充电站投资收益测算 → finance.md
python scripts/build.py 工作目录/proposal.md                 # 出 docx + pdf
python scripts/preview.py 工作目录/xxx.pdf                    # 页面总览 + 空白页 / 孤页检测
```

- 配图由运行 skill 的 Agent 用自带生图能力生成，脚本不调生图接口、不需要 API key；缺图时自动放占位图。
- 正文里 `<!-- include: finance.md -->` 会插入测算章节，改假设重跑 `finance.py` 再 build 即可更新。

## 目录

```
proposal-writer/
├── SKILL.md                  流程路由（8 步）
├── references/
│   ├── workflow.md           需求理解、提问规则、出稿 / 自检 / 交付
│   ├── outlines.md           四类通用大纲
│   ├── source-format.md      proposal.md 语法（frontmatter、```chart、```image、include）
│   ├── charts.md             统计图：gantt / donut / bar / hbar / line / funnel / tornado / radar
│   ├── visuals.md            配图规划、生图提示词、主色
│   ├── writing-rules.md      写作要求与禁用套话
│   ├── qa-checklist.md       交付前检查表
│   └── industry/             行业包
│       ├── supercharging.md          超充站：场景判断、输入体检、五类大纲、写作禁区、配图
│       ├── supercharging-data.md     行业数据（带出处、A/B/C 可靠性分级，2026-11）
│       └── supercharging-finance.md  测算公式、默认假设、finance.py 用法
├── scripts/                  build / mdparse / render_docx / charts / finance / images / preview
└── assets/
    ├── example/              发布会企划书样例
    └── example-supercharge/  超充站建站可研样例（proposal.md + assumptions.json + finance.md）
```

## 说明

- 行业数据来自 2026-11 的公开资料调研，每条带出处和时点；标 C 级的只能写进背景，不进测算。
  服务费 0.5 元上限、2026 年储能价格、各地现行超充补贴尚未核实到官方原文，补贴默认不计入测算。
- 加新行业：照 `references/industry/supercharging*.md` 的结构加一组行业包，在 `workflow.md` 的类型表里登记。
- 样例中的站点、公司、地址均为虚构。
