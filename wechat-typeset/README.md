# wechat-typeset

Markdown → 微信公众号可直接粘贴的内联样式 HTML，30 套主题；也能把稿件推到公众号草稿箱。

## 为什么需要它

微信编辑器会剥掉 `<style>` 标签和 class，只认内联样式。所以排版必须在生成阶段
就把样式写死到每个元素上，直接用 markdown-it 的输出粘进去会散架。

## 依赖

```bash
npm install          # markdown-it / linkedom / highlight.js
```

Node 18+（脚本用内置 `fetch`）。

## 用法

```bash
node render.mjs <input.md> --theme <id> --fit --out <output.html> --json
node render.mjs --list-themes
```

推草稿箱需要 `WECHAT_APPID` / `WECHAT_APPSECRET`，默认 dry-run，加 `--commit` 才真提交：

```bash
node publish.mjs <article.html> --title "<标题>" --author "<署名>" \
  --digest "<摘要>" --thumb-from-first-image --commit
```

## 两个硬限制（官方文档）

- 正文 **必须少于 2 万字符**。内联样式占全文约八成，所以渲染务必带 `--fit`，
  它会逐档压缩直到达标（短字体栈 → 去 `!important` → 去掉与容器重复的继承声明）。
- **外部图片 URL 会被微信过滤**。`publish.mjs` 已自动把正文外链图走
  `cgi-bin/media/uploadimg` 转存、封面走 `cgi-bin/material/add_material`。

## 测试

```bash
node render.mjs test/format-test.md --theme claude --fit --out /tmp/t.html
node test/check.mjs /tmp/t.html     # 14 项断言
```

## 致谢

主题表与微信兼容处理移植自
[raphael-publish](https://github.com/liuxiaopai-ai/raphael-publish)（MIT），
原项目是浏览器端 React 应用，这里改为在 linkedom 上无头运行。
上游许可证全文见 `LICENSE.upstream`。
