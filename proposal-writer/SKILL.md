---
name: proposal-writer
description: 给设计方写设计需求单（宣传页 / 海报 / 折页、场站效果图与导视、工服 / 手提袋 / 纸杯等 VI 物料、办公室形象墙与门牌、集装箱 / 围挡 / 户外广告面、改稿意见），按甲方品牌部惯用的需求单格式出 Word 和 PDF，自动套用品牌档案（logo、VI 色、定位语、广告语、站点导视）；用户可指定一个文件夹作为知识库，出稿前先查里面的资料、往期稿和素材；也能写带配图和统计图的企划书、活动 / 营销方案、超充站可研。用户说「做个宣传页」「出个效果图需求」「给设计写需求」「导视 / VI / 门牌 / 广告面怎么做」「写修改意见给设计」，或「出一份企划书 / 活动策划 / 营销方案」时使用。
---

# 设计需求单 + 企划书（proposal-writer）

## 交付铁律（每次都适用，优先于下面所有步骤）

1. **交给用户的只能是 Word（.docx）和 PDF**。`brief.md`、`proposal.md`、`.json`、规则文件都是中间稿，**不发给用户，不放进产物**。
   最后一条消息里要附上这两个文件；没有 Word 和 PDF 就不算完成。
2. **一步完成，不反问**。用户说要什么物料，这一轮就交出 Word 和 PDF。
   - **品牌档案里有的信息（定位语、广告语、地址、色值、logo、站点……）直接用，绝不再问用户要**。先读完档案再动笔。
   - 档案里也没有的，用下面「默认值」表，不问；默认值也给不了的才写 `【待补：xxx】`，照样出稿。
   - 要选版式、选颜色、选方向时**自己选一个最合适的**，写进需求单；想给备选，就在同一份需求单里并列「方案 A / 方案 B」。
   - 「先出策划单再投产」= 这份需求单本身就是策划单，直接出。
   - **禁止**：「请你发我 XX」「补齐后我再出」「需要我先出一份示例吗」「还是等你……」。回复的最后一句不能是问句。
   - 唯一可以问的情况：完全看不出要做什么物料（只说了「帮我做个设计」）。这时只问一句，同时按最常见的理解（宣传页）先出一版。

   **默认值**（档案没写、用户也没说时直接用）：

   | 缺的信息 | 默认怎么写 |
   |---|---|
   | 工商全称 / 版权脚注 | 用档案里的品牌名，如「最终解释权归 <品牌名> 所有」；活动类用「最终解释权归场站所有」 |
   | 尺寸 | 海报 / 宣传页 A4 竖版（210×297mm）；易拉宝 80×200cm；朋友圈海报 1080×1920px |
   | 版式 / 主色 | 品牌档案的 VI 色（主色 + 白 + 辅灰）；特殊色只在档案写明的场景用 |
   | 字体 | 「按 VI 手册字体；没有就用思源黑体」 |
   | logo | 品牌档案里的 logo 文件（`brand:logo.png`），直接插进需求单 |
   | 二维码 / 小程序码 | 写「此处放小程序码（设计方从品牌源文件取用，不得自绘）」，留位置 |
   | 电话 | 宣传页、海报留空白手填；户外广告用档案里的服务热线 |
   | 交稿时间 / 数量 | 写【待补】，不影响出稿 |
   | 交付格式 | 源文件 + JPG |
3. **用户在对话里给的要求、规则、口径（如「电话留空手填」「加脚注」「先出策划单」），直接写进这份需求单**，
   不要去改 `brands/`、`references/` 下的文件，也不要另外生成「规则文件」交付。
   用户明确说「以后都这样」时，照样先出这次的 Word 和 PDF，在消息末尾用一句话说明这条规则已写进本次需求单。
4. `brief.py` 跑不起来（缺依赖、不能执行 Python）时：先 `pip install -r <skill_dir>/scripts/requirements.txt` 重试；
   还不行就用平台自带的文档生成能力，按 [references/brief/format.md](references/brief/format.md) 的版式直接做出 Word，再导出 PDF。
   **任何情况下都不能用 Markdown 文件代替 Word 交付。**
   没有 LibreOffice、出不了 PDF 时，用平台的「Word 转 PDF」能力；实在不行就只交 Word，并说明原因。

## 第 0 步：查知识库（两种模式都做）

`python <skill_dir>/scripts/kb.py status`：
- 已配置 → `kb.py search 关键词…` 找资料、往期稿、价格、logo、二维码，`kb.py read <path>` 读相关文件，
  图片用 `kb:相对路径` 插进稿子。事实优先级：用户本轮消息 > 知识库 > 品牌档案 > 默认值。
- 没配置 → 跳过，照常出稿。输出里 `remind: true` 时，在交付消息最后加一句（陈述句）提醒用户可以指定知识库文件夹。
- 用户在对话里发了文件夹路径 → `kb.py set <路径>`，接着做任务。

细则 → [references/knowledge-base.md](references/knowledge-base.md)

先判断模式：

| 用户要的 | 模式 |
|---|---|
| 交给设计师做的东西：宣传页、海报、效果图、导视、VI 物料、门牌、形象墙、广告面、改稿意见 | **A 设计需求单**（主要用途） |
| 给老板 / 客户看的方案：企划书、活动策划、营销方案、超充站可研 / 补贴申报 / 场地合作 | **B 企划书** |

## A 设计需求单

1. **读品牌档案**：`brands/<brand>/brand.md`；没写 `brand` 时用 `brands/DEFAULT` 里的目录名（仓库自带的是虚构示例品牌 [brands/demo/brand.md](brands/demo/brand.md)）。
   品牌名、logo、VI 色、定位语、广告语、地址、站点和导视套用关系都从这里取，不改写、不编。
2. **定类型、查必备信息**：[references/brief/types.md](references/brief/types.md)，六类：宣传页、场站效果图 + 导视、VI 物料、
   办公空间、户外广告面、改稿意见。每类有「必须拿到」清单和真实改稿里的「常见返工点」。
3. **写 `brief.md`**：流程与文案要求见 [references/brief/workflow.md](references/brief/workflow.md)，
   语法见 [references/brief/format.md](references/brief/format.md)。
   - 文案（印到画面上的字）和设计说明（`>` 引用块，只给设计师看）分开写
   - 要突出的关键词 `**加粗**`；缺的信息写 `【待补：xxx】`，文末列「需提供的素材」
   - 返工点提前写进设计说明
   - 知识库里找到的 logo、二维码、产品图、现场照片用 `kb:相对路径` 直接插入
4. **出稿**：`python <skill_dir>/scripts/brief.py brief.md`（第一次用先跑 `--check`）。`warnings` 不为空就改完重出。
5. **自检**：`python <skill_dir>/scripts/preview.py <输出.pdf>`，对照 [references/brief/qa.md](references/brief/qa.md)。
6. **交付**：发 `brief.py` 输出 JSON 里 `outputs` 的 docx 和 pdf 两个文件（不发 brief.md），
   消息里列出 `todos`（待补项），提醒用户补齐再转设计。改稿意见除了出文件，也可以附一段文字方便贴群。

样例：[assets/example-brief-flyer/brief.md](assets/example-brief-flyer/brief.md)（购车礼 A4 双面宣传页）、
[assets/example-brief-station/brief.md](assets/example-brief-station/brief.md)（两个新站的效果图 + 导视）。
换客户：复制 `brands/demo/` 为新目录，改 `brand.md`、`rules.json`、logo，再把 `brands/DEFAULT` 改成新目录名（或在 frontmatter 写 `brand: 新目录名`）。

## B 企划书

1. **理解需求**：判断企划类型，补齐关键信息；信息不全时带着假设往下做 → [references/workflow.md](references/workflow.md)
   超充站 / 充电站相关先读 [references/industry/supercharging.md](references/industry/supercharging.md)；
   客户有品牌档案时，品牌信息同样取自 `brands/<brand>/brand.md`；客户做**重卡**超充时，客群是司机和车队，不是乘用车。
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

知识库里有往期方案、数据表、价格、站点资料时，背景和测算数字优先用它（注明出处文件名），不再用默认假设。

样例：[assets/example/proposal.md](assets/example/proposal.md)（发布会）、
[assets/example-supercharge/proposal.md](assets/example-supercharge/proposal.md)（超充站建站可研）。

`<skill_dir>` 指本技能所在目录。依赖见 `scripts/requirements.txt`。

**安装后**：告诉用户可以指定一个文件夹当知识库（发路径给 Agent，或运行 `python <skill_dir>/scripts/kb.py set <文件夹路径>`，
或设环境变量 `PROPOSAL_KB_DIR`）。不配置也能用。
