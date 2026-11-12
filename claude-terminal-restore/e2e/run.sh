#!/bin/bash
# 用法: bash run.sh <pwsh|wsl>   在隔离的 VS Code 实例里跑一遍「启动 → 退出 → 重开恢复」
set -u
mode=$1
E=$(cd "$(dirname "$0")" && pwd -W)
NODE="${NODE:-$(command -v node)}" # 复制一份 node.exe 当假 claude 用
mkdir -p "$E/bin"
[ -f "$E/bin/claude.exe" ] || cp "$NODE" "$E/bin/claude.exe"

R=$(python "$E/setup.py" "$mode")
echo "run dir: $R"
if [ ! -f "$E/driver/ctr-e2e-driver-0.0.1.vsix" ] || [ "$E/driver/extension.js" -nt "$E/driver/ctr-e2e-driver-0.0.1.vsix" ]; then
  (cd "$E/driver" && rm -f *.vsix && npx -y @vscode/vsce@3.6.0 package --allow-missing-repository --skip-license >/dev/null 2>&1)
fi
cp "$E/e2e-config.json" "$E/driver/e2e-config.json"
(cd "$E/driver" && rm -f *.vsix && npx -y @vscode/vsce@3.6.0 package --allow-missing-repository --skip-license >/dev/null 2>&1)

MAIN=$(ls /c/codes/tools/claude-terminal-restore/*.vsix | tail -1)
CODE=(code --user-data-dir "$R/ud" --extensions-dir "$R/ext")
"${CODE[@]}" --install-extension "$MAIN" --force 2>&1 | grep -i success
"${CODE[@]}" --install-extension "$E/driver/ctr-e2e-driver-0.0.1.vsix" --force 2>&1 | grep -i success

export CLAUDE_CONFIG_DIR="${R//\//\\}\\claude-home"

running() {
  powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='Code.exe'\" | Where-Object { \$_.CommandLine -like '*run-$mode*' }).Count" | tr -d '\r'
}

wait_phase() {
  local want=$1 limit=$2 i=0
  while [ "$(cat "$R/phase")" != "$want" ] && [ $i -lt $limit ]; do sleep 2; i=$((i+2)); done
  echo "phase=$(cat "$R/phase") after ${i}s"
}

wait_exit() {
  local i=0
  while [ "$(running)" != "0" ] && [ $i -lt 60 ]; do sleep 2; i=$((i+2)); done
  echo "code instances left: $(running)"
}

echo "== 第 1 轮"
"${CODE[@]}" --new-window "$R/ws" >/dev/null 2>&1
wait_phase 2 240
wait_exit
echo "== 第 2 轮（重开）"
"${CODE[@]}" "$R/ws" >/dev/null 2>&1
wait_phase done 120
wait_exit
echo "== 结果"
cat "$R/results.json"
echo
echo "== 插件日志"
find "$R/ud/logs" -name "*Claude 终端恢复*" -exec sh -c 'echo "-- $1"; cat "$1"' _ {} \;
