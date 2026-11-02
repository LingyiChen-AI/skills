"""生产库只读查询（带护栏）。库在 config.json 的 dbs 里登记，口令运行时从 dsn.file 读取，不复制。

  python prodq.py --list
  python prodq.py --db voc_config "SELECT id, name FROM xxx WHERE shop_id = 123"
  python prodq.py --db sr_voc --limit 20 "SELECT ... WHERE dt = '2026-11-01' AND shop_id = 1"
  python prodq.py --db csr "SHOW CREATE TABLE biz_shop"

护栏：
  - 只允许单条 SELECT / WITH / SHOW / DESC / DESCRIBE / EXPLAIN，拦截写操作、锁、导出
  - SELECT 不写 LIMIT 自动补（默认 50），LIMIT 上限 200
  - 聚合 / 去重必须带 WHERE
  - MySQL 会话 READ ONLY + 15s 超时；StarRocks query_timeout=15
  - 长字段截断到 300 字
"""
import argparse
import re
import socket
import subprocess
import sys
import time

from _common import expand, load_config

try:
    import pymysql
except ImportError:
    raise SystemExit("缺少 pymysql：python -m pip install --user pymysql（不要用 python -I 运行本脚本）")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
CELL_MAX = 300
ALLOWED_FIRST = {"SELECT", "WITH", "SHOW", "DESC", "DESCRIBE", "EXPLAIN"}
FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|REPLACE|MERGE|UPSERT|CREATE|ALTER|DROP|TRUNCATE|RENAME|GRANT|REVOKE|"
    r"LOCK|UNLOCK|CALL|LOAD|HANDLER|KILL|SET|COMMIT|ROLLBACK|OUTFILE|DUMPFILE)\b|FOR\s+UPDATE|LOCK\s+IN\s+SHARE",
    re.I,
)
AGG = re.compile(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(|\bGROUP\s+BY\b|\bDISTINCT\b", re.I)
DSN_RE = re.compile(r'DSN:\s*"(?P<user>[^:"]+):(?P<pw>.*)@tcp\((?P<host>[^:)]+):(?P<port>\d+)\)/(?P<db>[^?"]+)')


def read_dsn(spec):
    """从 markdown 文档的指定小节里找 `DSN: "user:pw@tcp(host:port)/db?..."` 行。"""
    path = expand(spec["file"])
    if not path.exists():
        raise SystemExit(f"找不到口令文档 {path}")
    text = path.read_text(encoding="utf-8")
    section = spec.get("section")
    if section:
        m = re.search(rf"^{re.escape(section)}\s*$(.*?)(?=^#{{2,3}} |\Z)", text, re.M | re.S)
        if not m:
            raise SystemExit(f"口令文档里没找到小节「{section}」")
        text = m.group(1)
    for line in text.splitlines():
        d = DSN_RE.search(line)
        if d and d["db"] == spec["db"]:
            return d.groupdict()
    raise SystemExit(f"口令文档小节里没有库 {spec['db']} 的 DSN")


def port_open(port):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_tunnel(tcfg, host, port):
    local = tcfg["local_ports"].get(host)
    if local is None:
        return host, port  # 没登记隧道：直连
    if port_open(local):
        return "127.0.0.1", local
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        ["ssh", "-i", str(expand(tcfg["key"])), "-N", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30",
         "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-L", f"{local}:{host}:{port}", tcfg["jump"]],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags,
    )
    for _ in range(40):
        if port_open(local):
            return "127.0.0.1", local
        time.sleep(0.5)
    raise SystemExit(f"隧道 127.0.0.1:{local} → {host}:{port} 建立失败（跳板机 {tcfg['jump']}）")


def strip_comments(sql):
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"(--|#)[^\n]*", " ", sql)
    return sql.strip().rstrip(";").strip()


def check_and_limit(sql, limit):
    body = strip_comments(sql)
    if not body:
        raise SystemExit("SQL 为空")
    if ";" in body:
        raise SystemExit("只允许单条语句")
    first = body.split(None, 1)[0].upper()
    if first not in ALLOWED_FIRST:
        raise SystemExit(f"只允许 {sorted(ALLOWED_FIRST)}，收到 {first}")
    no_str = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", "''", body)
    bad = FORBIDDEN.search(no_str)
    if bad and first not in {"SHOW", "DESC", "DESCRIBE"}:
        raise SystemExit(f"拦截：含禁止关键字 {bad.group(0)}（生产只读）")
    if first in {"SELECT", "WITH"}:
        if AGG.search(no_str) and not re.search(r"\bWHERE\b", no_str, re.I):
            raise SystemExit("拦截：聚合/去重查询必须带 WHERE，用索引列/分区列/时间范围收窄后再查")
        m = re.search(r"\bLIMIT\s+(\d+)(?:\s*,\s*(\d+))?(?:\s+OFFSET\s+\d+)?\s*$", no_str, re.I)
        if m:
            n = int(m.group(2) or m.group(1))
            if n > MAX_LIMIT:
                raise SystemExit(f"LIMIT {n} 超过上限 {MAX_LIMIT}")
        else:
            body = f"{body}\nLIMIT {min(limit, MAX_LIMIT)}"
    return body


def cell(v):
    if v is None:
        return "NULL"
    if isinstance(v, (bytes, bytearray)):
        v = v.decode("utf-8", "replace")
    s = str(v).replace("\n", "\\n").replace("\t", " ")
    return s if len(s) <= CELL_MAX else s[:CELL_MAX] + f"…(共{len(s)}字)"


def connect(cfg, alias):
    db = cfg["dbs"][alias]
    dsn = read_dsn(db["dsn"])
    host, port = ensure_tunnel(cfg["tunnels"], dsn["host"], int(dsn["port"]))
    conn = pymysql.connect(host=host, port=port, user=dsn["user"], password=dsn["pw"], database=db["database"],
                           charset="utf8mb4", connect_timeout=10, read_timeout=30, ssl_disabled=True)
    with conn.cursor() as cur:
        if db["kind"] == "mysql":
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.execute("SET SESSION max_execution_time = 15000")
        else:
            cur.execute("SET query_timeout = 15")
    return conn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("sql", nargs="?")
    a = ap.parse_args()
    cfg = load_config()

    if a.list:
        for k, d in cfg["dbs"].items():
            used = [p for p, pc in cfg["projects"].items() if k in pc.get("dbs", [])]
            print(f"{k:18} {d['kind']:10} 库 {d['database']:18} 项目 {','.join(used)}")
        return
    if not a.db or not a.sql:
        ap.error("需要 --db 和 SQL")
    if a.db not in cfg["dbs"]:
        raise SystemExit(f"未登记的库 {a.db}，可用：{sorted(cfg['dbs'])}")

    sql = check_and_limit(a.sql, a.limit)
    conn = connect(cfg, a.db)
    try:
        with conn.cursor() as cur:
            t0 = time.time()
            cur.execute(sql)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            cost = time.time() - t0
    finally:
        conn.close()

    print(f"-- {a.db} ({cfg['dbs'][a.db]['database']}) | {len(rows)} 行 | {cost:.2f}s")
    print(f"-- SQL: {' '.join(sql.split())}")
    if cols:
        print("\t".join(cols))
    for r in rows:
        print("\t".join(cell(v) for v in r))


if __name__ == "__main__":
    main()
