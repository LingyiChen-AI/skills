"""拉取群聊上下文（用户身份），按时间正序输出精简文本。

  python chat_context.py --chat-id oc_xxx [--limit 30]
  python chat_context.py --message-ids om_a,om_b      # 指定消息（如被引用的消息）
"""
import argparse

from _common import lark_json


def fmt(m):
    sender = (m.get("sender") or {}).get("name") or (m.get("sender") or {}).get("id", "?")
    content = "[已撤回]" if m.get("deleted") else (m.get("content") or "").replace("\r", "")
    reply = f" ↩{m['reply_to']}" if m.get("reply_to") else ""
    return f"[{m.get('create_time', '')}] {sender} ({m.get('msg_type', '')}, {m.get('message_id', '')}{reply}):\n{content}\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chat-id")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--message-ids")
    a = ap.parse_args()

    if a.message_ids:
        d = lark_json(["im", "+messages-mget", "--as", "user", "--message-ids", a.message_ids])
    elif a.chat_id:
        n = max(1, min(a.limit, 100))
        d = lark_json(["im", "+chat-messages-list", "--as", "user", "--chat-id", a.chat_id,
                       "--page-size", str(n), "--order", "desc"])
    else:
        raise SystemExit("需要 --chat-id 或 --message-ids")

    data = d.get("data", {})
    msgs = data.get("messages") or data.get("items") or []
    msgs.sort(key=lambda m: (m.get("create_time", ""), m.get("message_position", "")))
    for m in msgs:
        print(fmt(m))
    print(f"--- 共 {len(msgs)} 条（按时间正序）")


if __name__ == "__main__":
    main()
