#!/usr/bin/env bash
# 迁移前备份（部署方案 §5「迁移前备份」+ §3.3「WAL 文件」）。
#
# SQLite 的 batch_alter_table 是「建新表 → 拷数据 → 换名」，失败时回滚依赖文件副本
# 而不是事务。所以这一步不是可选的加固，是回滚策略能成立的前提。
#
# 备份前先 checkpoint：-wal 里可能还压着已提交但没落主文件的事务，
# 只复制主文件等于备份了一个旧状态。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DEST="${1:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$DEST"

echo "==> checkpoint WAL"
docker compose exec -T api python -c "
import sqlite3
con = sqlite3.connect('/data/unhappened.db')
con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
con.close()
print('wal checkpointed')
"

echo "==> 复制数据库文件"
docker compose cp api:/data/unhappened.db "$DEST/unhappened-$STAMP.db"
chmod 600 "$DEST/unhappened-$STAMP.db"

echo "backup-db: $DEST/unhappened-$STAMP.db"
echo "提醒：ENCRYPTION_KEY 必须与这份备份分开存放——放在一起等于没加密。"
