# wx-article

公众号文章一条龙：调研 → 定角度标题 → 建目录 → 配图 → 写正文 → 传图床换 CDN → 排版 → 推草稿箱。
全程不反问，一次做完。

## 依赖

- **wechat-typeset** skill —— 第七步排版和推草稿靠它。没有它只能产出 Markdown。
- **fireworks-tech-graph** skill —— 第四步画配图用。
- `rsvg-convert`（`brew install librsvg`）—— svg 转 png。
- Node 18+（脚本用了内置 `fetch`）。

## 配置

```bash
openclaw config set env.vars.WX_GITHUB_TOKEN <GitHub PAT，需 Contents 读写权限>
openclaw config set env.vars.WX_AUTHOR       <公众号署名>
openclaw config set env.vars.WECHAT_APPID    <公众号 AppID>
openclaw config set env.vars.WECHAT_APPSECRET <公众号 AppSecret>
openclaw gateway restart
```

注意变量名是 `WX_GITHUB_TOKEN` 不是 `GITHUB_TOKEN` —— openclaw 会刻意把
`GITHUB_TOKEN`/`GH_TOKEN` 从 agent 环境里抹掉，防止网关的 GitHub 凭据泄漏给
agent 执行的命令。

图床仓库默认 `LingyiChen-AI/images`，用 `WX_IMAGE_REPO` 覆盖；
路径前缀默认 `wx-content-cdn`，用 `WX_IMAGE_PROJECT` 覆盖。

## 脚本

| 脚本 | 用途 |
| --- | --- |
| `scripts/new-article.mjs` | 按 `YYYYMMDD/<标题>/` 建目录 |
| `scripts/search.mjs` | 不需要 API key 的网页搜索（抓 Bing 结果页） |
| `scripts/upload-images.mjs` | 传图床并把正文里的本地路径换成 CDN 链接 |

## 文章风格

`references/style.md` 是从 36 篇已发布文章统计出来的（篇幅、小节数、加粗频次、
开头的四种写法等），不是拍脑袋定的。换成你自己的号时请重新统计。
