#!/usr/bin/env bash
# 部署后检查（部署方案 §7 的 12 项）。任一失败即判定发布失败。
#
# 它不重新实现断言：12 项检查已经逐项映射到 SMOKE-core-01..18
# （见 logos/resources/test/smoke/core-smoke-test-cases.md 第三节的映射表），
# 所以这里的职责只有两件——先确认密钥齐备，再把 smoke 跑完。
# 两处实现同一批断言，迟早会漂移成两套结论。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${APP_ENV:?APP_ENV 必须显式设置（staging | production）}"
: "${SMOKE_BASE_URL:?SMOKE_BASE_URL 必须指向本次发布的 API 根}"
export SMOKE_ENV="${SMOKE_ENV:-$APP_ENV}"
export SMOKE_WEB_URL="${SMOKE_WEB_URL:-$SMOKE_BASE_URL}"

echo "==> [1/2] 环境变量与密钥（§7-11）"
bash ops/check-env.sh || exit 1

echo "==> [2/2] 冒烟测试（§7 的其余 11 项，逐项映射到 SMOKE-core-*）"
node scripts/run-smoke.js
smoke_status=$?

results="${OPENLOGOS_SMOKE_RESULT_PATH:-logos/resources/verify/smoke-results.jsonl}"
if [[ -f "$results" ]]; then
  echo "==> 失败项："
  grep '"status": *"fail"' "$results" || echo "  （无）"
fi

if (( smoke_status != 0 )); then
  echo "post-deploy-check: FAILED —— 按部署方案第六节回滚"
  exit 1
fi
echo "post-deploy-check: OK"
