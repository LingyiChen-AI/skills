"""准备隔离 VS Code 的测试环境。用法: python setup.py <pwsh|wsl>"""
import json, os, shutil, sys

mode = sys.argv[1]
E = os.path.dirname(os.path.abspath(__file__)).replace('\\', '/')
R = f'{E}/run-{mode}'
shutil.rmtree(R, ignore_errors=True)
os.makedirs(R)
claude_dir = f'{R}/claude-home'
os.makedirs(claude_dir)
with open(f'{claude_dir}/settings.json', 'w', encoding='utf-8') as f:
    json.dump({}, f)

win_dirs, shell_dirs = {}, {}
for sub in ['projA', 'projB', 'projC']:
    d = f'{R}/ws/{sub}'
    os.makedirs(d)
    win_dirs[sub] = d.replace('/', '\\')
    shell_dirs[sub] = d if mode == 'pwsh' else '/mnt/' + d[0].lower() + d[2:]

exe = f'{E}/bin/claude.exe'
fake = f'{E}/fakeclaude.js'
if mode == 'pwsh':
    command = f'& "{exe}" "{fake}"'
else:
    command = f'"/mnt/{exe[0].lower()}{exe[2:]}" "{fake}"'

cfg = {
    'mode': mode,
    'claudeDir': claude_dir.replace('/', '\\'),
    'markers': f'{R}/markers.log',
    'results': f'{R}/results.json',
    'phaseFile': f'{R}/phase',
    'winDirs': win_dirs,
    'shellDirs': shell_dirs,
    'command': command,
}
for target in [f'{E}/e2e-config.json', f'{E}/driver/e2e-config.json']:
    with open(target, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
with open(cfg['phaseFile'], 'w') as f:
    f.write('1')

os.makedirs(f'{R}/ud/User')
settings = {
    'security.workspace.trust.enabled': False,
    'workbench.startupEditor': 'none',
    'update.mode': 'none',
    'extensions.autoUpdate': False,
    'extensions.autoCheckUpdates': False,
    'telemetry.telemetryLevel': 'off',
    'terminal.integrated.confirmOnKill': 'never',
    'terminal.integrated.confirmOnExit': 'never',
    'window.restoreWindows': 'all',
    'python.terminal.activateEnvironment': False,
    'claudeRestore.command': command,
    'terminal.integrated.defaultProfile.windows': 'PowerShell' if mode == 'pwsh' else 'Ubuntu (WSL)',
}
with open(f'{R}/ud/User/settings.json', 'w', encoding='utf-8') as f:
    json.dump(settings, f, ensure_ascii=False, indent=2)
print(R)
