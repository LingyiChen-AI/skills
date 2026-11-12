// 假 Claude：模拟真 claude 的会话文件 + SessionStart / SessionEnd hook，并记下自己被怎么启动的。
// 进程名得叫 claude.exe 钩子才会取参数，所以这里把参数通过环境外的方式传给 hook：直接在事件里校验 marker。
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');
const C = require('./e2e-config.json');

const argv = process.argv.slice(2);
let id = null;
let resume = false;
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === '--resume' || argv[i] === '--session-id') {
    id = argv[i + 1];
    resume = argv[i] === '--resume';
  }
}
id = id || crypto.randomUUID();
const cwd = process.cwd();
const projDir = path.join(C.claudeDir, 'projects', cwd.replace(/[^a-zA-Z0-9]/g, '-'));
fs.mkdirSync(projDir, { recursive: true });
const jsonl = path.join(projDir, `${id}.jsonl`);
if (!fs.existsSync(jsonl)) {
  fs.writeFileSync(jsonl, JSON.stringify({ type: 'user', message: { content: `测试会话 ${path.basename(cwd)}` } }) + '\n');
}
fs.appendFileSync(C.markers, JSON.stringify({ argv, cwd, id, pid: process.pid, time: Date.now() }) + '\n');

function hook(payload) {
  spawnSync(process.execPath, [path.join(C.claudeDir, 'terminal-restore', 'hook.js')], {
    input: JSON.stringify(payload),
    env: { ...process.env, CLAUDE_CONFIG_DIR: C.claudeDir },
  });
}
hook({ session_id: id, hook_event_name: 'SessionStart', cwd, source: resume ? 'resume' : 'startup' });
console.log(`[fake claude] session ${id} cwd ${cwd} args ${argv.join(' ')}`);

process.stdin.setEncoding('utf8');
process.stdin.on('data', (d) => {
  const mm = /mode (\w+)/.exec(d);
  if (mm) {
    hook({ session_id: id, hook_event_name: 'UserPromptSubmit', cwd, permission_mode: mm[1], prompt: 'hi' });
    fs.appendFileSync(C.markers.replace('markers.log', 'modes.log'), `${id} ${mm[1]}\n`);
    return;
  }
  if (d.includes('exit')) {
    hook({ session_id: id, hook_event_name: 'SessionEnd', cwd, reason: 'prompt_input_exit' });
    process.exit(0);
  }
});
setInterval(() => {}, 1 << 30);
