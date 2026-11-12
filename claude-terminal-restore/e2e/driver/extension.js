// 测试驱动：在隔离的 VS Code 里模拟用户操作。
// 第 1 轮：开 A/B/C 三个终端，各自 cd 到子目录启动假 claude（A 带启动参数）；叉掉 B，C 里 /exit；然后退出 VS Code。
// 第 2 轮：等恢复列表弹出、回车接受，检查 A 是否在原目录、带原参数 --resume 回来。
const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const C = require('./e2e-config.json');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = { mode: C.mode, steps: [] };
function step(name, ok, info) {
  results.steps.push({ name, ok, info });
  fs.writeFileSync(C.results, JSON.stringify(results, null, 2));
}
function markers() {
  try {
    return fs.readFileSync(C.markers, 'utf8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l));
  } catch {
    return [];
  }
}
function stateFile() {
  const key = vscode.workspace.workspaceFolders[0].uri.fsPath;
  return path.join(C.claudeDir, 'terminal-restore', 'workspaces',
    crypto.createHash('sha1').update(key.toLowerCase()).digest('hex').slice(0, 16) + '.json');
}
function sessions() {
  try {
    return JSON.parse(fs.readFileSync(stateFile(), 'utf8')).sessions;
  } catch {
    return [];
  }
}
async function waitFor(fn, ms) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    const v = fn();
    if (v) return v;
    await sleep(500);
  }
  return null;
}
const norm = (p) => (p || '').replace(/[\\/]+$/, '').toLowerCase();

async function phase1() {
  const mk = async (name, sub, extra) => {
    const t = vscode.window.createTerminal({ name });
    t.show();
    await sleep(3000);
    t.sendText(`cd "${C.shellDirs[sub]}"`);
    await sleep(800);
    t.sendText(`${C.command} ${extra}`.trim());
    const m = await waitFor(() => markers().find((x) => norm(x.cwd) === norm(C.winDirs[sub])), 30000);
    step(`启动 ${name}（cd ${sub}）`, !!m, m);
    return { t, m };
  };
  const A = await mk('A', 'projA', '--dangerously-skip-permissions --model opus');
  const B = await mk('B', 'projB', '');
  const Cc = await mk('C', 'projC', '');
  A.t.sendText('mode auto');
  const all = await waitFor(() => sessions().length >= 3 && sessions(), 30000);
  step('三个会话都被识别', !!all, all);

  B.t.show();
  await sleep(500);
  await vscode.commands.executeCommand('workbench.action.terminal.kill');
  Cc.t.sendText('exit');
  const left = await waitFor(() => {
    const s = sessions();
    return s.length === 1 && A.m && s[0].sessionId === A.m.id && s;
  }, 30000);
  step('叉掉 B、C 里 exit 后只剩 A', !!left, sessions());
  const a = sessions().find((s) => A.m && s.sessionId === A.m.id);
  step('A 记下了会话里切换的权限模式 auto', !!a && a.permissionMode === 'auto', a && a.permissionMode);
  step('A 记下了原目录和启动参数', !!a && norm(a.cwd) === norm(C.winDirs.projA)
    && JSON.stringify(a.launchArgs) === JSON.stringify(['--dangerously-skip-permissions', '--model', 'opus']), a);

  results.markerCount = markers().length;
  fs.writeFileSync(C.phaseFile, '2');
  fs.writeFileSync(C.results.replace('.json', '-phase1.json'), JSON.stringify(results, null, 2));
  await sleep(1000);
  await vscode.commands.executeCommand('workbench.action.quit');
}

async function phase2() {
  const p1 = JSON.parse(fs.readFileSync(C.results.replace('.json', '-phase1.json'), 'utf8'));
  results.steps = p1.steps;
  const aId = (p1.steps[0].info || {}).id;
  const before = p1.markerCount; // 第 1 轮结束时的数量；静默恢复可能比驱动启动还早
  await sleep(3000); // 默认静默恢复，不操作任何弹窗
  const m = await waitFor(() => markers().slice(before).find((x) => x.id === aId), 30000);
  step('重开后恢复了 A', !!m, m);
  if (m) {
    step('恢复时进入原目录', norm(m.cwd) === norm(C.winDirs.projA), m.cwd);
    const want = ['--dangerously-skip-permissions', '--model', 'opus', '--permission-mode', 'auto', '--resume', aId];
    step('恢复时带上原启动参数和权限模式', JSON.stringify(m.argv.slice(-7)) === JSON.stringify(want), m.argv);
  }
  const others = markers().slice(before).filter((x) => x.id !== aId);
  step('B、C 没有被恢复', others.length === 0, others);
  fs.writeFileSync(C.phaseFile, 'done');
  await sleep(1000);
  await vscode.commands.executeCommand('workbench.action.quit');
}

function activate() {
  const phase = fs.readFileSync(C.phaseFile, 'utf8').trim();
  setTimeout(() => {
    (phase === '1' ? phase1() : phase === '2' ? phase2() : Promise.resolve()).catch((e) => step('异常', false, String(e.stack || e)));
  }, 2000);
}

module.exports = { activate };
