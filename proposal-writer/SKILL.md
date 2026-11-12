---
name: proposal-writer
description: 写完整的企划书 / 策划案 / 活动方案 / 营销方案 / 新品上市方案，带配图和统计图，排版成 Word（docx）和 PDF 交付。用户说「出一份 XX 企划书」「写个活动策划」「做个营销方案 / 推广方案 / 发布会方案」「策划案要 Word / PDF」时使用；超充站 / 充电站的建站可研、补贴申报、场地合作提案、开业活动、年度运营方案也用它（带投资收益测算）。
---

# 企划书（proposal-writer）

一句需求进来，交付一份**排好版、带图**的企划书文件（PDF + Word）。

## 流程（按顺序做，每步细则见对应文件）

1. **理解需求**：判断企划类型，补齐关键信息；信息不全时带着假设往下做，不要反复追问
   → [references/workflow.md](references/workflow.md)
   **超充站 / 充电站**相关的需求，先读行业包 → [references/industry/supercharging.md](references/industry/supercharging.md)
   （场景判断、输入体检、专用大纲、行业数据、写作禁区）
2. **定大纲**：按类型选章节模板，删掉用不上的章节
   → [references/outlines.md](references/outlines.md)（有行业包时用行业包的大纲）
   - 要算投资回报的（建站可研、场地合作、年度目标）：写 `assumptions.json`，跑 `python <skill_dir>/scripts/finance.py assumptions.json`，
     正文用 `<!-- include: finance.md -->` 插入测算章节 → [references/industry/supercharging-finance.md](references/industry/supercharging-finance.md)
3. **写正文**：写成 `proposal.md`，语法见 [references/source-format.md](references/source-format.md)，
   写作要求见 [references/writing-rules.md](references/writing-rules.md)
4. **规划配图**：逐章判断配什么图。数据类用 ```chart 块（脚本自动画），
   场景类、视觉类用 ```image 块 → [references/visuals.md](references/visuals.md)、[references/charts.md](references/charts.md)
5. **生图（必须在排版之前做完）**：`python <skill_dir>/scripts/build.py proposal.md --list-images` 列出要画的图，
   然后**用你自己的生图能力**（千问办公里是「生图任务」）按每张的 `prompt` 和 `ratio` 逐张生成，等任务出结果，
   再用 `python <skill_dir>/scripts/images.py save <图片链接或文件> <save_to>` 存到指定路径。
   再跑一次 `--list-images`，确认 `todo` 是 0。不需要任何 API key → [references/visuals.md](references/visuals.md)「生图操作」
6. **排版出稿**：`python <skill_dir>/scripts/build.py proposal.md`（第一次用先跑 `--check`）
7. **自检**：`python <skill_dir>/scripts/preview.py <输出的.pdf>`，查看总览图，处理空白页、孤页和图表问题，
   再对照 [references/qa-checklist.md](references/qa-checklist.md) 过一遍内容
8. **交付**：把 PDF（和 Word）发给用户，附一段三五行的摘要，说明有哪些假设需要用户确认

`<skill_dir>` 指本技能所在目录。依赖见 `scripts/requirements.txt`。
完整样例：[assets/example/proposal.md](assets/example/proposal.md)（发布会）、
[assets/example-supercharge/proposal.md](assets/example-supercharge/proposal.md)（超充站建站可研，含 assumptions.json）。
