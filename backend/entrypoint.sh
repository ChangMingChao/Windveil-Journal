#!/bin/sh
# 让 §3.3 的「`.db` 一律 600」成为结构性保证，而不是一次手工 chmod。
#
# SQLite 建文件时用的是进程 umask。默认 022 会建出 644——本次 staging 演练里
# SMOKE-core-05 就是这么发现的。umask 0077 让主文件、`-wal`、`-shm` 一出生就是 600。
#
# 顺带把已存在的文件收紧一次：镜像升级前留下的 644 文件不会因为改了 umask 而自动变。
set -e
umask 0077

db_path=$(python -c 'import os; print(os.environ.get("DATABASE_URL", "").split("///")[-1])' 2>/dev/null || true)
if [ -n "$db_path" ]; then
    for f in "$db_path" "$db_path-wal" "$db_path-shm"; do
        if [ -f "$f" ]; then chmod 600 "$f" 2>/dev/null || true; fi
    done
fi

exec "$@"
