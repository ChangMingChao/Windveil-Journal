#!/usr/bin/env bash
# personal 局域网部署辅助脚本（个人自用的未跟踪辅助文件，非方法论交付物）。
#
# 与 ops/deploy.sh 的分工：首次部署/改版本仍走 ops/deploy.sh（构建镜像、迁移、建桶），
# 本脚本只管这套 personal 栈的日常启停，以及 caddy 的局域网 JSON 配置再生成。
#
# 两个固定差异：
#   * COMPOSE_PROJECT_NAME=personal —— 与 staging 演练（windveil-journal）完全隔离，
#     各自独立的卷与网络；
#   * caddy 用 ops/compose-personal-override.yml 挂载 ops/caddy-personal.json 跑原生
#     JSON 配置 —— 手机浏览器按 IP 访问不发 SNI，而 Caddy 2.8.4 的 Caddyfile 适配器
#     会丢弃全局 default_sni，只能注入 JSON 的 apps.tls.connection_policies。
#
# 用法：
#   bash ops/personal.sh up       # 启动全栈（先重生成 JSON 配置）
#   bash ops/personal.sh down     # 停止（保留数据卷）
#   bash ops/personal.sh ps       # 状态
#   bash ops/personal.sh logs     # 跟踪日志（可带服务名，如 logs caddy）
#   bash ops/personal.sh regen    # 仅重生成 caddy JSON（IP 变化后）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export COMPOSE_PROJECT_NAME=personal
COMPOSE=(docker compose -f docker-compose.yml -f ops/compose-personal-override.yml --profile storage)

# 从仓库 Caddyfile 重新适配 JSON 并注入 default_sni。
# IP 变化（DHCP/换网）后重跑：bash ops/personal.sh regen && bash ops/personal.sh up
regen() {
  set -a; source "$ROOT/.env"; set +a
  local ip="${SITE_ADDRESS:?SITE_ADDRESS 未设置}"
  local winroot; winroot="$(cygpath -m "$ROOT")"
  # MSYS_NO_PATHCONV=1 防止 Git Bash 把容器内路径 /tmp/Caddyfile 改写成宿主路径
  MSYS_NO_PATHCONV=1 docker run --rm -e SITE_ADDRESS="$ip" \
    -v "$winroot/Caddyfile:/tmp/Caddyfile:ro" \
    caddy:2.8-alpine caddy adapt --config /tmp/Caddyfile --adapter caddyfile \
    > "$ROOT/ops/.caddy-adapted.tmp.json"
  # node 收到 Windows 形式路径（Git Bash 会把 /f/... 转换成 F:/...）
  node "$ROOT/ops/.inject-default-sni.mjs" \
    "$(cygpath -m "$ROOT/ops/.caddy-adapted.tmp.json")" \
    "$(cygpath -m "$ROOT/ops/caddy-personal.json")" "$ip"
  rm -f "$ROOT/ops/.caddy-adapted.tmp.json"
  echo "已生成 ops/caddy-personal.json（default_sni=$ip）"
}

case "${1:-}" in
  up)    regen; "${COMPOSE[@]}" up -d ;;
  down)  "${COMPOSE[@]}" down ;;
  ps)    "${COMPOSE[@]}" ps ;;
  logs)  shift || true; "${COMPOSE[@]}" logs -f --tail=100 "$@" ;;
  regen) regen ;;
  *)     echo "用法: bash ops/personal.sh {up|down|ps|logs [服务]|regen}"; exit 1 ;;
esac
