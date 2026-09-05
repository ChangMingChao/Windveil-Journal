# api 与 scheduler 共享同一镜像，只是入口命令不同（部署方案 §2 拓扑取舍 2）——
# 避免两套构建产物版本漂移。
#
# 两条与这个产品直接相关的选择：
#   * 非 root 运行，且 /data 的属主是它。`.db` 与 WAL 文件要求 600 权限
#     （§3.3），root 跑起来这条约束就没有意义了。
#   * 不装任何编译工具链到最终镜像。cryptography / argon2-cffi 都有 wheel，
#     装不上说明平台不对，应该当场失败而不是悄悄编译出一个不一样的东西。

FROM python:3.12-slim AS builder

# uv 从官方 distroless 镜像取，版本钉死（部署方案：镜像 tag 一律不用 latest）
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

# PyPI 镜像源可按构建环境覆盖（默认官方源）：网络受限的本机构建传
# --build-arg UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple。
# 只影响依赖下载，不改变锁定的版本解析。
ARG UV_DEFAULT_INDEX=https://pypi.org/simple
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_DEFAULT_INDEX=${UV_DEFAULT_INDEX}

WORKDIR /src
COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

# 非 editable 安装（`uv pip install .` 的默认行为）：产物要能脱离 /src 运行
RUN uv pip install --system --no-cache .

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC

# tzdata 是 timing.py 计算季节与自然周的依赖（按用户时区），不是可选项
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 unhappened \
 && mkdir -p /data /objects \
 && chown -R unhappened:unhappened /data /objects

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/alembic /usr/local/bin/uvicorn /usr/local/bin/

WORKDIR /app
COPY --chown=unhappened:unhappened app ./app
COPY --chown=unhappened:unhappened migrations ./migrations
COPY --chown=unhappened:unhappened alembic.ini ./
COPY --chown=unhappened:unhappened entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh

USER unhappened
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

# entrypoint 只做一件事：把 umask 收到 0077 再 exec —— 让「`.db` 一律 600」
# 落在文件创建的那一刻，而不是靠部署脚本事后补 chmod（§3.3）
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
