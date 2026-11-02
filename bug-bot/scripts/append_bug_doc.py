"""把一条 bug 分析追加到群对应的飞书文档（本机 lark-cli 用户身份），并回读确认。

markdown 文件结构（第一行 "## " 开头，字段顺序固定）：

  ## <bug 标题>

  **复现步骤**

  1. ...

  **修复建议**

  1. ...（文件:行号）

  **提出人**：张三

  **提出时间**：2026-11-02 09:46

  python append_bug_doc.py --chat-id oc_xxx reports/2026-11-02-xxx.md   # 文档地址取 config.json 里该群的 doc_url
  python append_bug_doc.py --doc <飞书文档链接> reports/xxx.md
"""
import argparse
from pathlib import Path

from _common import lark_json, load_config

REQUIRED = ["复现步骤", "修复建议", "提出人", "提出时间"]


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--chat-id")
    g.add_argument("--doc")
    ap.add_argument("file")
    a = ap.parse_args()

    doc = a.doc
    if a.chat_id:
        grp = load_config()["groups"].get(a.chat_id)
        if not grp or not grp.get("doc_url"):
            raise SystemExit(f"config.json 里群 {a.chat_id} 没有配置 doc_url")
        doc = grp["doc_url"]

    path = Path(a.file).resolve()
    text = path.read_text(encoding="utf-8").strip()
    first = text.splitlines()[0] if text else ""
    if not first.startswith("## "):
        raise SystemExit("第一行必须是 '## <bug 标题>'")
    missing = [k for k in REQUIRED if k not in text]
    if missing:
        raise SystemExit(f"缺少字段：{missing}")
    pos = [text.find(k) for k in REQUIRED]
    if pos != sorted(pos):
        raise SystemExit(f"字段顺序必须是 {REQUIRED}")
    title = first[3:].strip()

    # lark-cli 的 @file 只接受相对路径，所以在文件所在目录执行
    lark_json(["docs", "+update", "--as", "user", "--doc", doc, "--command", "append",
               "--doc-format", "markdown", "--content", f"@{path.name}"], cwd=str(path.parent))
    content = lark_json(["docs", "+fetch", "--as", "user", "--doc", doc])["data"]["document"]["content"]
    if title not in content:
        raise SystemExit(f"回读没找到标题「{title}」，请检查文档")
    print(f"已写入并回读确认：{title}")
    print(doc)


if __name__ == "__main__":
    main()
