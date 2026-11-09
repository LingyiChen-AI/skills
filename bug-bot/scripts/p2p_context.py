"""读群主和某个人的私聊记录（群主用户身份），按时间正序输出精简文本。

  python p2p_context.py --trigger om_xxx --with 胡涵 [--days 7] [--limit 50] [--download-dir reports/res]

私聊是群主的隐私，脚本自己做校验，不信任调用方：
  1. --trigger 必须是本次 @机器人 的那条群消息；用群主身份读回它，发送人必须是群主本人。
  2. 触发消息正文里必须出现 --with 的名字（群主点名要看和谁的对话）。
  3. 按名字搜人，必须唯一命中，且群主和对方聊过（有 p2p 会话）。
任何一条不满足就拒绝，不读私聊。
"""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from _common import lark_json
from chat_context import fmt


def owner_open_id():
    d = lark_json(["contact", "+get-user", "--as", "user"])
    u = (d.get("data") or {}).get("user") or d.get("data") or {}
    oid = u.get("open_id")
    if not oid:
        raise SystemExit("取不到群主本人的 open_id（lark-cli 用户身份没登录？）")
    return oid, u.get("name", "")


def check_trigger(trigger, owner_id, name):
    d = lark_json(["im", "+messages-mget", "--as", "user", "--message-ids", trigger])
    msgs = (d.get("data") or {}).get("messages") or []
    if not msgs:
        raise SystemExit(f"[拒绝] 读不到触发消息 {trigger}")
    m = msgs[0]
    sender = (m.get("sender") or {}).get("id")
    if sender != owner_id:
        raise SystemExit("[拒绝] 只有群主本人 @机器人 时才能读群主的私聊，这次触发人不是群主")
    if name not in (m.get("content") or ""):
        raise SystemExit(f"[拒绝] 触发消息里没有点名「{name}」，不读私聊。请群主在 @机器人 的消息里写明要看和谁的对话")
    return m


def find_peer(name):
    d = lark_json(["contact", "+search-user", "--as", "user", "--query", name])
    users = (d.get("data") or {}).get("users") or []
    exact = [u for u in users if u.get("localized_name") == name] or users
    if not exact:
        raise SystemExit(f"[拒绝] 通讯录里找不到「{name}」")
    if len(exact) > 1:
        cands = "、".join(f"{u.get('localized_name')}（{u.get('department', '')}）" for u in exact[:5])
        raise SystemExit(f"[拒绝] 「{name}」匹配到多个人：{cands}。请群主写全名")
    u = exact[0]
    if not u.get("p2p_chat_id"):
        raise SystemExit(f"[拒绝] 群主和「{name}」没有私聊记录")
    return u


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trigger", required=True, help="本次 @机器人 的消息 ID（bridge_context 的 messageIds）")
    ap.add_argument("--with", dest="peer", required=True, help="对方姓名，必须出现在触发消息里")
    ap.add_argument("--days", type=int, default=7, help="往前读几天，默认 7，最多 30")
    ap.add_argument("--limit", type=int, default=50, help="最多读几条，默认 50，最多 200")
    ap.add_argument("--include-after", action="store_true", help="也读触发消息之后的私聊（默认不读）")
    ap.add_argument("--download-dir", help="把图片 / 文件下载到这个目录（截图里常有报错）")
    a = ap.parse_args()

    name = a.peer.strip().lstrip("@")
    owner_id, owner_name = owner_open_id()
    trig = check_trigger(a.trigger, owner_id, name)
    peer = find_peer(name)

    days = max(1, min(a.days, 30))
    limit = max(1, min(a.limit, 200))
    cst = timezone(timedelta(hours=8))
    # 默认只读到触发消息那一分钟为止：群主 @机器人 之后私聊里聊的别的事不读
    end = datetime.strptime(trig["create_time"], "%Y-%m-%d %H:%M").replace(tzinfo=cst) + timedelta(minutes=1)
    if a.include_after:
        end = datetime.now(cst)
    start = end - timedelta(days=days)
    fmt_t = "%Y-%m-%dT%H:%M:%S+08:00"
    args = ["im", "+chat-messages-list", "--as", "user", "--chat-id", peer["p2p_chat_id"],
            "--start", start.strftime(fmt_t), "--end", end.strftime(fmt_t), "--order", "desc", "--no-reactions",
            "--page-size", str(min(limit, 50))]
    if limit > 50:
        args += ["--page-all", "--page-limit", str((limit + 49) // 50)]
    cwd = None
    if a.download_dir:
        Path(a.download_dir).mkdir(parents=True, exist_ok=True)
        cwd = a.download_dir
        args.append("--download-resources")
    d = lark_json(args, cwd=cwd)

    data = d.get("data", {})
    msgs = (data.get("messages") or data.get("items") or [])[:limit]
    msgs.sort(key=lambda m: (m.get("create_time", ""), m.get("message_position", "")))
    print(f"--- {owner_name} 与 {peer.get('localized_name')}（{peer.get('department', '')}）的私聊，{start:%m-%d %H:%M} ~ {end:%m-%d %H:%M}")
    for m in msgs:
        print(fmt(m))
    print(f"--- 共 {len(msgs)} 条（按时间正序）")
    if a.download_dir:
        res = Path(a.download_dir) / "lark-im-resources"
        files = sorted(p for p in res.rglob("*") if p.is_file()) if res.exists() else []
        for p in files:
            print(f"[附件] {p.resolve().as_posix()}")


if __name__ == "__main__":
    main()
