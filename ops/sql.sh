#!/usr/bin/env bash
# 让部署后检查能读写容器化部署里的那个数据库文件。
#
# 数据库默认落在命名卷里，宿主上没有对应路径（Windows / macOS 更是只能用命名卷，
# 见 docker-compose.yml 的说明）。smoke 又必须能查表数量、迁移版本、加密落地，
# 还要把一条 next_trigger_at 置为过去。所以给它一条统一的入口，而不是让 runner
# 自己去猜数据库在哪。
#
# 用法：
#   echo "SELECT count(*) FROM wishes" | bash ops/sql.sh query   → JSON 行数组
#   bash ops/sql.sh stat                                          → .db 的权限位（八进制）
#   bash ops/sql.sh pragma journal_mode                           → PRAGMA 取值
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SERVICE="${SQL_SERVICE:-api}"
mode="${1:-query}"

# 统一的容器内取数脚本。SQL / PRAGMA 名从 argv 进去，不做字符串拼接。
PY='
import json, os, sqlite3, sys
path = os.environ["DATABASE_URL"].split("///")[-1]
con = sqlite3.connect(path, timeout=10)
mode, arg = sys.argv[1], sys.argv[2]
try:
    if mode == "pragma":
        print(con.execute("PRAGMA " + arg).fetchone()[0])
    else:
        rows = [list(r) for r in con.execute(arg).fetchall()]
        con.commit()
        # BLOB 用 latin-1 转成可 JSON 化的字符串：调用方要判断密文里有没有明文
        enc = lambda v: v.decode("latin-1") if isinstance(v, (bytes, bytearray)) else v
        json.dump([[enc(c) for c in r] for r in rows], sys.stdout, ensure_ascii=False)
finally:
    con.close()
'

case "$mode" in
  query)
    docker compose exec -T "$SERVICE" python -c "$PY" query "$(cat)"
    ;;
  pragma)
    docker compose exec -T "$SERVICE" python -c "$PY" pragma "${2:?pragma 名称必填}"
    ;;
  stat)
    # 路径按 Python 那套同样的规则推导：`sqlite+aiosqlite:////data/x.db` 的
    # 文件路径是 `/data/x.db`，用 shell 的 `##*///` 会把开头的斜杠一起吃掉。
    docker compose exec -T "$SERVICE" python -c '
import os, stat
path = os.environ["DATABASE_URL"].split("///")[-1]
print(oct(stat.S_IMODE(os.stat(path).st_mode))[2:])
'
    ;;
  *)
    echo "未知模式：$mode（支持 query | pragma | stat）" >&2
    exit 2
    ;;
esac
