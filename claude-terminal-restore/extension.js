// Claude 终端恢复
// - 自动识别：Claude Code 的 SessionStart hook 写事件文件（会话 id + 进程祖先链），插件按终端 shell 进程号认领。
// - 记录关闭那一刻：关窗口 / 关 VS Code / 关机导致的终端关闭保留记录；用户自己叉掉终端、/exit 退出 Claude 的不再恢复。
// - 跨窗口：记录按工作区存成文件（~/.claude/terminal-restore/workspaces/），每个窗口打开时只恢复自己的。
const vscode = require('vscode');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

const CLAUDE_DIR = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude');
const ROOT = path.join(CLAUDE_DIR, 'terminal-restore');
const EVENTS = path.join(ROOT, 'events');
const WS_DIR = path.join(ROOT, 'workspaces');
const HOOK_DST = path.join(ROOT, 'hook.js');
const STALE_EVENT_MS = 2 * 60 * 1000;

/** @type {Map<vscode.Terminal, string>} 终端 → 会话 id */
const bound = new Map();
let stateFile = null;
let busy = Promise.resolve();
const log = vscode.window.createOutputChannel('Claude 终端恢复');

function cfg(key) {
  return vscode.workspace.getConfiguration('claudeRestore').get(key);
}

// 开机时间（分钟精度），用来判断记录里的进程号是不是本次开机的，防止重启后进程号复用认错
const BOOT_ID = Math.round((Date.now() - os.uptime() * 1000) / 60000);

// ---------- 工作区记录文件 ----------

function workspaceKey() {
  if (vscode.workspace.workspaceFile && vscode.workspace.workspaceFile.scheme === 'file') {
    return vscode.workspace.workspaceFile.fsPath;
  }
  const f = vscode.workspace.workspaceFolders;
  return f && f.length ? f[0].uri.fsPath : null;
}

function loadSessions() {
  if (!stateFile) return [];
  try {
    return JSON.parse(fs.readFileSync(stateFile, 'utf8')).sessions || [];
  } catch {
    return [];
  }
}

function saveSessions(list) {
  if (!stateFile) return;
  fs.mkdirSync(WS_DIR, { recursive: true });
  const tmp = stateFile + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify({ workspace: workspaceKey(), sessions: list }, null, 2));
  fs.renameSync(tmp, stateFile);
}

function putSession(rec) {
  saveSessions(loadSessions().filter((s) => s.sessionId !== rec.sessionId).concat(rec));
}

function dropSessions(ids) {
  const drop = new Set(ids);
  saveSessions(loadSessions().filter((s) => !drop.has(s.sessionId)));
}

// ---------- 会话记录文件（Claude 自己的 jsonl） ----------

function findSessionFile(id) {
  const root = path.join(CLAUDE_DIR, 'projects');
  let dirs = [];
  try {
    dirs = fs.readdirSync(root);
  } catch {
    return null;
  }
  for (const d of dirs) {
    const f = path.join(root, d, `${id}.jsonl`);
    if (fs.existsSync(f)) return f;
  }
  return null;
}

function firstPrompt(file) {
  let text = '';
  try {
    const fd = fs.openSync(file, 'r');
    const buf = Buffer.alloc(256 * 1024);
    const n = fs.readSync(fd, buf, 0, buf.length, 0);
    fs.closeSync(fd);
    text = buf.subarray(0, n).toString('utf8');
  } catch {
    return '';
  }
  for (const line of text.split('\n')) {
    let rec;
    try {
      rec = JSON.parse(line);
    } catch {
      continue;
    }
    if (rec.type !== 'user' || !rec.message || rec.isMeta) continue;
    const c = rec.message.content;
    const s = typeof c === 'string'
      ? c
      : Array.isArray(c) ? c.filter((p) => p && p.type === 'text').map((p) => p.text).join(' ') : '';
    const t = s.replace(/\s+/g, ' ').trim();
    if (t && !t.startsWith('<')) return t;
  }
  return '';
}

function fmtTime(ms) {
  const d = new Date(ms);
  const p = (x) => String(x).padStart(2, '0');
  return `${d.getMonth() + 1}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function short(s, n) {
  return s.length > n ? s.slice(0, n) + '…' : s;
}

// ---------- 终端 ↔ 会话 ----------

async function terminalPids() {
  const m = new Map();
  await Promise.all(vscode.window.terminals.map(async (t) => {
    try {
      const pid = await t.processId;
      if (pid) m.set(pid, t);
    } catch {}
  }));
  return m;
}

async function bindTerminal(term, sessionId, cwd, launchArgs, permissionMode) {
  const old = bound.get(term);
  const prevRec = loadSessions().find((s) => s.sessionId === sessionId || s.sessionId === old);
  if (!permissionMode) permissionMode = prevRec && prevRec.permissionMode || null;
  if (!Array.isArray(launchArgs)) {
    const prev = loadSessions().find((s) => s.sessionId === sessionId || s.sessionId === old);
    launchArgs = prev && Array.isArray(prev.launchArgs) ? prev.launchArgs : [];
  }
  if (old && old !== sessionId) dropSessions([old]); // /clear 或恢复后换了新会话 id
  bound.set(term, sessionId);
  let pid;
  try {
    pid = await term.processId;
  } catch {}
  putSession({ sessionId, cwd, launchArgs, permissionMode, shellPid: pid, bootId: BOOT_ID, terminalName: term.name, updatedAt: Date.now() });
  log.appendLine(`绑定 ${term.name} (pid ${pid}) → ${sessionId} 目录=${cwd} 参数=${launchArgs.join(' ')} 模式=${permissionMode}`);
}

function serial(fn) {
  busy = busy.then(fn, fn).catch((e) => log.appendLine(`出错：${e && e.stack || e}`));
  return busy;
}

/** 读 hook 写的事件文件，认领属于本窗口终端的。 */
function processEvents() {
  return serial(async () => {
    let files = [];
    try {
      files = fs.readdirSync(EVENTS).filter((f) => f.endsWith('.json')).sort();
    } catch {
      return;
    }
    if (!files.length) return;
    const pids = await terminalPids();
    for (const f of files) {
      const full = path.join(EVENTS, f);
      let ev;
      try {
        ev = JSON.parse(fs.readFileSync(full, 'utf8'));
      } catch {
        continue;
      }
      if (ev.event === 'Mode') {
        // 权限模式变化：按会话 id 找本窗口的记录，找不到说明是别的窗口的
        const rec = loadSessions().find((s) => s.sessionId === ev.sessionId);
        if (rec) {
          rec.permissionMode = ev.permissionMode;
          putSession(rec);
          log.appendLine(`权限模式 ${ev.sessionId} → ${ev.permissionMode}`);
          try { fs.unlinkSync(full); } catch {}
        } else if (Date.now() - (ev.time || 0) > STALE_EVENT_MS) {
          try { fs.unlinkSync(full); } catch {}
        }
        continue;
      }
      const pid = (ev.ancestors || []).find((p) => pids.has(p));
      const term = pid && pids.get(pid);
      if (term) {
        if (ev.event === 'SessionStart') {
          await bindTerminal(term, ev.sessionId, ev.cwd, ev.launchArgs, ev.permissionMode);
        } else if (ev.event === 'SessionEnd' && ['prompt_input_exit', 'logout'].includes(ev.reason)) {
          // 在 Claude 里 /exit 或 Ctrl+C 退出：用户主动结束，不再恢复
          if (bound.get(term) === ev.sessionId) bound.delete(term);
          dropSessions([ev.sessionId]);
          log.appendLine(`会话已退出 ${ev.sessionId}`);
        }
        try { fs.unlinkSync(full); } catch {}
      } else if (Date.now() - (ev.time || 0) > STALE_EVENT_MS) {
        try { fs.unlinkSync(full); } catch {} // 不在任何 VS Code 终端里的会话，过期清理
      }
    }
  });
}

/** Reload Window 后终端进程还活着：按进程号认回来。 */
async function rebindLive() {
  const pids = await terminalPids();
  for (const s of loadSessions()) {
    if (s.bootId !== BOOT_ID || !s.shellPid) continue;
    const t = pids.get(s.shellPid);
    if (t && !bound.has(t)) bound.set(t, s.sessionId);
  }
}

function makeTerminal(name, cwd) {
  const opts = { name, cwd: cwd && fs.existsSync(cwd) ? cwd : undefined };
  const shell = (cfg('shellPath') || '').trim();
  if (shell) opts.shellPath = shell;
  return vscode.window.createTerminal(opts);
}

function shellQuote(a) {
  return /^[\w@%+=:,./\-]+$/.test(a) ? a : `"${a.replace(/"/g, '\\"')}"`;
}

/** 原启动参数 + --resume，例如 claude --dangerously-skip-permissions --resume <id> */
function resumeArgs(rec) {
  const args = (rec.launchArgs || []).slice();
  const mode = rec.permissionMode;
  // 会话里最后一次的权限模式优先于启动参数里的；default 就是启动时的样子，不额外加
  if (mode && mode !== 'default') {
    for (let i = args.length - 1; i >= 0; i--) {
      if (args[i] === '--permission-mode') args.splice(i, 2);
      else if (args[i].startsWith('--permission-mode=')) args.splice(i, 1);
    }
    args.push('--permission-mode', mode);
  }
  return args;
}

function resumeCommand(rec) {
  const args = resumeArgs(rec).map(shellQuote).join(' ');
  return [cfg('command'), args, '--resume', rec.sessionId].filter(Boolean).join(' ');
}

async function restore(fromStartup) {
  const live = new Set(bound.values());
  const list = loadSessions().filter((s) => !live.has(s.sessionId));
  if (!list.length) {
    if (!fromStartup) vscode.window.showInformationMessage('这个窗口没有需要恢复的 Claude 会话。');
    return;
  }
  const items = [];
  const gone = [];
  for (const s of list) {
    const f = findSessionFile(s.sessionId);
    if (!f) {
      gone.push(s.sessionId); // 一句话没聊过，没东西可恢复
      continue;
    }
    let mtime = s.updatedAt;
    try { mtime = fs.statSync(f).mtimeMs; } catch {}
    const prompt = firstPrompt(f);
    items.push({
      label: short(prompt || s.sessionId, 50),
      description: `最后活动 ${fmtTime(mtime)}${resumeArgs(s).length ? ' · ' + resumeArgs(s).join(' ') : ''}`,
      detail: s.cwd,
      picked: true,
      rec: s,
      prompt,
      mtime,
    });
  }
  if (gone.length) dropSessions(gone);
  if (!items.length) return;
  items.sort((a, b) => b.mtime - a.mtime);

  const silent = fromStartup && cfg('startupRestore') === 'silent';
  const chosen = silent ? items : await vscode.window.showQuickPick(items, {
    canPickMany: true,
    ignoreFocusOut: true,
    title: `上次关闭时这个窗口开着 ${items.length} 个 Claude 会话，勾选要恢复的（没勾的不再提示）`,
    placeHolder: 'Esc 先不处理，之后可用命令「Claude: 恢复上次的 Claude 会话」',
  });
  if (!chosen) return;
  const keep = new Set(chosen.map((i) => i.rec.sessionId));
  dropSessions(items.filter((i) => !keep.has(i.rec.sessionId)).map((i) => i.rec.sessionId));
  let last;
  for (const i of chosen) {
    const term = makeTerminal(`Claude · ${short(i.prompt || '会话', 12)}`, i.rec.cwd);
    term.sendText(resumeCommand(i.rec));
    await bindTerminal(term, i.rec.sessionId, i.rec.cwd, i.rec.launchArgs, i.rec.permissionMode);
    last = term;
  }
  if (last) last.show(silent); // 静默恢复时不抢编辑器焦点
  if (silent && chosen.length) {
    vscode.window.setStatusBarMessage(`$(terminal) 已恢复 ${chosen.length} 个 Claude 会话`, 8000);
    log.appendLine(`静默恢复 ${chosen.length} 个会话`);
  }
}

async function newTerminal() {
  const term = makeTerminal('Claude', workspaceKey() && vscode.workspace.workspaceFolders
    ? vscode.workspace.workspaceFolders[0].uri.fsPath : undefined);
  term.show();
  term.sendText(cfg('command'));
}

// ---------- 安装 hook ----------

function ensureHook(context) {
  try {
    fs.mkdirSync(ROOT, { recursive: true });
    const src = fs.readFileSync(path.join(context.extensionPath, 'hook.js'), 'utf8');
    let cur = '';
    try { cur = fs.readFileSync(HOOK_DST, 'utf8'); } catch {}
    if (cur !== src) fs.writeFileSync(HOOK_DST, src);

    const settingsPath = path.join(CLAUDE_DIR, 'settings.json');
    let settings = {};
    if (fs.existsSync(settingsPath)) settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    const command = `node "${HOOK_DST.replace(/\\/g, '/')}"`;
    settings.hooks = settings.hooks || {};
    let changed = false;
    for (const ev of ['SessionStart', 'SessionEnd', 'UserPromptSubmit']) {
      const groups = settings.hooks[ev] = settings.hooks[ev] || [];
      const has = groups.some((g) => (g.hooks || []).some((h) => String(h.command || '').includes('terminal-restore/hook.js')));
      if (!has) {
        groups.push({ hooks: [{ type: 'command', command, async: true, timeout: 30 }] });
        changed = true;
      }
    }
    if (changed) {
      fs.copyFileSync(settingsPath, settingsPath + '.bak-terminal-restore');
      fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2) + '\n');
      log.appendLine('已在 ~/.claude/settings.json 加上会话识别 hook');
      vscode.window.showInformationMessage('Claude 终端恢复：已加上会话识别 hook，之后新启动的 Claude 会自动被记录（已开着的需重开一次）。');
    }
  } catch (e) {
    vscode.window.showWarningMessage(`Claude 终端恢复：安装 hook 失败（${e.message}），自动识别不可用。`);
  }
}

// ---------- 入口 ----------

async function activate(context) {
  const key = workspaceKey();
  stateFile = key
    ? path.join(WS_DIR, crypto.createHash('sha1').update(key.toLowerCase()).digest('hex').slice(0, 16) + '.json')
    : null;
  fs.mkdirSync(EVENTS, { recursive: true });
  ensureHook(context);

  context.subscriptions.push(
    log,
    vscode.commands.registerCommand('claudeRestore.newTerminal', newTerminal),
    vscode.commands.registerCommand('claudeRestore.restore', () => restore(false)),
    vscode.commands.registerCommand('claudeRestore.forget', () => {
      saveSessions([]);
      bound.clear();
      vscode.window.showInformationMessage('已清空这个窗口的 Claude 会话记录。');
    }),
    vscode.window.onDidOpenTerminal(() => setTimeout(processEvents, 500)),
    vscode.window.onDidCloseTerminal((t) => {
      const id = bound.get(t);
      if (!id) return;
      bound.delete(t);
      const reason = t.exitStatus && t.exitStatus.reason;
      log.appendLine(`终端关闭 ${t.name} 原因=${reason}`);
      if (reason === vscode.TerminalExitReason.User) {
        dropSessions([id]); // 用户自己叉掉
      } else if (reason === vscode.TerminalExitReason.Process) {
        // shell 退出：可能是用户 exit，也可能是关机时进程被杀。等几秒，扩展还活着才删。
        setTimeout(() => dropSessions([id]), 5000);
      }
      // Shutdown / Unknown：关窗口或退出 VS Code，保留
    }),
  );

  let timer;
  try {
    const w = fs.watch(EVENTS, () => {
      clearTimeout(timer);
      timer = setTimeout(processEvents, 300);
    });
    context.subscriptions.push({ dispose: () => w.close() });
  } catch {}
  const iv = setInterval(processEvents, 15000);
  context.subscriptions.push({ dispose: () => clearInterval(iv) });

  await rebindLive();
  await processEvents();
  if (stateFile && cfg('startupRestore') !== 'off') {
    setTimeout(() => restore(true).catch((e) => log.appendLine(String(e))), 1500);
  }
}

function deactivate() {}

module.exports = { activate, deactivate };
