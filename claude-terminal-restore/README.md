# Claude 终端恢复（VS Code 插件）

VS Code 关掉（或电脑关机）时，记住终端里还开着哪几个 Claude Code 会话；下次打开窗口，自动在**原目录**、按**原启动参数和权限模式**把它们 `claude --resume` 回来。只恢复关闭那一刻还开着的会话，不会把历史会话全翻出来。

## 能做什么

- **自动识别**：在普通终端里直接敲 `claude` 就行，不用换命令。插件靠 Claude Code 的 hook 认出每个终端里跑的是哪个会话。
- **只恢复该恢复的**：VS Code 退出 / 关机时开着的会话会恢复；自己叉掉的终端、在 Claude 里 `/exit` 退出的会话不再恢复。`/clear` 之后记录会换成新会话。
- **原目录、原参数**：记下会话启动时的目录和启动参数（如 `--dangerously-skip-permissions`、`--model opus`），恢复时原样带上。
- **权限模式**：会话里用 Shift+Tab 切的模式（auto、plan、acceptEdits……）每发一条消息记一次，恢复时加 `--permission-mode <模式>`。
- **多窗口**：每个工作区一份记录，互不干扰；Reload Window 不会误恢复。
- **终端类型**：PowerShell、cmd、Git Bash、WSL（Windows 上的 claude 通过 interop 跑也能识别），Mac / Linux 的 shell。
- **静默恢复**：默认打开窗口直接恢复，不弹窗，状态栏提示恢复了几个。

## 安装

```bash
code --install-extension claude-terminal-restore-0.6.0.vsix --force
```

装好后 Reload Window。插件第一次启动会：

1. 把 `hook.js` 复制到 `~/.claude/terminal-restore/hook.js`；
2. 在 `~/.claude/settings.json` 里加上 `SessionStart`、`SessionEnd`、`UserPromptSubmit` 三个 hook（`async`，不拖慢 Claude），改之前备份为 `settings.json.bak-terminal-restore`。已有的其它 hook 保留。

hook 装好之前就开着的 Claude 会话识别不到，重开一下即可。

自己打包：

```bash
npx -y @vscode/vsce@3.6.0 package --allow-missing-repository --skip-license
```

## 命令与设置

| 命令 | 作用 |
|---|---|
| `Claude: 新建 Claude 终端` | 开一个终端并启动 claude |
| `Claude: 恢复上次的 Claude 会话` | 手动恢复（弹勾选列表） |
| `Claude: 清空这个窗口的 Claude 会话记录` | 清掉本工作区的记录 |

| 设置 | 默认 | 说明 |
|---|---|---|
| `claudeRestore.command` | `claude` | 恢复时用的启动命令 |
| `claudeRestore.shellPath` | 空 | 恢复用的 shell，空则跟随默认终端 |
| `claudeRestore.startupRestore` | `silent` | `silent` 静默恢复 / `ask` 弹勾选列表 / `off` 不自动恢复 |

运行日志在输出面板「Claude 终端恢复」。

## 原理

- `hook.js`：SessionStart / SessionEnd 时从自身进程往上找进程链（Windows 用 `Get-CimInstance Win32_Process`，Mac / Linux 用 `ps`），找到 claude 进程取启动参数，写一个事件文件到 `~/.claude/terminal-restore/events/`；UserPromptSubmit 时只在权限模式变化时写一条 Mode 事件，不查进程表。
- `extension.js`：监听事件目录，用进程链匹配 VS Code 终端的 shell PID，把「终端 ↔ 会话」记到 `~/.claude/terminal-restore/workspaces/<工作区哈希>.json`。按终端关闭原因区分「用户叉掉」和「VS Code 退出」，退出时保留记录，下次打开恢复。

## 注意

- 权限模式是发消息时才记的：切了模式但一条消息都没发就关掉，恢复的还是切换前的模式。
- Mac / Linux 上 hook 需要 `node` 在 PATH 里。
- 插件每次启动都会检查并补回 hook；不想用了先卸载插件，再从 `settings.json` 删掉含 `terminal-restore/hook.js` 的三条 hook。

## 测试

`e2e/` 是端到端测试：起一个隔离的 VS Code（独立的 user-data / extensions 目录和 `CLAUDE_CONFIG_DIR`），用假 claude 开三个终端，分别模拟「保留」「叉掉」「/exit」，退出再重开，检查恢复的目录、参数、权限模式。

```bash
bash e2e/run.sh pwsh   # PowerShell 终端
bash e2e/run.sh wsl    # WSL 终端
bash e2e/unix-hook-test.sh   # 在 WSL 里测 hook.js 的 Mac / Linux 分支（需先放 e2e/bin/node-linux.tar.xz）
```

已验证：Windows 上 PowerShell、WSL 两种终端各 11 项通过；hook 的 Unix 分支在 WSL Ubuntu 里测过；真实 Claude 确认 hook 能拿到权限模式。尚未在真实 Mac 上测过。
