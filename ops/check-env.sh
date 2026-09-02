#!/usr/bin/env bash
# 必需环境变量检查（部署方案 §7-11、SMOKE-core-03）。
#
# 一条铁律：**不打印任何密钥值**，只打印变量名与「是否非空 / 长度是否达标」。
# 一个主打私密的应用，把密钥打进 CI 日志比配置缺失更严重。
set -uo pipefail

APP_ENV="${APP_ENV:-local}"

# 所有环境都必需
REQUIRED=(
  APP_ENV
  APP_BASE_URL
  DATABASE_URL
  JWT_SECRET
  ENCRYPTION_KEY
  LLM_BASE_URL
  LLM_API_KEY
  LLM_MODEL
  ASR_BASE_URL
  ASR_API_KEY
  ASR_MODEL
)

# staging / production 额外必需：对象存储与投递通道
if [[ "$APP_ENV" == "staging" || "$APP_ENV" == "production" ]]; then
  REQUIRED+=(
    S3_ENDPOINT
    S3_BUCKET
    S3_ACCESS_KEY
    S3_SECRET_KEY
    SMTP_HOST
    SMTP_FROM
    VAPID_SUBJECT
  )
fi

# 最小长度要求。ENCRYPTION_KEY 丢失等于全部用户内容永久不可读，长度必须够
declare -A MIN_LEN=( [ENCRYPTION_KEY]=32 [JWT_SECRET]=32 )

fail=0
for name in "${REQUIRED[@]}"; do
  value="${!name:-}"
  if [[ -z "$value" ]]; then
    echo "MISSING  $name"
    fail=1
    continue
  fi
  min="${MIN_LEN[$name]:-0}"
  if (( ${#value} < min )); then
    echo "TOO_SHORT $name (len=${#value}, need >=$min)"
    fail=1
    continue
  fi
  echo "OK       $name (len=${#value})"
done

# 生产不允许留着开发默认值
for name in JWT_SECRET ENCRYPTION_KEY; do
  value="${!name:-}"
  if [[ "$APP_ENV" == "staging" || "$APP_ENV" == "production" ]] && [[ "$value" == dev-only-* ]]; then
    echo "DEV_DEFAULT $name still set to a dev-only placeholder"
    fail=1
  fi
done

if (( fail )); then
  echo "check-env: FAILED"
  exit 1
fi
echo "check-env: OK (${#REQUIRED[@]} variables)"
