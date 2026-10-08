---
name: wx-article
description: |
  公众号文章一条龙：调研 → 定角度标题 → 建目录 → 配图 → 写正文 → 传图床换 CDN → 排版 → 推草稿箱。
  触发词：写篇推文 / 写个公众号文章 / 发到公众号 / 查资料写文章 / 帮我写文章发微信 / wx-article。
  【第一步必做】用 read 工具读 ~/.agents/skills/wx-article/SKILL.md 拿到完整流程，不要用 tool_search 找它，它是文件不是工具。
  【三条铁律，即使没读上面那个文件也要遵守】
  1 搜索不要用 web_search（本机没配 provider，必然失败），用 node ~/.agents/skills/wx-article/scripts/search.mjs "<关键词>" --count 8，再用 web_fetch 打开原页核实。
  2 不要反问用户、不要给 A/B 选项、不要只写个框架让用户补——角度标题自己定，碰到障碍自己解决。
  3 七步全做完、草稿进了公众号后台才算完成，写完 content.md 只是第五步。
  只排版不写作时用 wechat-typeset。
---

# wx-article

把一个选题做成可发布的公众号文章。全流程七步，一口气做完。

## 不要反问，直接产出

用户给了选题就直接写完发草稿，**不要停下来问角度、问标题、问要不要继续**。
角度和标题你自己定——**先读 `references/style.md`**，那里有从 36 篇已发布文章里
统计出来的人设、篇幅、结构和开头写法，照着定就不会偏。

**碰到障碍自己解决，不要变成选择题甩回来。** 缺图就生成，缺封面就做封面，
脚本报错就读报错自己修，主题没选好就按内容调性挑一个。不要出现
「你给我两个选择」「走 A 还是走 B」「要不要继续」这类话。

只有这两种情况才回头问：

- 调研后发现信源不足，写出来会是编的
- 用户的要求本身有歧义（比如同名的两个东西，不确定指哪个）

**缺环境变量不算障碍，先自查**：`WX_GITHUB_TOKEN`、`WECHAT_APPID`、`WECHAT_APPSECRET`、
`WX_AUTHOR` 应当已配在网关 `env.vars` 里（配置方法见本目录 README）。脚本报 not set 时先 `echo ${VAR:+set}` 确认，
而不是直接判定"做不了"。

注意图床用的是 **`WX_GITHUB_TOKEN`** 不是 `GITHUB_TOKEN` —— openclaw 会刻意把
`GITHUB_TOKEN`/`GH_TOKEN` 从 agent 环境里抹掉（防止网关的 GitHub 凭据泄漏给
agent 执行的命令），所以图床单独用了一个名字。

其余一律自己决策。

## 什么才算做完

**七步全部跑完、草稿进了公众号后台，才算完成。** 写完 `content.md` 只是第五步，
后面还有配图上传、排版、推草稿。不要写完正文就停。

收尾前对照这份清单，每项都要有对应的工具调用记录：

- [ ] 目录建好（`new-article.mjs`）
- [ ] **配图齐了**，至少封面 + 1–2 张内容图（没有素材就用 fireworks 自己画）
- [ ] 正文用 `write` 工具写进 `content.md`
- [ ] **正文里每张图都用 `![]()` 引了** —— `grep -c '!\[' content.md` 要等于图片数，
      为 0 说明图白画了
- [ ] 图片传图床、`content.md` 里换成 CDN 链接（`leftoverLocalRefs` 为空）
- [ ] `render.mjs --fit` 生成 `content.html`，输出 `fits: true`
- [ ] `publish.mjs --commit` 推草稿，拿到 `media_id`

**不要把文章正文贴进聊天框。** 正文在 `content.md` 里，用户点开就能看。
最后只回一段简短汇报：标题、角度一句话、字数、配图数、主题、草稿 media_id。

**提到文件时用 markdown 链接写完整绝对路径**：`[content.md](~/.openclaw/workspace/wx-content/…/content.md)`。
只用反引号包路径不会变成可点的文件卡片，缩写成 `.../content.html` 更会直接报
`session file not found`。

任何一步失败就地解决再往下走；真的解决不了，说清楚卡在哪、还差什么，
而不是停在半截假装完成。

默认目录 **`~/.openclaw/workspace/wx-content`**，用户另有指定就用他给的。
必须放在 agent workspace 里面——界面的文件面板只能打开根目录内的文件，
放到 `~/codes/...` 用户点开会报 `session file not found`。

## 一、调研

按内容类型选手段，不要一律用同一个：

| 类型 | 调研方式 |
| --- | --- |
| 外部资讯 / 爆料 / 新工具 | `scripts/search.mjs` 搜，再 `web_fetch` 逐条核实（见下） |
| 自己的项目发布 / 版本更新 | `git -C <repo> log --oneline -15` + 读 README |
| 接入 / 编译 / 部署教程 | **先把步骤真跑一遍**，拿到真实输出再落笔 |
| 资源分享 / 引流 | 同上，先看目标赛道近期热度，确认卖点站得住 |

调研完一句话交代料够不够、最抓人的点是什么，然后**直接继续**，不要等回复。

### 搜索怎么做

本机 `web_search` **没有配 provider**（需要 Brave / Serper 之类的 API key），调它必然失败。
不要浪费一轮去试，直接用自带的兜底脚本：

```bash
node ~/.agents/skills/wx-article/scripts/search.mjs "<关键词>" --count 8
```

它抓 Bing 结果页，不需要任何 key，返回标题 / 来源站 / 摘要 / 真实 URL。
拿到结果后**必须再用 `web_fetch` 打开原页核实**——摘要只够判断哪条值得读，不足以作为事实依据。

想查某个具体站点就直接 `web_fetch`，它是通的（如果报
`Blocked: resolves to private/internal/special-use IP address`，
说明 `tools.web.fetch.ssrfPolicy.allowRfc2544BenchmarkRange` 被关掉了，打开即可）。

**没有信源就不要写。** 搜不到、打不开、信息对不上时，如实告诉用户缺什么，
问他是否提供资料。绝对不要编造数据、时间线、版本号、benchmark、引用链接。

## 二、定角度和标题（自己定，不要问）

调研完立刻定下来，一句话说明你的选择，然后继续往下做：

- **角度**：找反差、落差、或一个具体的痛点。不要平铺直叙地介绍「它是什么」。
- **标题**：直给、有信息量。参考已发布的那批——《K8s Admin：一个轻量级的多集群
  Kubernetes 管理平台》《Seedance 2.0 API 个人也能用了：通过 UCloud 曲线调用》
  《Claude Mythos 5 炸场：10 万亿参数，强到 Anthropic 自己都不敢公开发布》。
- **结构**：按 `references/style.md` 里对应类型的骨架走。

## 三、建目录

```bash
node ~/.agents/skills/wx-article/scripts/new-article.mjs "<标题>" [--root <dir>]
```

不带 `--root` 时默认写到 `~/.openclaw/workspace/wx-content/YYYYMMDD/<标题>/`，产出 `content.md` 和同级 `resources/`。
标题里的 `/` 和 `|` 会被替换成 `-`（它们会切断路径）。

## 四、配图

**这一步在写正文之前做，不许跳过直接去写。**
实测跳过的后果：文章写完了没有图，后面传图床、排版全都空转。

每篇都必须有图，两个来源：

1. **原文/素材里的图** —— 下载到 `resources/`，正文用相对路径 `./resources/img_01.png` 引用。
   挑有信息量的（benchmark 图表、架构图、界面截图），纯文字截图不要。
2. **没有现成图就自己生成** —— 用 fireworks-tech-graph 画。资讯类画对比图或时间线，
   工具类画架构图或工作流，教程类画流程图。一篇至少 2–3 张，别让正文一路纯文字。

### 用 fireworks-tech-graph 画图

**它不是 CLI**，是 skill 目录里的 python 脚本。真实调用方式：

```bash
FW=~/.agents/skills/fireworks-tech-graph
cd "$FW" && python3 ./scripts/generate-from-template.py architecture <out.svg> "$(cat spec.json)"
rsvg-convert -w 1080 -h 1920 <out.svg> -o <out.png> && rm <out.svg>
```

模板类型：`architecture` / `flow` / `sequence` / `concept`。

**节点必须带坐标**，只给 label 会报 `Unexpected error: 'x'`。
照着 `$FW/fixtures/*.json` 写 spec，字段是
`{id, kind, x, y, width, height, label, type_label, fill, stroke}`，
箭头是 `{source, target, source_port, target_port, flow}`。
先 `cat` 一个 fixture 看结构再动手，不要凭空造 JSON。

**配色只能用浅底。** 模板的文字颜色是写死的深色（`#111827`），
填深色底会让字完全看不见——实测用 `#0B1220` 出来就是一团黑方块。

安全配色：

- `fill` 一律 `#ffffff`，或极浅的 `#f8fafc` / `#f5f5f7`
- `stroke` 用彩色描边做区分：`#2F6FED` 蓝 / `#22C55E` 绿 / `#F59E0B` 橙 / `#dce5e3` 灰
- 不要自创 `fill`，直接抄 fixture 里的值

**画布要显式给够。** 顶层加 `"width"` / `"height"`，并保证
`最右节点的 x + width + 60 <= 画布 width`，否则右边会被切掉（实测切过）。
竖排比横排安全——一行放三个框很容易超宽。

**label 要短。** 一个框里塞「高置信度 → 直接走自动分支(规则 / 工具调用 / 简单回复)」
这么长会溢出框、和邻框文字叠在一起（实测叠过）。单行控制在 14 个汉字以内，
长内容用 `\n` 换行分成两三行，或者把框加宽。

**画完必须自己看一眼。** 用 `read` 打开生成的 png 确认文字清晰可读，
糊了、看不见字、布局重叠就改 spec 重画，不要把废图塞进文章。

封面用 9:16（1080×1920），正文配图用默认比例。

## 五、写正文

**前置检查**：`resources/` 里必须已经有图了。空的说明第四步被跳过了，回去补。

**动笔前先读 `~/.agents/skills/wx-article/references/style.md`**，按里面的规范写。
### 图片和链接的写法不一样，别搞混

**图片必须用 markdown 图片语法**，这是唯一能渲染出图的写法：

```markdown
![封面](./resources/cover.png)
![Jev 工作流](./resources/flow.png)
```

写成 `（封面图：https://...）` 这种纯文本**不会渲染成图片**，只会显示一行字——实测犯过。
正文里每张图都要用 `![]()` 引，一张不引等于白画。

**超链接才贴纯文本 URL**（公众号渲染不了 `[文字](url)` 这种链接语法）：

```markdown
GitHub：https://github.com/xxx/yyy
```

一句话记：**`![]()` 给图片，裸 URL 给链接。**

**正文必须用 `write` 工具写入**，不要用 `exec` + heredoc。
openclaw 只把 `read`/`write`/`edit` 碰过的文件登记为会话文件，
用 exec 生成的文件在界面里点开会报 `session file not found`。

要点：1300–1500 中文字、8–10 个小节、开头用那四种写法之一、结尾给行动指引或判断、
数据必须有出处、
正文从 `# 标题` 开始不要 frontmatter、图片先用相对路径下一步统一换 CDN。

## 六、传图床，换 CDN 链接

```bash
node ~/.agents/skills/wx-article/scripts/upload-images.mjs "<articleDir>"
```

它会把 `resources/` 里的图传到 GitHub 图床，并把 `content.md` 里的本地引用
**原地替换成 jsDelivr CDN 链接**。`WX_GITHUB_TOKEN` 已配在网关环境里，直接跑。

跑完检查输出的 `leftoverLocalRefs` 必须为空——有残留说明还有图没传上去，
回去补传，不要带着本地路径往下走（公众号渲染不了本地路径）。

## 七、排版 + 推草稿箱

```bash
node ~/.agents/skills/wechat-typeset/render.mjs "<content.md>" --theme <id> --fit \
  --out "<articleDir>/content.html" --json
node ~/.agents/skills/wechat-typeset/publish.mjs "<articleDir>/content.html" \
  --title "<标题>" --author "$WX_AUTHOR" --digest "<摘要>" --thumb-from-first-image --commit
```

HTML 输出到文章目录里（跟 content.md 放一起），不要丢 `/tmp`——用户要能找到。
主题先跑 `render.mjs --list-themes` 看一遍再挑，并说明为什么选它。
凭据已配在 `env.vars`，不要向用户索要 AppID / AppSecret。
`--commit` 前先跑一次 dry-run 自查；草稿只进草稿箱不会群发，确认无误就直接提交。

## 几个会踩的坑

- **正文超 20000 字符**会被微信拒。渲染必须带 `--fit`，它会自动逐档压缩到达标，
  输出里的 `compaction` 字段会说明用了哪几档。
  **不要换主题反复试**——实测主题之间体积差不到 5%，换 7 次也压不下来，纯属浪费。
  `--fit` 三档压完还超，输出里的 `trimChineseCharsBy` 会给出还需删减的字数，
  按那个数精简正文，然后重新渲染。
- **缺封面** `draft/add` 返回 40007，不是报错信息字面意思的「media_id 无效」。
  用 `--thumb-from-first-image` 让脚本自动传封面素材。
- **外链图会被微信过滤**（不是报错，是静默丢弃）。`publish.mjs` 已自动把正文外链图
  转存成微信图片、封面转成永久素材，照上面的命令跑即可。
- **公众号后台 IP 白名单** 没配会让 `cgi-bin/token` 返回 40164。挂代理时出口 IP 会变，
  报这个错就把错误信息里那个 IP 加进后台白名单。
- **界面里点不开文件** 说明它是 exec 生成的。只有 `read`/`write`/`edit` 碰过的文件
  才会被登记成会话文件。交付时如果要让用户能点开 HTML，先 `read` 一下它。
