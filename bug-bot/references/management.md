# 管理命令与配置

所有命令：`python scripts/bugbot.py <子命令>`（在 skill 目录 `~/.claude/skills/bug-bot` 下执行，或写完整路径）。
脚本直接用 `python` 运行，不要加 `-I`。

## 子命令

| 子命令 | 作用 |
|---|---|
| `list` | 列出已登记的项目、库、群 |
| `add-project <名字> --repo <git url> [--branch-glob 'release/*'] [--rules AGENTS.md] [--desc 说明] [--dbs a,b]` | 登记项目。会 `git ls-remote` 验证仓库，并打印匹配到的最新分支。名字就是 `/tmp/auto-bug-tester/<名字>` 的目录名 |
| `add-db <别名> --database <MySQL 库名> [--projects a,b]` | 登记生产库。库名就是 SQL 执行窗口里 `USE` 的库；只支持 MySQL（StarRocks 不在 SQL 执行窗口范围内） |
| `add-group (--chat-name 群名 \| --chat-id oc_xxx) --projects a,b --doc <飞书文档链接> [--slug 目录名]` | 给群配机器人：查 chat_id → 确认机器人在群里 → 确认文档能访问 → 生成工作目录和 CLAUDE.md → 写 bridge 绑定 → 重启。对已有的群再执行一次就是修改（项目、文档） |
| `remove-group <chat_id>` | 解除绑定并重启（工作目录和 reports 保留） |
| `render [--chat-id x]` | 按模板重新生成群工作目录的 CLAUDE.md（改了模板、项目说明、库列表之后执行）。CLAUDE.md 每次运行时读取，不用重启 |
| `check [--project x] [--live]` | 自检：同步每个项目的最新代码；核对 SQL 执行窗口连接已 verified、机器人还在 SQL 群里（只读）。`--live` 会真的往 SQL 群发一条 `SELECT 1` 走通整条链路 |
| `status` | bridge 进程、各群绑定、今天最后一次回复时间 |
| `restart` | 重启 bridge（会清理 Windows 上残留的锁记录） |

## 典型流程

**加一个新项目到现有群**：
1. `add-db ...`（项目用到新的生产库时）
2. `add-project other-service --repo git@gitee.com:<org>/other-service.git --desc "另一个后端（Go/gin）" --dbs other_db`
3. `add-group --chat-id <群> --projects my-service,other-service --doc <原文档>`（或改 config.json 的 groups 后 `render`）
4. `check --project other-service`

**给一个新群配机器人**：
1. 在飞书里把机器人拉进群，新建一份记录用的飞书文档。
2. `add-group --chat-name "XX沟通群" --projects my-service --doc <文档链接>`
3. 群主在群里回复 bug 消息并 @机器人 试一次。

**改查 bug 流程**（输出格式、硬规则、查询上限）：改 `assets/workspace-CLAUDE.md.tmpl` → `render`。

## config.json 字段

- `code_root`：代码克隆根目录，`~/AppData/Local/Temp/auto-bug-tester`（Git Bash 里就是 `/tmp/auto-bug-tester`）。
- `bridge`：bridge 状态目录、profile 名、群工作目录根、计划任务名。
- `projects.<名字>`：`repo`、`branch_glob`（fnmatch，取版本号最大的；`release/V3.3` > `release/V3.0-20260824`）、`rules_file`、`description`、`dbs`（库别名列表，决定 CLAUDE.md 里列出哪些库）。
- `sql_window.skill_dir`：sql-window skill 的目录（默认 `~/.claude/skills/sql-window`）。
- `dbs.<别名>`：`kind`（只能是 `mysql`）、`database`（SQL 执行窗口里 `USE` 的库名）。不存地址和口令。
- `groups.<chat_id>`：`name`、`slug`（工作目录名，在 `bridge.workspaces_root` 下）、`projects`、`doc_url`。

## 查生产库：sqlq.mjs（经 SQL 执行窗口）

`node scripts/sqlq.mjs --db <别名> --cost "<成本依据>" "<SELECT ...>"`。流程：
本地校验（sql-window 的 `prepare`）→ 拿串行锁 → 以群主身份往「研发SQL执行群」发 `-- env: prod / USE 库 / SQL / @SQL执行窗口`
（按请求 ID 幂等）→ 每 10 秒读一次原消息的话题，最多 6 次 → 拿到机器人回复后打印结果并 `finish` 释放锁。

- 连接配置是 sql-window 的 `~/.codex/sql-window/connection.json`（chatId、机器人 open_id `botId`、`botAppId`、status）。
  2026-11-02 已用 `SELECT 1` 联调通过（status = verified）。机器人换了、群换了就按 sql-window skill「首次接通」重新核实。
- 请求记录在 `~/.codex/sql-window/requests/<请求ID>/`（SQL、发送回执、话题原文）。
- 输出 `[未完成]`：机器人 1 分钟内没回，用 `--fetch <请求ID>` 再读；下一次查询拿锁时也会先自动收尾已发送的旧请求。
- 状态是 `unknown`（发送结果不明）时脚本拒绝继续，需要人工到 SQL 群核对原消息，按 sql-window skill「中断和异常」处理后再 `finish`，不要手动删锁。
- 机器人拒绝执行（例如判定不是只读）时会直接回复原消息而不是在话题里，脚本两种都认。
- 脚本绕开 `lark-cli.cmd`（Windows 上多行参数会被截断），用 `node run.js` 调用，并去掉 bridge 注入的环境变量，保证是用户身份。

## 机制要点

- **只有群主能触发**：群不加入 bridge 白名单（不执行 `/invite group`），bridge 只放行应用创建者；别人 @ 时 bridge 会回一句"尚未加入响应列表"。
- **只发结论**：bridge profile 偏好设为纯文本回复、隐藏工具、关闭 COT（私聊也生效）。但 Claude 的所有文字段落都会被拼进最终消息，所以模板里严禁输出进度句。若仍混入，只能改 bridge 源码（纯文本模式下 Claude 也只取 `final_text`），按用户要求要先 fork 到自己仓库再改。
- **身份**：bridge 让 agent 的 lark-cli 走机器人身份；`chat_context.py`、`append_bug_doc.py` 去掉 bridge 环境变量，改用本机 lark-cli 默认的用户身份（群主本人）读群、写文档。
- **会话延续**：同一个群的多次 @ 共用一个 Claude 会话（bridge 按群保存 session）。
