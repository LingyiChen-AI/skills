# bug-bot

飞书群里的「查 bug 机器人」。群主在群里回复一条 bug 消息并 @机器人，机器人在后台读群聊上下文，
把项目最新的 release 分支拉到 `/tmp/auto-bug-tester/<项目>` 读代码，经飞书「SQL执行窗口」只读查生产库复现，
最后在群里回一条结论（结论 / 复现步骤 / 修复建议），并把修复建议追加到飞书文档。只给建议，不改代码。

本 skill 负责管理：加项目、加生产库、给群配机器人、改查 bug 流程模板、重启和排障。

## 架构

- [lark-channel-bridge](https://github.com/zarazhangrui/lark-coding-agent-bridge)：把飞书消息桥接到本机 Claude Code，
  每个群绑定一个工作目录。
- 群工作目录里的 `CLAUDE.md` 由 `assets/workspace-CLAUDE.md.tmpl` 渲染，规定流程、输出格式和硬规则。
- `scripts/` 里的运行时脚本：`chat_context.py`（读群聊）、`sync_code.py`（同步最新 release）、
  `sqlq.mjs`（生产只读查询，经 SQL 执行窗口）、`append_bug_doc.py`（写飞书文档）。

## 依赖

- Windows + Git Bash，Node.js 22+，Python 3.10+。
- `npm i -g lark-channel-bridge`，扫码绑定一个飞书 PersonalAgent 应用；常驻方式见 `references/bridge-windows.md`。
- `lark-cli` 已用本人账号登录（读群聊、写文档、往 SQL 群提交查询都用用户身份）。
- sql-window skill 装在 `~/.claude/skills/sql-window`，并按它的说明完成首次接通（`~/.codex/sql-window/connection.json`，状态 verified）。

## 配置

```bash
cp config.example.json config.json   # 按实际环境填写；config.json 已被 .gitignore 忽略
```

不存任何数据库地址和口令：`dbs` 只登记库别名和 MySQL 库名，查询由 SQL 执行窗口机器人执行。

## 命令

`python scripts/bugbot.py <子命令>`：

| 子命令 | 用途 |
| --- | --- |
| `list` | 列出项目、库、群、SQL 执行窗口连接状态 |
| `add-project` | 登记项目（仓库、release 分支规则、规则文件、用到的库） |
| `add-db` | 登记生产库（别名 → MySQL 库名） |
| `add-group` | 给群配机器人：查 chat_id、校验机器人在群里和文档可访问、生成工作目录、绑定、重启 |
| `remove-group` | 解除群绑定 |
| `render` | 按模板重新生成所有群的 `CLAUDE.md` |
| `check [--live]` | 自检：同步代码 + SQL 执行窗口连接；`--live` 真发一条 `SELECT 1` |
| `status` / `restart` | 查看状态 / 重启 bridge（会清理 Windows 上的残留锁） |

详细参数和字段说明见 `references/management.md`。

## 安全护栏

- `sqlq.mjs` 复用 sql-window 的校验：只允许单条 SELECT，必须带成本依据，自动加 `MAX_EXECUTION_TIME(5000)`，
  没写 LIMIT 补 50（上限 200），不许 `SELECT *`；一次只跑一条（串行锁），按请求 ID 幂等发送，超时不重发。
- 群不加入 bridge 白名单，只有群主（应用创建者）@ 才会触发。
- 机器人以 `bypassPermissions` 运行，护栏靠脚本和 `CLAUDE.md` 约束。
