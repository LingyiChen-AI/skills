#!/bin/bash
# 在 Linux（WSL）里测 hook.js 的 Mac / Linux 分支：ps 取进程链、认出 claude 进程、取启动参数。
set -e
D=$(cd "$(dirname "$0")/.." && pwd)  # 插件根目录
T=/tmp/ctr-unix
rm -rf $T && mkdir -p $T/home $T/npm
tar -xJf $D/e2e/bin/node-linux.tar.xz -C $T
NODE=$(ls -d $T/node-v*/bin)/node
cp $D/hook.js $T/home/hook.js

cat > $T/fake.js <<'EOF'
const { spawnSync } = require('child_process');
const r = spawnSync(process.execPath, [process.env.HOOK], {
  input: JSON.stringify({ session_id: process.env.SID, hook_event_name: 'SessionStart', cwd: process.cwd() }),
  env: { ...process.env, CLAUDE_CONFIG_DIR: process.env.CFG },
});
process.stdout.write(String(r.stderr || ''));
EOF

# 1) 原生 claude 形式：可执行文件名就叫 claude
ln -s $NODE $T/claude
# 2) npm 形式：node 跑一个叫 claude 的脚本
cp $T/fake.js $T/npm/claude

check() {
  local sid=$1
  local f=$(ls $T/home/terminal-restore/events/*-$sid-SessionStart.json)
  echo "== $sid"
  cat $f; echo
}

cd /tmp
SHELLPID=$$
HOOK=$T/home/hook.js CFG=$T/home SID=native $T/claude $T/fake.js --dangerously-skip-permissions --model opus "首句提示"
check native
HOOK=$T/home/hook.js CFG=$T/home SID=npm $NODE $T/npm/claude --resume abc --permission-mode plan
check npm
echo "本 shell pid: $SHELLPID"
