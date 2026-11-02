"""bug-bot 脚本公共函数：读写 config.json、以用户身份调 lark-cli。"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config.json"

# bridge 把 lark-cli 绑成机器人身份（bot-only）。读群历史、写文档要用群主本人身份，
# 所以调用时去掉 bridge 注入的变量，回落到本机默认（用户身份）配置。
_BRIDGE_ENV_KEYS = ("LARK_CHANNEL", "LARK_CHANNEL_HOME", "LARK_CHANNEL_PROFILE", "LARKSUITE_CLI_CONFIG_DIR")


def load_config():
    if not CONFIG_PATH.exists():
        raise SystemExit(f"缺少 {CONFIG_PATH}：先把同目录的 config.example.json 复制为 config.json 并按实际环境填写")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def expand(p):
    return Path(os.path.expanduser(p))


def lark_cli(args, cwd=None):
    """以用户身份调用 lark-cli，绕开 Windows 的 .cmd 壳（多行参数会被截断）。返回 (code, stdout, stderr)。"""
    lark = shutil.which("lark-cli")
    if not lark:
        raise SystemExit("找不到 lark-cli")
    run_js = os.path.join(os.path.dirname(lark), "node_modules", "@larksuite", "cli", "scripts", "run.js")
    env = {k: v for k, v in os.environ.items() if k not in _BRIDGE_ENV_KEYS}
    p = subprocess.run(["node", run_js, *args], capture_output=True, encoding="utf-8", env=env, cwd=cwd)
    return p.returncode, p.stdout or "", p.stderr or ""


def lark_json(args, cwd=None):
    code, out, err = lark_cli(args, cwd=cwd)
    if code != 0:
        raise SystemExit(f"lark-cli {' '.join(args[:2])} 失败 code={code}\n{err[:800]}\n{out[:800]}")
    return json.loads(out)
