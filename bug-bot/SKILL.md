---
name: bug-bot
description: Use when 管理飞书群里的「查 bug 机器人」（lark-channel-bridge + Claude Code）：给机器人加项目、加生产库、给新群配机器人、改查 bug 流程、看运行状态、重启 bridge、排查机器人不回复 / 回复异常；关键词：查 bug 机器人、bug-bot、群里 @机器人查 bug、加项目、加群、auto-bug-tester、lark-channel-bridge 重启。
---

# bug-bot：飞书群查 bug 机器人管理

群主在绑定的飞书群里 @机器人 → bridge 在该群的工作目录启动 Claude → 按目录里的 `CLAUDE.md` 读群聊、
同步最新 release 代码到 `/tmp/auto-bug-tester/<项目>`、经 SQL 执行窗口只读查生产 → 群里回一条结论，修复建议追加到飞书文档。

- **配置**：`config.json`（项目、生产库别名、群）。只在本机，不进仓库；新机器先把 `config.example.json` 复制成 `config.json` 再填。
  依赖：lark-channel-bridge、lark-cli（已登录用户身份）、**sql-window skill**（`~/.codex/sql-window/connection.json` 已接通）。
- **查生产库**：不直连。`scripts/sqlq.mjs` 复用 sql-window skill，以群主身份把 SQL 发到飞书「研发SQL执行群」，由「SQL执行窗口」机器人执行后读回结果。只支持 MySQL 单条 SELECT。
- **管理命令**：`python scripts/bugbot.py <子命令>`（`-h` 看参数），路径相对本 skill 目录。命令和字段说明见 `references/management.md`。
- **机器人运行时脚本**：`scripts/chat_context.py`、`p2p_context.py`（读群主点名的私聊，自带校验）、`sync_code.py`、`sqlq.mjs`、`append_bug_doc.py`，由生成的 `CLAUDE.md` 调用。
- **查 bug 流程模板**：`assets/workspace-CLAUDE.md.tmpl`。改流程只改模板，然后 `bugbot.py render`，所有群一起更新，不用重启。

常见任务：
- 加群：**不用跑命令**。把机器人拉进群、群主 @ 一次就会自动登记（`onboard`，默认项目 `default_projects`，自动建记录文档）；所有人都能 @ 要在群里发 `/invite group`。指定项目 / 文档才用 `add-group`。
- 加项目 / 加库 / 改群配置 / 改流程 / 查库不通 → `references/management.md`
- 机器人不回复、回复报错、重启、Windows 上 bridge 的坑 → `references/bridge-windows.md`

约束：生产只读（只走 `sqlq.mjs`）；机器人只给修复建议、不改代码；重启只用 `bugbot.py restart`，不用 `lark-channel-bridge restart/start`。
