// Claude Code 的 SessionStart / SessionEnd hook：把「哪个会话、在哪个目录、带什么参数启动、跑在哪条进程链上」
// 写成事件文件，由 VS Code 插件「Claude 终端恢复」按终端进程号认领。配置为 async，不阻塞 Claude 启动。
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.join(process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude'), 'terminal-restore');
const EVENTS = path.join(ROOT, 'events');

// 恢复时由插件自己加，不能沿用的参数：会话相关、一次性的
const DROP_WITH_VALUE = new Set(['--resume', '-r', '--session-id', '--from-pr']);
const DROP_FLAG = new Set(['--continue', '-c', '--fork-session', '--print', '-p']);
// 常见的不带值的开关，后面跟的非 - 开头的词是首句提示词，不保留
const BOOL_FLAGS = new Set([
  '--dangerously-skip-permissions', '--allow-dangerously-skip-permissions', '--verbose', '--ide',
  '--strict-mcp-config', '--chrome', '--no-chrome', '--continue', '-c', '--fork-session', '--print', '-p',
]);

function readStdin() {
  try {
    return JSON.parse(fs.readFileSync(0, 'utf8') || '{}');
  } catch {
    return {};
  }
}

/** 进程表：pid → { ParentProcessId, Name, CommandLine }。Windows 用 CIM，Mac / Linux 用 ps。 */
function processTable() {
  if (process.platform !== 'win32') {
    const out = execFileSync('ps', ['-A', '-o', 'pid=,ppid=,args='], { encoding: 'utf8', timeout: 20000, maxBuffer: 64 * 1024 * 1024 });
    const m = new Map();
    for (const line of out.split('\n')) {
      const r = /^\s*(\d+)\s+(\d+)\s+(.*)$/.exec(line);
      if (!r) continue;
      const args = r[3].trim();
      const first = args.split(/\s+/)[0] || '';
      m.set(Number(r[1]), { ProcessId: Number(r[1]), ParentProcessId: Number(r[2]), Name: path.basename(first), CommandLine: args });
    }
    return m;
  }
  const out = execFileSync(
    'powershell.exe',
    ['-NoProfile', '-NonInteractive', '-Command',
      '[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress'],
    { encoding: 'utf8', windowsHide: true, timeout: 20000, maxBuffer: 64 * 1024 * 1024 },
  );
  const m = new Map();
  for (const p of JSON.parse(out)) m.set(p.ProcessId, p);
  return m;
}

/** Windows 命令行拆词（够用版：处理双引号）。 */
function splitCommandLine(s) {
  const out = [];
  let cur = '';
  let q = false;
  let has = false;
  for (const ch of s || '') {
    if (ch === '"') { q = !q; has = true; continue; }
    if (!q && /\s/.test(ch)) {
      if (has) out.push(cur);
      cur = '';
      has = false;
      continue;
    }
    cur += ch;
    has = true;
  }
  if (has) out.push(cur);
  return out;
}

/** 是不是 Claude 进程：原生 claude / claude.exe，或 node / bun 跑的 claude 脚本（Mac 上 npm 装的）。 */
function isClaude(p) {
  const name = (p.Name || '').toLowerCase();
  if (/^claude(\.exe)?$/.test(name)) return true;
  if (/^(node|node\.exe|bun|bun\.exe)$/.test(name)) {
    const script = splitCommandLine(p.CommandLine)[1] || '';
    return /^claude(\.js|\.cjs|\.mjs)?$/i.test(path.basename(script)) || /@anthropic-ai[\\/]claude-code/i.test(script);
  }
  return false;
}

/** 从 claude 的命令行里取出要沿用的启动参数。 */
function launchArgs(cmdline) {
  const tok = splitCommandLine(cmdline).slice(1); // 去掉 exe 本身
  const keep = [];
  for (let i = 0; i < tok.length; i++) {
    const t = tok[i];
    if (DROP_WITH_VALUE.has(t)) {
      if (tok[i + 1] && !tok[i + 1].startsWith('-')) i++;
      continue;
    }
    if (/^--(resume|session-id|from-pr)=/.test(t) || DROP_FLAG.has(t)) continue;
    if (!t.startsWith('-')) {
      const prev = keep[keep.length - 1];
      // 跟在带值参数后面的是它的值，保留；否则是首句提示词，丢掉
      if (prev && prev.startsWith('-') && !prev.includes('=') && !BOOL_FLAGS.has(prev)) keep.push(t);
      continue;
    }
    keep.push(t);
  }
  return keep;
}

function writeEvent(ev) {
  fs.mkdirSync(EVENTS, { recursive: true });
  const name = `${ev.time}-${ev.sessionId}-${ev.event}.json`;
  const tmp = path.join(EVENTS, name + '.tmp');
  fs.writeFileSync(tmp, JSON.stringify(ev));
  fs.renameSync(tmp, path.join(EVENTS, name));
}

const input = require.main === module ? readStdin() : {};
if (input.session_id && input.hook_event_name === 'UserPromptSubmit') {
  // 每次发消息记一下当前权限模式（会话里 Shift+Tab 切的模式不在命令行上）。不查进程表，很轻。
  if (input.permission_mode) {
    const cache = path.join(ROOT, 'modes', input.session_id);
    let last = '';
    try { last = fs.readFileSync(cache, 'utf8'); } catch {}
    if (last !== input.permission_mode) {
      fs.mkdirSync(path.dirname(cache), { recursive: true });
      fs.writeFileSync(cache, input.permission_mode);
      writeEvent({ event: 'Mode', sessionId: input.session_id, permissionMode: input.permission_mode, time: Date.now() });
    }
  }
} else if (input.session_id) {
  const ev = {
    event: input.hook_event_name,
    sessionId: input.session_id,
    cwd: input.cwd,
    source: input.source,
    reason: input.reason,
    ancestors: [],
    launchArgs: null,
    permissionMode: input.permission_mode || null,
    time: Date.now(),
  };
  try {
    const table = processTable();
    let pid = process.pid;
    for (let i = 0; i < 15; i++) {
      const p = table.get(pid);
      if (!p || !p.ParentProcessId || ev.ancestors.includes(p.ParentProcessId)) break;
      pid = p.ParentProcessId;
      ev.ancestors.push(pid);
      const parent = table.get(pid);
      if (ev.launchArgs === null && parent && isClaude(parent)) {
        ev.launchArgs = launchArgs(parent.CommandLine);
      }
    }
  } catch {
    ev.ancestors = [process.ppid];
  }
  writeEvent(ev);
}

module.exports = { launchArgs, splitCommandLine };
