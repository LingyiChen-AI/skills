---
name: proposal-writer
description: 给设计方写设计需求单（宣传页 / 海报 / 折页、场站效果图与导视、工服 / 手提袋 / 纸杯等 VI 物料、办公室形象墙与门牌、集装箱 / 围挡 / 户外广告面、改稿意见），按润杰超充（重卡超充）的需求单格式出 Word 和 PDF，自动套用品牌档案（logo、VI 色、定位语、广告语、站点导视）；也能写带配图和统计图的企划书、活动 / 营销方案、超充站可研。用户说「做个宣传页」「出个效果图需求」「给设计写需求」「导视 / VI / 门牌 / 广告面怎么做」「写修改意见给设计」，或「出一份企划书 / 活动策划 / 营销方案」时使用。
---

# 设计需求单 + 企划书（proposal-writer）

先判断模式：

| 用户要的 | 模式 |
|---|---|
| 交给设计师做的东西：宣传页、海报、效果图、导视、VI 物料、门牌、形象墙、广告面、改稿意见 | **A 设计需求单**（主要用途） |
| 给老板 / 客户看的方案：企划书、活动策划、营销方案、超充站可研 / 补贴申报 / 场地合作 | **B 企划书** |

## A 设计需求单

1. **读品牌档案**：`brands/<brand>/brand.md`，默认润杰超充 → [brands/runjie/brand.md](brands/runjie/brand.md)。
   品牌名、logo、VI 色、定位语、广告语、地址、站点和导视套用关系都从这里取，不改写、不编。
2. **定类型、查必备信息**：[references/brief/types.md](references/brief/types.md)，六类：宣传页、场站效果图 + 导视、VI 物料、
   办公空间、户外广告面、改稿意见。每类有「必须拿到」清单和真实改稿里的「常见返工点」。
3. **写 `brief.md`**：流程与文案要求见 [references/brief/workflow.md](references/brief/workflow.md)，
   语法见 [references/brief/format.md](references/brief/format.md)。
   - 文案（印到画面上的字）和设计说明（`>` 引用块，只给设计师看）分开写
   - 要突出的关键词 `**加粗**`；缺的信息写 `【待补：xxx】`，文末列「需提供的素材」
   - 返工点提前写进设计说明
4. **出稿**：`python <skill_dir>/scripts/brief.py brief.md`（第一次用先跑 `--check`）。`warnings` 不为空就改完重出。
5. **自检**：`python <skill_dir>/scripts/preview.py <输出.pdf>`，对照 [references/brief/qa.md](references/brief/qa.md)。
6. **交付**：Word + PDF，消息里列出 `todos`（待补项），提醒用户补齐再转设计。改稿意见可以直接输出一段文字贴群。

样例：[assets/example-brief-flyer/brief.md](assets/example-brief-flyer/brief.md)（购车礼 A4 双面宣传页）、
[assets/example-brief-station/brief.md](assets/example-brief-station/brief.md)（两个新站的效果图 + 导视）。
换客户：复制 `brands/runjie/` 为新目录，改 `brand.md`、`rules.json`、logo，frontmatter 写 `brand: 新目录名`。

## B 企划书

1. **理解需求**：判断企划类型，补齐关键信息；信息不全时带着假设往下做 → [references/workflow.md](references/workflow.md)
   超充站 / 充电站相关先读 [references/industry/supercharging.md](references/industry/supercharging.md)；
   客户是润杰时，品牌信息同样取自 `brands/runjie/brand.md`（润杰做的是**重卡**超充，客群是司机和车队，不是乘用车）。
2. **定大纲** → [references/outlines.md](references/outlines.md)（有行业包时用行业包的大纲）。
   要算投资回报的：写 `assumptions.json`，跑 `python <skill_dir>/scripts/finance.py assumptions.json`，
   正文用 `<!-- include: finance.md -->` 插入 → [references/industry/supercharging-finance.md](references/industry/supercharging-finance.md)
3. **写正文** `proposal.md` → [references/source-format.md](references/source-format.md)、[references/writing-rules.md](references/writing-rules.md)
4. **规划配图**：数据用 ```chart，场景用 ```image → [references/visuals.md](references/visuals.md)、[references/charts.md](references/charts.md)
5. **生图（排版前做完）**：`build.py proposal.md --list-images` 列清单，用你自己的生图能力逐张生成，
   `images.py save <链接或文件> <save_to>` 存好，再跑 `--list-images` 确认 `todo` 为 0
6. **排版**：`python <skill_dir>/scripts/build.py proposal.md`
7. **自检**：`preview.py <输出.pdf>`，再对照 [references/qa-checklist.md](references/qa-checklist.md)
8. **交付**：PDF（和 Word）+ 三五行摘要，列出需要用户确认的假设

样例：[assets/example/proposal.md](assets/example/proposal.md)（发布会）、
[assets/example-supercharge/proposal.md](assets/example-supercharge/proposal.md)（超充站建站可研）。

`<skill_dir>` 指本技能所在目录。依赖见 `scripts/requirements.txt`。
