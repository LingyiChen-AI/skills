---
name: wechat-typeset
description: 把 Markdown 排版成微信公众号可直接粘贴的内联样式 HTML，30 套主题可选，并可把排好的稿件作为草稿推送到公众号后台。当用户要求「排版」「公众号排版」「转成公众号格式」「生成推文 HTML」「上传公众号草稿」「发到公众号后台」，或写完一篇公众号文章需要落地成可发布形态时使用。移植自 raphael-publish（github.com/liuxiaopai-ai/raphael-publish）。
---

# wechat-typeset

Markdown → 微信公众号 HTML。微信编辑器会剥掉 `<style>` 标签和 class，只认内联样式，
所以排版必须在生成阶段就把样式写死到每个元素上。本 skill 做的就是这件事。

## 排版

```bash
node ~/.agents/skills/wechat-typeset/render.mjs <input.md> --theme <id> --out <output.html>
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--theme <id>` | 主题 id，默认 `apple` |
| `--out <file>` | 输出 HTML 文件；省略则打到 stdout |
| `--title <t>` | 标题；省略时取正文第一个 H1 |
| `--json` | 输出统计信息（字节数、图片数、内联样式节点数等） |
| `--fit` | **推草稿时就用这个。**自动逐档压缩直到 < 20000 字符，压到哪档会在输出里报 |
| `--max-chars N` | 自定义上限，默认 20000 |
| `--compact` | 只做第一档（短字体栈+去空格），手动控制时用 |
| `--drop-important` | 配合 `--compact` 追加第二档 |
| `--list-themes` | 列出全部 30 套主题 |

看有哪些主题：

```bash
node ~/.agents/skills/wechat-typeset/render.mjs --list-themes
```

分三组共 30 套。常用的几个：

- **经典** — `apple`（Mac，极致留白）、`claude`（燕麦卡其，适合长文）、`wechat`（微信原生观感）、
  `media`（NYT）、`medium`、`stripe`、`bloomberg`
- **潮流** — `notion`、`github`、`sspai`、`dracula`、`nord`、`sakura`、`ocean`、`monokai`
- **更多风格** — `solarized`、`cyberpunk`、`ink`、`lavender`、`forest`、`coffee`、`bauhaus`

## 它对微信做了哪些适配

直接用 markdown-it 的输出粘进公众号会散架，以下问题都已处理：

1. **根节点用 `<section>`** 并带容器样式 —— 微信对顶层 `div` 的处理不稳定。
2. **样式全部内联** —— 每个 `p / li / h1-h4 / blockquote / table / img` 都写死 style。
3. **`<li>` 里的 `<p>` 降级成 `<span>`** —— 否则微信会把列表项拆成多个块。
4. **字体属性强制下发** —— 微信编辑器会丢掉继承，所以把容器的
   `font-family / font-size / line-height / color` 逐个复制到文本节点上。
5. **中文标点吸入强调标签** —— `<strong>重点</strong>：` 会被微信在冒号前换行，
   改成 `<strong>重点：</strong>`，并用 U+2060 word-joiner 兜底。
6. **标题内的 strong/em/a/code 改用 `inherit`** —— 避免标题被正文的强调配色污染。
7. **代码块带 Mac 三色圆点**，语法高亮由 highlight.js 内联完成。

## 推送到公众号草稿箱

**凭据已经配好了**（`env.vars.WECHAT_APPID` / `WECHAT_APPSECRET`，网关启动时注入进程环境）。
不要再向用户索要 AppID 或 AppSecret，直接用环境变量里的即可；先跑一次 dry-run 自查，
确认输出无误后立刻带 `--commit` 提交，不需要停下来征求同意——草稿只进草稿箱，不会群发。

```bash
node ~/.agents/skills/wechat-typeset/publish.mjs <article.html> \
  --title "<标题>" --author "$WX_AUTHOR" --digest "<摘要>" [--thumb-media-id "<封面素材 id>"]

node ~/.agents/skills/wechat-typeset/publish.mjs <article.html> \
  --title "<标题>" --author "$WX_AUTHOR" --digest "<摘要>" --commit
```

不加 `--commit` 时是 dry-run，只打印将要调用的接口，不发任何请求。

流程是公众号官方的两步：`cgi-bin/token` 拿 access_token → `cgi-bin/draft/add` 建草稿。
草稿只进后台草稿箱，不会自动群发，还需要人到后台确认发布。

AppSecret 只从环境变量读，不接受命令行参数，也不会打进日志——命令行参数会留在 shell history 里。

## 注意

- **正文 ≤ 20000 字符**（官方文档原文：「必须少于2万字符」）。内联样式占全文八成，
  所以渲染时**务必加 `--fit`**，它会自动逐档压：
  1. 短字体栈 + 去空格（移动端渲染不变，零风险）
  2. 去 `!important`（微信样式表若有 important 规则可能反压过来）
  3. 去掉与容器重复的 font-family/font-size/line-height，改走继承（最后手段）
  三档压完仍超限时，输出里的 `trimChineseCharsBy` 会告诉你还要删多少字，
  按这个数删，不要换主题乱试——主题之间体积差别很小。
- **外部图片 URL 会被微信直接过滤掉**（文档原文：「外部图片url将被过滤」）。
  `publish.mjs` 已自动把正文里的外链图逐张走 `cgi-bin/media/uploadimg` 转存，
  封面走 `cgi-bin/material/add_material`。不要手动塞外链。
- 服务器 IP 需要在公众号后台的 IP 白名单里，否则 `cgi-bin/token` 返回 40164。
