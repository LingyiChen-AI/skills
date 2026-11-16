# proposal-writer

两种模式：

- **A 设计需求单**（主要用途）：一句话需求 → 按客户惯用格式写好的设计需求单（Word + PDF），交给设计方做宣传页 / 海报、
  场站效果图与导视、VI 物料（工服、手提袋、纸杯）、办公室形象墙与门牌、集装箱 / 户外广告面，也能写改稿意见。
  依据真实需求单和改稿群聊，把每类物料的必备信息和常见返工点写进模板；自动套用品牌档案并做品牌规则检查。仓库自带的品牌「驰远超充」和全部样例都是虚构的。
- **B 企划书**：一句话需求 → 带配图、统计图、排好版的企划书（Word + PDF）。
  支持活动企划、营销方案、新品上市、通用企划；带**超充站 / 充电站行业包**（建站可研、补贴申报、场地合作提案、开业活动、年度运营营销，含投资收益测算）。

设计目标是放进千问办公「技能扩展」，经「IM 频道 · 飞书」在飞书里 @ 机器人出稿，也可以在 Claude Code 等 Agent 里直接用。

## 安装后：配置知识库（可选）

可以指定一个文件夹当知识库，不限文件类型（ppt、pdf、Word、Excel、图片、视频、设计源文件……），
出稿前 Agent 会先到里面搜索、读取相关文件，素材用 `kb:相对路径` 直接插进稿子。不配置也能正常用。

```bash
python scripts/kb.py set <文件夹路径>     # 配置（也可以在对话里把路径发给 Agent，或设环境变量 PROPOSAL_KB_DIR）
python scripts/kb.py status              # 查看是否已配置
python scripts/kb.py search 海报 小程序码  # 按文件名和正文搜索
python scripts/kb.py read 价格/服务费.xlsx  # 抽文字；抽不出的（图片、视频、源文件）由 Agent 自己打开分析
```

没配置时，第一次出稿会在交付消息末尾提醒一句，不会打断任务。

## 设计需求单

```bash
python scripts/brief.py 工作目录/brief.md          # 出 docx + pdf；输出 todos（待补项）和 warnings（品牌规则）
```

```
brands/DEFAULT            默认品牌目录名（不写 brand 时用它）
brands/demo/              虚构示例品牌档案（换客户就复制这个目录，改完把 DEFAULT 指向它）
├── brand.md              品牌信息、VI 色、logo 规则、站点与导视套用、办公点、权益口径、已有物料、对接习惯
├── rules.json            出稿自动检查：禁用旧广告语、各类型必有内容、宣传页电话留白
└── logo.png / partner-logo.png
references/brief/
├── workflow.md           流程、提问规则、文案要求
├── types.md              六类物料：必须拿到的信息 + 需求单结构 + 常见返工点
├── format.md             brief.md 语法（文案与设计说明分开写）
└── qa.md                 交付前检查
scripts/brief.py、render_brief.py   brief.md → 需求单版式（A4、标题 + 头部信息 + 分区文案）
assets/example-brief-flyer/、example-brief-station/   样例：购车礼 A4 双面宣传页、新站效果图 + 导视
```


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
