"""bug-bot 管理命令：登记项目 / 数据库 / 群，生成群工作目录，重启 bridge，自检。

  python bugbot.py list
  python bugbot.py add-project <名字> --repo <git url> [--branch-glob 'release/*'] [--rules AGENTS.md] [--desc ...] [--dbs a,b]
  python bugbot.py add-db <别名> --database <库> [--projects a,b]     （生产库经 sql-window 的 SQL 执行窗口查，只支持 MySQL）
  python bugbot.py add-group (--chat-name <群名> | --chat-id oc_xxx) --projects a,b --doc <飞书文档链接> [--slug xxx]
  python bugbot.py remove-group <chat_id>
  python bugbot.py render [--chat-id oc_xxx]
  python bugbot.py check [--project x] [--live]    （--live 会在 SQL 群里真发一条 SELECT 1）
  python bugbot.py status
  python bugbot.py restart
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date

from _common import CONFIG_PATH, SKILL_DIR, expand, lark_json, load_config, save_config

SCRIPTS = (SKILL_DIR / "scripts").as_posix()
TEMPLATE = SKILL_DIR / "assets" / "workspace-CLAUDE.md.tmpl"


# ---------- 公共 ----------

def bridge_paths(cfg):
    b = cfg["bridge"]
    home = expand(b["home"])
    return home, home / "profiles" / b["profile"] / "workspaces.json", expand(b["workspaces_root"])


def bot_app_id(cfg):
    home, _, _ = bridge_paths(cfg)
    root = json.loads((home / "config.json").read_text(encoding="utf-8"))
    return root["profiles"][cfg["bridge"]["profile"]]["accounts"]["app"]["id"]


def split_csv(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def restart_bridge(cfg):
    ps1 = SKILL_DIR / "scripts" / "restart-bridge.ps1"
    b = cfg["bridge"]
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1),
                        "-Root", str(expand(b["home"])), "-Task", b["scheduled_task"]],
                       capture_output=True)
    out = (p.stdout or b"").decode("gbk", "replace") + (p.stderr or b"").decode("gbk", "replace")
    print(out.strip())
    if p.returncode != 0:
        raise SystemExit("bridge 重启失败")


# ---------- render / 绑定 ----------

def render_group(cfg, chat_id):
    g = cfg["groups"][chat_id]
    _, _, ws_root = bridge_paths(cfg)
    ws = ws_root / g["slug"]
    (ws / "reports").mkdir(parents=True, exist_ok=True)

    proj_lines, dbs = [], []
    for name in g["projects"]:
        p = cfg["projects"][name]
        proj_lines.append(f"- `{name}`：{p.get('description', '')}（仓库 {p['repo']}，分支 `{p.get('branch_glob', 'release/*')}` 取最新）"
                          f"\n  生产库：{', '.join('`' + d + '`' for d in p.get('dbs', [])) or '无'}")
        dbs += [d for d in p.get("dbs", []) if d not in dbs]

    text = TEMPLATE.read_text(encoding="utf-8")
    for k, v in {
        "GROUP_NAME": g["name"], "CHAT_ID": chat_id, "SCRIPTS": SCRIPTS, "DOC_URL": g["doc_url"],
        "PROJECTS_BLOCK": "\n".join(proj_lines), "DBS_LIST": "、".join(f"`{d}`" for d in dbs) or "无",
    }.items():
        text = text.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if left:
        raise SystemExit(f"模板里有未替换的占位符：{left}")
    (ws / "CLAUDE.md").write_text(text, encoding="utf-8")
    return ws


def bind(cfg, chat_id, ws):
    _, ws_json, _ = bridge_paths(cfg)
    data = json.loads(ws_json.read_text(encoding="utf-8")) if ws_json.exists() else {}
    data.setdefault("chats", {})
    data.setdefault("named", {})
    data["chats"][chat_id] = {"cwd": str(ws)}
    ws_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def unbind(cfg, chat_id):
    _, ws_json, _ = bridge_paths(cfg)
    if not ws_json.exists():
        return False
    data = json.loads(ws_json.read_text(encoding="utf-8"))
    hit = data.get("chats", {}).pop(chat_id, None) is not None
    ws_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return hit


# ---------- 子命令 ----------

def cmd_list(cfg, a):
    print("== 项目 ==")
    for k, p in cfg["projects"].items():
        print(f"  {k:20} {p['repo']}  [{p.get('branch_glob', 'release/*')}]  库: {','.join(p.get('dbs', []))}")
    print("== 数据库 ==")
    for k, d in cfg["dbs"].items():
        print(f"  {k:20} {d['kind']:10} {d['database']}")
    conn = sql_window_conn()
    print(f"== SQL 执行窗口 ==\n  {conn.get('groupName')} ({conn.get('chatId')}) → {conn.get('botName')}  状态: {conn.get('status')}")
    print("== 群 ==")
    for k, g in cfg["groups"].items():
        print(f"  {g['name']} ({k})  项目: {','.join(g['projects'])}  目录: {g['slug']}\n    文档: {g['doc_url']}")


def cmd_add_project(cfg, a):
    out = subprocess.run(["git", "ls-remote", "--heads", a.repo], capture_output=True, encoding="utf-8", timeout=60)
    if out.returncode != 0:
        raise SystemExit(f"仓库访问失败：{out.stderr.strip()}")
    for d in split_csv(a.dbs):
        if d not in cfg["dbs"]:
            raise SystemExit(f"库 {d} 未登记，先 add-db")
    cfg["projects"][a.name] = {
        "repo": a.repo, "branch_glob": a.branch_glob, "rules_file": a.rules,
        "description": a.desc or "", "dbs": split_csv(a.dbs),
    }
    save_config(cfg)
    sys.path.insert(0, SCRIPTS)
    import fnmatch
    from sync_code import version_key
    heads = [l.split("refs/heads/", 1)[1] for l in out.stdout.splitlines() if "refs/heads/" in l]
    match = [h for h in heads if fnmatch.fnmatch(h, a.branch_glob)]
    print(f"已登记项目 {a.name}；匹配 {a.branch_glob} 的分支 {len(match)} 个，最新：{max(match, key=version_key) if match else '无'}")
    print("用到它的群需要重新 render：python bugbot.py render")


def sql_window_conn():
    home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    p = os.path.join(home, "sql-window", "connection.json")
    if not os.path.exists(p):
        raise SystemExit(f"缺少 {p}：先按 sql-window skill 完成首次接通（找到 SQL 群和「SQL执行窗口」机器人）")
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def cmd_add_db(cfg, a):
    cfg["dbs"][a.alias] = {"kind": "mysql", "database": a.database}
    for p in split_csv(a.projects):
        if p not in cfg["projects"]:
            raise SystemExit(f"项目 {p} 未登记")
        if a.alias not in cfg["projects"][p]["dbs"]:
            cfg["projects"][p]["dbs"].append(a.alias)
    save_config(cfg)
    print(f"已登记库 {a.alias}（MySQL 库 {a.database}，经 SQL 执行窗口查询）。用到它的群需要重新 render")


def resolve_chat(a):
    if a.chat_id:
        info = lark_json(["api", "GET", f"/open-apis/im/v1/chats/{a.chat_id}", "--as", "user"])
        return a.chat_id, (info.get("data") or {}).get("name") or a.chat_id
    chats = lark_json(["im", "+chat-search", "--as", "user", "--query", a.chat_name])["data"].get("chats") or []
    exact = [c for c in chats if c["name"] == a.chat_name]
    pick = exact or chats
    if len(pick) != 1:
        names = "、".join(f"{c['name']}({c['chat_id']})" for c in chats) or "无"
        raise SystemExit(f"群名「{a.chat_name}」匹配到 {len(pick)} 个，请改用 --chat-id。候选：{names}")
    return pick[0]["chat_id"], pick[0]["name"]


def cmd_add_group(cfg, a):
    projects = split_csv(a.projects)
    for p in projects:
        if p not in cfg["projects"]:
            raise SystemExit(f"项目 {p} 未登记，先 add-project")
    chat_id, name = resolve_chat(a)
    bots = lark_json(["im", "+chat-members-list", "--as", "user", "--chat-id", chat_id, "--member-types", "bot"])["data"]["bots"]
    app_id = bot_app_id(cfg)
    if not any(b.get("app_id") == app_id for b in bots):
        raise SystemExit(f"机器人（{app_id}）不在群「{name}」里，先在飞书里把它拉进群")
    lark_json(["docs", "+fetch", "--as", "user", "--doc", a.doc])  # 验证文档可访问

    old = cfg["groups"].get(chat_id, {})
    slug = a.slug or old.get("slug") or f"bug-bot-{chat_id[-8:]}"
    cfg["groups"][chat_id] = {"name": name, "slug": slug, "projects": projects, "doc_url": a.doc}
    save_config(cfg)
    ws = render_group(cfg, chat_id)
    bind(cfg, chat_id, ws)
    print(f"群「{name}」({chat_id}) → {ws}")
    if not a.no_restart:
        restart_bridge(cfg)


def cmd_remove_group(cfg, a):
    g = cfg["groups"].pop(a.chat_id, None)
    save_config(cfg)
    hit = unbind(cfg, a.chat_id)
    print(f"已移除群 {g['name'] if g else a.chat_id}（bridge 绑定{'已解除' if hit else '本来就没有'}；工作目录保留）")
    restart_bridge(cfg)


def cmd_render(cfg, a):
    targets = [a.chat_id] if a.chat_id else list(cfg["groups"])
    for cid in targets:
        ws = render_group(cfg, cid)
        bind(cfg, cid, ws)
        print(f"已生成 {ws / 'CLAUDE.md'}")
    print("CLAUDE.md 每次运行时读取，改完不用重启；新增绑定才需要 python bugbot.py restart")


def cmd_check(cfg, a):
    sys.path.insert(0, SCRIPTS)
    from sync_code import sync
    ok = True
    projects = [a.project] if a.project else list(cfg["projects"])
    for name in projects:
        try:
            repo_dir, branch, info = sync(name)
            print(f"[代码] {name}: {branch} @ {info}")
        except SystemExit as e:
            ok = False
            print(f"[代码] {name}: 失败 {e}")
        for d in cfg["projects"][name].get("dbs", []):
            spec = cfg["dbs"].get(d)
            if not spec or spec.get("kind") != "mysql":
                ok = False
                print(f"[库]   {d}: 未登记或不是 MySQL（SQL 执行窗口只支持 MySQL）")
    # SQL 执行窗口：连接配置 + 机器人还在群里（只读，不发消息）
    try:
        conn = sql_window_conn()
        bots = lark_json(["im", "+chat-members-list", "--as", "user", "--chat-id", conn["chatId"],
                          "--member-types", "bot", "--page-size", "50"])["data"]["bots"]
        hit = any(b.get("member_id") == conn["botId"] for b in bots)
        ok = ok and hit and conn.get("status") == "verified"
        print(f"[SQL]  {conn.get('groupName')} / {conn.get('botName')}: 连接 {conn.get('status')}，机器人{'在群里' if hit else '不在群里'}")
    except SystemExit as e:
        ok = False
        print(f"[SQL]  失败 {e}")
    if a.live:
        p = subprocess.run(["node", str(SKILL_DIR / "scripts" / "sqlq.mjs"), "--test"], capture_output=True, encoding="utf-8")
        print(f"[SQL]  联调 SELECT 1: {'ok' if p.returncode == 0 else '失败'}\n{(p.stdout or p.stderr).strip()[-600:]}")
        ok = ok and p.returncode == 0
    sys.exit(0 if ok else 1)


def cmd_status(cfg, a):
    home, ws_json, _ = bridge_paths(cfg)
    p = subprocess.run(["lark-channel-bridge", "ps"], capture_output=True, encoding="utf-8", shell=True)
    print(p.stdout.strip() or p.stderr.strip())
    binds = json.loads(ws_json.read_text(encoding="utf-8")).get("chats", {}) if ws_json.exists() else {}
    log = home / "profiles" / cfg["bridge"]["profile"] / "logs" / f"bridge-{date.today():%Y%m%d}.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    for cid, g in cfg["groups"].items():
        bound = binds.get(cid, {}).get("cwd", "")
        last = next((json.loads(l) for l in reversed(lines) if cid in l and '"event":"sent"' in l), None)
        print(f"- {g['name']}: 绑定 {'✓ ' + bound if bound else '✗ 未绑定'}；今天最后一次回复 {last['ts'][11:19] if last else '无'}")


def main():
    ap = argparse.ArgumentParser(description="bug-bot 管理")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("add-project")
    s.add_argument("name"); s.add_argument("--repo", required=True)
    s.add_argument("--branch-glob", default="release/*"); s.add_argument("--rules", default="AGENTS.md")
    s.add_argument("--desc"); s.add_argument("--dbs")
    s = sub.add_parser("add-db")
    s.add_argument("alias"); s.add_argument("--database", required=True); s.add_argument("--projects")
    s = sub.add_parser("add-group")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--chat-name"); g.add_argument("--chat-id")
    s.add_argument("--projects", required=True); s.add_argument("--doc", required=True)
    s.add_argument("--slug"); s.add_argument("--no-restart", action="store_true")
    s = sub.add_parser("remove-group"); s.add_argument("chat_id")
    s = sub.add_parser("render"); s.add_argument("--chat-id")
    s = sub.add_parser("check"); s.add_argument("--project"); s.add_argument("--live", action="store_true")
    sub.add_parser("status")
    sub.add_parser("restart")
    a = ap.parse_args()

    cfg = load_config()
    {
        "list": cmd_list, "add-project": cmd_add_project, "add-db": cmd_add_db, "add-group": cmd_add_group,
        "remove-group": cmd_remove_group, "render": cmd_render, "check": cmd_check, "status": cmd_status,
        "restart": lambda c, _: restart_bridge(c),
    }[a.cmd](cfg, a)


if __name__ == "__main__":
    main()
