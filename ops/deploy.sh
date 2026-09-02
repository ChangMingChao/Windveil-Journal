#!/usr/bin/env bash
# 发布（部署方案 §4.3，staging 与 production 相同）。
#
# 顺序是刻意的：scheduler 放最后，因为它是唯一会在无人值守时写数据的进程——
# 先让 api 在新 schema 上跑通、确认无误，再放它进来。
#
# 用法：
#   IMAGE_TAG=$(git rev-parse --short HEAD) bash ops/deploy.sh
#   （production 追加 --profile 决定是否启用自带 MinIO）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${IMAGE_TAG:?IMAGE_TAG 必须是本次发布的 git sha，不能用 latest}"
COMPOSE=(docker compose)
if [[ "${WITH_MINIO:-1}" == "1" ]]; then
  COMPOSE+=(--profile storage)
fi

echo "==> [0/6] 前置检查：环境变量与迁移可读性"
bash ops/check-env.sh
"${COMPOSE[@]}" config --quiet
mkdir -p /tmp/unhappened-release
"${COMPOSE[@]}" run --rm --no-deps api alembic upgrade head --sql \
  > /tmp/unhappened-release/migration.sql || true
echo "    迁移 SQL 已导出到 /tmp/unhappened-release/migration.sql —— 请人工过一眼再继续"

echo "==> [1/6] 构建镜像 unhappened-api:$IMAGE_TAG"
if docker image inspect "unhappened-api:$IMAGE_TAG" >/dev/null 2>&1; then
  # 同一个 tag 只该对应同一份产物，已存在就不重建：重建既没有意义，
  # 又会在只读镜像仓库或网络不稳的环境下白白引入一次失败。
  echo "    镜像已存在，跳过构建（tag 与产物一一对应）"
else
  "${COMPOSE[@]}" build api
fi

echo "==> [2/6] 迁移前备份（失败时靠这份文件回滚，不靠 alembic downgrade）"
if "${COMPOSE[@]}" ps --status running --services | grep -qx api; then
  bash ops/backup-db.sh ./backups
else
  echo "    api 未在运行（首次部署），跳过备份"
fi

echo "==> [3/6] 数据库迁移（先迁移后切流）"
"${COMPOSE[@]}" run --rm --no-deps api alembic upgrade head

echo "==> [4/6] 发布 api"
if [[ "${WITH_MINIO:-1}" == "1" ]]; then
  # 对象存储是依赖服务而不是发布单元，但它必须先在：api 起来之后第一次签发
  # 预签名就会去连它。bucket 用 api 镜像里的 boto3 创建，不额外拉一个 mc 镜像。
  echo "    启动自带对象存储并确认 bucket 存在"
  "${COMPOSE[@]}" up -d minio
  "${COMPOSE[@]}" run --rm --no-deps api python -c "
import os, boto3, botocore
s3 = boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT'],
                  aws_access_key_id=os.environ['S3_ACCESS_KEY'],
                  aws_secret_access_key=os.environ['S3_SECRET_KEY'])
bucket = os.environ['S3_BUCKET']
try:
    s3.head_bucket(Bucket=bucket)
    print('bucket exists:', bucket)
except botocore.exceptions.ClientError:
    s3.create_bucket(Bucket=bucket)
    print('bucket created:', bucket)
"
fi
"${COMPOSE[@]}" up -d --no-deps api

echo "==> [5/6] 发布静态站点与入口"
"${COMPOSE[@]}" up -d --no-deps web caddy

echo "==> [6/6] 重启 scheduler（最后，确保跑的是新代码 + 新 schema）"
"${COMPOSE[@]}" up -d --no-deps --force-recreate scheduler

echo
echo "deploy: 完成。回滚点："
echo "  应用   docker compose up -d  指回上一个 IMAGE_TAG"
echo "  数据库 直接恢复 ./backups 下迁移前的 .db 副本（单文件数据库的回滚就是一次文件替换）"
echo
echo "接下来执行部署后检查："
echo "  APP_ENV=$APP_ENV SMOKE_BASE_URL=<站点> bash ops/post-deploy-check.sh"
