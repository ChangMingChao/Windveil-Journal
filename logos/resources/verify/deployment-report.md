# 部署报告（Phase 3-7）

> 生成时间：2026-09-02｜模块：core｜目标环境：`staging`
> 执行依据：`logos/resources/prd/3-technical-plan/3-deployment/core-01-deployment-plan.md` §4.3
> 授权：用户明确选择「产出并部署到 staging，然后跑 `SMOKE_ENV=staging ops/post-deploy-check.sh`」

## 一、目标环境的真实形态（先说清楚）

这次部署的 `staging` 是**本机单机演练**，不是远程主机：

| 项 | 本次实际 | 部署方案预期 |
|----|---------|-------------|
| 宿主 | 本机 Docker Desktop（WSL2 后端） | 任意 VPS / 云主机 |
| 站点地址 | `SITE_ADDRESS=localhost` | 真实单域名 |
| 证书 | Caddy 本地 CA 签发的内部证书 | Let's Encrypt 自动签发 |
| 对象存储 | 自带 MinIO（`--profile storage`） | staging 同此；production 可换云 OSS |
| 外部 LLM / ASR | 无可用端点（走降级路径） | 真实供应商端点 |

因此两项检查按环境事实处理：`SMOKE-core-17`（证书剩余有效期 >14 天）对内部 CA
不适用而记 skip；`SMOKE-core-10` 因为没有 LLM 端点走了降级路径，按 §8.3 的分层断言
判 PASS 并带 warning。其余 16 项全部真实执行通过。

## 二、执行命令摘要

全部经 `ops/deploy.sh`（§4.3 的六步）执行，未跑方案之外的命令：

```text
[0/6] ops/check-env.sh + docker compose config --quiet
      + alembic upgrade head --sql  → /tmp/unhappened-release/migration.sql（人工过目）
[1/6] docker build -t unhappened-api:<IMAGE_TAG> ./backend
[2/6] ops/backup-db.sh ./backups        （首次部署时自动跳过）
[3/6] docker compose run --rm --no-deps api alembic upgrade head
[4/6] docker compose up -d minio + 建 bucket + up -d --no-deps api
[5/6] docker compose up -d --no-deps web caddy
[6/6] docker compose up -d --no-deps --force-recreate scheduler
```

`scheduler` 放在最后是刻意的：它是唯一会在无人值守时写数据的进程，
先让 `api` 在新 schema 上跑通再放它进来。

## 三、迁移结果

```text
alembic upgrade head → 0006_batch7_scheduler_heartbeat
0001_batch1_core → 0002_batch3_reminders → 0003_batch4_steps
→ 0004_batch5_orphans → 0005_batch6_memories → 0006_batch7_scheduler_heartbeat
```

部署后核对（`SMOKE-core-06/07`）：`alembic_version` = `0006_batch7_scheduler_heartbeat`，
17 张表、28 个 `idx_` 索引全部存在。§3.2 警告的「配错 DATABASE_URL 会建出一个空库
且不报错」正是靠这两项挡住。

## 四、服务启动结果

| 单元 | 镜像 | 状态 |
|------|------|------|
| `api` | `unhappened-api:staging-20260902T090037Z` | Up (healthy) |
| `scheduler` | 同一镜像，入口 `python -m app.scheduler` | Up (healthy) |
| `web` | `nginx:1.27-alpine` + `frontend/dist` 只读挂载 | Up |
| `caddy` | `caddy:2.8-alpine` | Up，80/443 |
| `minio` | `minio/minio:RELEASE.2024-10-13T13-34-11Z` | Up（`storage` profile） |

`/api/v1/health` 返回 `status=ok`、`database=ok`、`scheduler_heartbeat_age_seconds`
在 0–300 秒之间随扫描周期锯齿变化（阈值 900）。

## 五、部署后检查

`APP_ENV=staging bash ops/post-deploy-check.sh` → **OK**

```text
18 条结果：17 pass / 0 fail / 1 skip
skip：SMOKE-core-17（证书由 Caddy Local Authority 签发，公网有效期检查不适用）
```

§7 的 12 项检查逐项映射到 `SMOKE-core-*`，没有第二套实现——两处实现同一批断言迟早
会漂移成两套结论。

## 六、回滚点

| 层 | 回滚动作 |
|----|---------|
| 应用 | `.env` 的 `IMAGE_TAG` 指回上一个 tag，`bash ops/deploy.sh` 重跑（镜像按 tag 一一对应，不用 latest） |
| 数据库 | 直接恢复 `./backups/unhappened-<时间戳>.db`——单文件数据库的回滚就是一次文件替换，比 `alembic downgrade` 可靠 |
| 对象存储 | 不回滚。媒体只增不改 |
| 提醒队列 | 回滚前先 `docker compose stop scheduler`，避免旧代码消费新格式的 `reminder_outbox` |

本次是首次部署，`./backups` 为空（步骤 2 自动跳过）。**下一次部署会产出备份，
那之后数据库层才真正有回滚点。**

## 七、部署过程中发现并修正的缺陷

这一节是本次部署最有价值的产出：以下六个问题只有真跑起来才会暴露，
单元测试与场景测试全绿的情况下它们全部存在。

1. **`local` / 容器里调度进程的文件锁落在不可写目录。** 锁路径原本按
   `LOCAL_STORAGE_DIR` 的父目录推导，在镜像里指向 `/app`（属 root），
   非 root 运行的进程每一轮都 `PermissionError`，而且只能通过心跳超时间接发现。
   已改为按 `DATABASE_URL` 推导——锁守护的正是那个数据库文件，放在它旁边。

2. **`scheduler` 沿用了 api 的 HTTP 健康探针。** 它不监听 HTTP，结果是永久
   `unhealthy`。已换成读心跳行的探针，与 §7-2 的判定标准一致。

3. **`scheduler` 完全没有日志。** `logging.basicConfig` 只在 `app.main` 里调用，
   而 `python -m app.scheduler` 不会导入它——一个每轮都失败的调度进程在日志里
   安静得像什么都没发生。第 1 条的排查因此多花了一轮。已抽出 `app/obs.py`，
   两个入口都装配。

4. **`S3_PUBLIC_BASE` 是一个从未被使用的配置项。** 预签名 URL 按 `S3_ENDPOINT`
   （`http://minio:9000`）签发并直接交给浏览器，而浏览器解析不了这个内网主机名——
   **线上每一次上传都会失败**。已改为按对外地址签名，并据此重排 Caddy 路由（见下）。

5. **对象存储的反代路由形状原本是错的。** 第 4 条改完后签名仍然 `SignatureDoesNotMatch`：
   SigV4 把 Host **和整条路径**都签进签名，而 `handle_path /media/*` 会剥掉前缀。
   路径不能改，对外前缀就只能等于 bucket 名。已改为 `handle /<bucket>/*` +
   `header_up Host {host}`，`S3_PUBLIC_BASE` 相应改为站点根（不带后缀）。

6. **数据库文件权限是 644，不是 §3.3 要求的 600。** SQLite 按进程 umask 建文件。
   已加 `backend/entrypoint.sh`：`umask 0077` 后再 exec，并对已存在的
   主文件 / `-wal` / `-shm` 收紧一次——让 600 落在文件创建的那一刻，
   而不是靠部署脚本事后补 chmod。

另有两处是 smoke runner 自身的问题，一并修掉了：用例间的隐式执行顺序依赖
（`SMOKE-core-08` 需要 `SMOKE-core-10` 先建愿望，空 id 会让 URL 退化成列表端点，
B 反而拿到 200）；以及 `subprocess` 按本机 locale 解码容器输出，
BLOB 往返时炸在一个莫名的汉字上（已固定 UTF-8）。

## 八、未解决风险

| 风险 | 说明 | 影响 |
|------|------|------|
| Windows / macOS 宿主目录 + SQLite WAL 不可用 | WAL 需要 `-shm` 共享内存映射，Docker Desktop 的 9p / gRPC-FUSE 挂载不支持。`api` 与 `scheduler` 同时打开同一文件会 `disk I/O error` | 已在 compose 注释里写明并默认命名卷。**Linux 宿主的 bind mount 无此限制**，但若有人在 Windows 上照 `DB_DIR=./data` 部署会踩到 |
| 文件锁没有陈旧检测 | 进程被 SIGKILL 后锁文件残留，`O_EXCL` 会让后续每一轮都拿不到锁，调度**永久停摆**，唯一信号是心跳超时 | `restart: unless-stopped` 下真实可能发生。修它要改并发语义并补测试，本次刻意没顺手做 |
| 未演练回滚 | §6 要求 staging 每次发布后做一次 `downgrade -1` + `upgrade head` | 首次部署无上一版本可回，下次发布应补 |
| 无远程 staging | 证书、真实域名、公网可达性、Web Push 均未验证 | `SMOKE-core-17` 记 skip；Web Push 与 Service Worker 强制 HTTPS，真实证书下才算验证过 |
| `.env` 落在工作区 | 本次演练用的 `.env` 含本机生成的 `ENCRYPTION_KEY` | 已 `chmod 600` 并加入 `.gitignore`。**这些密钥只用于本机演练，不要复用到任何真实环境** |
| Docker Hub 拉取不稳定 | 构建期 `auth.docker.io` 的 DNS 被解析到无关地址，多次失败 | 已把基础镜像拉到本地并用 `--pull=false` 构建；CI 环境需要镜像缓存或私有仓库 |



## preferences-availability-timing 增量部署演练（2026-09-04）

> 目标环境：本机 `staging`（与 Phase 3-7 相同形态）｜镜像 `unhappened-api:eaaa893`｜授权：用户选择「本地部署演练」

### 执行摘要

| 步骤 | 结果 |
|------|------|
| 迁移前备份 | ✅ `ops/backup-db.sh` 真实执行（库非空，WAL checkpoint + 文件复制） |
| 迁移 0007 → 0008 | ✅ 三张新表 + 7 索引；部署后核对 20 张表 / 36 索引（SMOKE-core-06/07） |
| api / web / caddy / scheduler / minio | ✅ 全部 `unhappened-api:eaaa893`（web 为 nginx:1.27-alpine）就位，api healthy |
| 部署后检查 + smoke | ✅ 19 pass / 1 skip（SMOKE-core-17 内部 CA，预期）/ 0 fail；**SMOKE-core-19/20 首次真实执行通过** |

### 过程中发现并修正的问题（四处）

1. **迁移 0008 的 `op.exec_driver_sql` 不存在**——改为与 0005 相同的逐条 `op.execute`。
2. **DDL 注释里的 JSON 示例（`{"valid":true,...}`）在 `text()` 参数解析下炸出绑定参数错误**——`upgrade()` 改为 `bind.exec_driver_sql()` 逐条下发，跳过参数解析。第一次在线迁移因此半建（user_preferences / availability_windows 已建、timing_proposals 未建），已清理半建对象后干净重跑（三张空表无数据依赖，备份在手）。
3. **0007 迁移的离线模式缺陷（既有问题）**：deploy.sh 第 0 步 `alembic upgrade head --sql` 在 0007 的 `exec_driver_sql("PRAGMA ...")` 上失败，被 `|| true` 吞掉——不阻塞部署，但「迁移 SQL 人工过目」这一道防线实际从未生效，后续提案应修复 0007 的离线分支。
4. **smoke runner 的三处执行缺陷（既有问题，本次首次在 compose 路径暴露）**：
   - smoke_12 的 `docker compose run` 缺 `--no-deps`，会以「配置漂移」为由重建 api 依赖，令后续用例撞 502 窗口；
   - 镜像 ENTRYPOINT（entrypoint.sh）吞掉 `--once` 参数——默认 compose 路径此前从未真正通过，改为 `--entrypoint python scheduler -m app.scheduler --once`；
   - 本机演练需显式 `SMOKE_DB_CMD="bash ops/sql.sh"`（数据库在命名卷内）与 `IMAGE_TAG`（缺失时 compose run 会重建依赖）。

### 环境事实

- `ops/local-ca.crt` 已从当前 Caddy 数据卷重新导出（CA 与卷绑定，卷重建即变）；
- `SMOKE-core-10` 走降级路径 PASS 并带 warning（本机无真实 LLM 端点，.env 补了占位值）；
- `SMOKE-core-18` 日志明文抽查以 warning 记录（未提供 SMOKE_LOG_CMD）。
