# bug-bot

飞书群里的「查 bug 机器人」。群主在群里回复一条 bug 消息并 @机器人，机器人在后台读群聊上下文，
把项目最新的 release 分支拉到 `/tmp/auto-bug-tester/<项目>` 读代码，在生产库只读复现，
最后在群里回一条结论（结论 / 复现步骤 / 修复建议），并把修复建议追加到飞书文档。只给建议，不改代码。

本 skill 负责管理：加项目、加生产库、给群配机器人、改查 bug 流程模板、重启和排障。

## 架构

- [lark-channel-bridge](https://github.com/zarazhangrui/lark-coding-agent-bridge)：把飞书消息桥接到本机 Claude Code，
  每个群绑定一个工作目录。
- 群工作目录里的 `CLAUDE.md` 由 `assets/workspace-CLAUDE.md.tmpl` 渲染，规定流程、输出格式和硬规则。
- `scripts/` 里的运行时脚本：`chat_context.py`（读群聊）、`sync_code.py`（同步最新 release）、
  `prodq.py`（生产只读查询，带护栏）、`append_bug_doc.py`（写飞书文档）。

## 依赖

- Windows + Git Bash，Node.js 20.12+，Python 3.10+（`python -m pip install --user pymysql`）。
- `npm i -g lark-channel-bridge`，扫码绑定一个飞书 PersonalAgent 应用；常驻方式见 `references/bridge-windows.md`。
- `lark-cli` 已用本人账号登录（读群聊、写文档用用户身份）。
- 访问私网生产库需要跳板机和 SSH 私钥。

## 配置

```bash
cp config.example.json config.json   # 按实际环境填写；config.json 已被 .gitignore 忽略
```

口令不写进 `config.json`：每个库指向一份本地 markdown（如 `数据库连接.local.md`）里的
`DSN: "user:pw@tcp(host:port)/db"` 行，运行时读取。

## 命令

`python scripts/bugbot.py <子命令>`：

| 子命令 | 用途 |
| --- | --- |
| `list` | 列出项目、库、群 |
| `add-project` | 登记项目（仓库、release 分支规则、规则文件、用到的库） |
| `add-db` | 登记生产库（DSN 来源、是否走隧道） |
| `add-group` | 给群配机器人：查 chat_id、校验机器人在群里和文档可访问、生成工作目录、绑定、重启 |
| `remove-group` | 解除群绑定 |
| `render` | 按模板重新生成所有群的 `CLAUDE.md` |
| `check` | 自检：同步代码 + 每个库 `SELECT 1` |
| `status` / `restart` | 查看状态 / 重启 bridge（会清理 Windows 上的残留锁） |

详细参数和字段说明见 `references/management.md`。

## 安全护栏

- `prodq.py` 只允许单条 SELECT / WITH / SHOW / DESC / EXPLAIN，自动补 LIMIT（默认 50，上限 200），
  聚合必须带 WHERE；MySQL 会话设为 READ ONLY，查询超时 15 秒。
- 群不加入 bridge 白名单，只有群主（应用创建者）@ 才会触发。
- 机器人以 `bypassPermissions` 运行，护栏靠脚本和 `CLAUDE.md` 约束，生产库建议使用只读账号。
