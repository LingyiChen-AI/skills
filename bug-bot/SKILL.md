---
name: bug-bot
description: Use when 管理飞书群里的「查 bug 机器人」（lark-channel-bridge + Claude Code）：给机器人加项目、加生产库、给新群配机器人、改查 bug 流程、看运行状态、重启 bridge、排查机器人不回复 / 回复异常；关键词：查 bug 机器人、bug-bot、群里 @机器人查 bug、加项目、加群、auto-bug-tester、lark-channel-bridge 重启。
---

# bug-bot：飞书群查 bug 机器人管理

群主在绑定的飞书群里 @机器人 → bridge 在该群的工作目录启动 Claude → 按目录里的 `CLAUDE.md` 读群聊、
同步最新 release 代码到 `/tmp/auto-bug-tester/<项目>`、生产只读复现 → 群里回一条结论，修复建议追加到飞书文档。

- **配置**：`config.json`（项目、生产库、隧道、群；不存口令，口令运行时从各项目的 `*.local.md` 读）。
  只在本机，不进仓库；新机器先把 `config.example.json` 复制成 `config.json` 再填。依赖：lark-channel-bridge、lark-cli（已登录用户身份）、`pip install --user pymysql`。
- **管理命令**：`python scripts/bugbot.py <子命令>`（`-h` 看参数），路径相对本 skill 目录。命令和字段说明见 `references/management.md`。
- **机器人运行时脚本**：`scripts/chat_context.py`、`sync_code.py`、`prodq.py`、`append_bug_doc.py`，由生成的 `CLAUDE.md` 调用。
- **查 bug 流程模板**：`assets/workspace-CLAUDE.md.tmpl`。改流程只改模板，然后 `bugbot.py render`，所有群一起更新，不用重启。

常见任务：
- 加项目 / 加库 / 加群 / 改流程 → `references/management.md`
- 机器人不回复、回复报错、重启、Windows 上 bridge 的坑 → `references/bridge-windows.md`

约束：生产只读（只走 `prodq.py`）；机器人只给修复建议、不改代码；重启只用 `bugbot.py restart`，不用 `lark-channel-bridge restart/start`。
