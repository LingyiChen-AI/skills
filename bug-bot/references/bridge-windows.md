# lark-channel-bridge 在本机（Windows）的部署与排障

- 包：npm `lark-channel-bridge` 0.7.1（源码 github zarazhangrui/lark-coding-agent-bridge），全局安装。
- 机器人：扫码向导创建的 PersonalAgent 应用，名称和 app id 见 `~/.lark-channel/config.json` 的 `profiles.<profile>.accounts.app`；profile 默认 `claude`，状态目录 `~/.lark-channel/`。
- 常驻：计划任务 `LarkChannelBridge.Bot.claude`，ONLOGON 触发，动作改为
  `conhost.exe --headless %USERPROFILE%\.lark-channel\daemon\claude\launcher.cmd`（不弹窗口，见下表）。
- 群 → 工作目录绑定：`~/.lark-channel/profiles/claude/workspaces.json` 的 `chats.<chat_id>.cwd`。
- 偏好：`~/.lark-channel/config.json` 的 `profiles.claude.preferences`
  （`messageReply: text` + `messageReplyMigrated: true`、`showToolCalls: false`、`cotMessages: off`、`runIdleTimeoutMinutes: 30`）。
- 日志：`~/.lark-channel/profiles/claude/logs/bridge-YYYYMMDD.jsonl`（按 chatId / traceId 过滤）、
  `logs/daemon/daemon-stderr.log`。机器人每次运行的完整过程：`~/.claude/projects/<工作目录编码>/<session>.jsonl`。

## 已踩过的坑

| 现象 | 原因 | 处理 |
|---|---|---|
| `lark-channel-bridge start` 报 `错误: 拒绝访问。`（终端里是乱码） | 创建 ONLOGON 计划任务需要管理员 | 管理员终端执行一次；之后用 `bugbot.py restart` |
| `status` 正常但不回消息，任务 Last Result `-1073741510` | 任务弹出的控制台窗口被关掉（0xC000013A） | 任务动作改成 `conhost.exe --headless ...` |
| 机器人回复 `Failed to authenticate. API Error: 403 Request not allowed` | 计划任务启动的进程没有代理，直连 Anthropic 被拒 | 把代理设成用户级环境变量 `HTTPS_PROXY/HTTP_PROXY=<本机代理地址>`、`NO_PROXY=localhost,127.0.0.1,::1`（只写在 PowerShell profile 里不够） |
| `start` / `restart` 后起不来：`当前 profile 已有 bridge 进程占用`、`kill ESRCH` | Windows 上进程被杀后不清 `registry/locks/*.meta.json` 和 `registry/processes.json` | `bugbot.py restart`（`scripts/restart-bridge.ps1` 会清理已退出 PID 的记录） |
| `lark-channel-bridge start` 之后又弹黑窗口、launcher 被改 | `start` 每次重写 launcher.cmd 并重新注册任务 | 不用 `start`；若已执行，管理员终端重建任务：`schtasks /Create /F /SC ONLOGON /RL LIMITED /TN "LarkChannelBridge.Bot.claude" /TR "conhost.exe --headless %USERPROFILE%\.lark-channel\daemon\claude\launcher.cmd"`（cmd 里执行；PowerShell 里把 `%USERPROFILE%` 换成 `$env:USERPROFILE`） |
| 群消息开头混进「正在定位……」之类的句子 | bridge 纯文本模式把 Claude 所有文字段落拼成一条 | 模板已严禁；仍出现就需要改 bridge 源码（先 fork） |
| 含中文的 .ps1 在 PowerShell 5.1 报语法错 | 无 BOM 的 UTF-8 被当 ANSI 读 | .ps1 存成 UTF-8 BOM |

## 排查顺序

1. `python scripts/bugbot.py status`：进程在不在、群有没有绑定。
2. 看 bridge 日志里该 chatId 最近的事件：`intake` 有没有收到、`skip-not-allowed-user`（不是群主触发）、`agent exit code`、`outbound sent`。
3. 看机器人会话 jsonl：调用了哪些脚本、哪一步报错。
