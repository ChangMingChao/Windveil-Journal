# 风启簿 · Windveil Journal

> Wait for the wind, then set forth. 等风来，再启程。

风是时机，簿是心愿册。Windveil 取「风掀起帷幕，心愿由此开启」。这是一个个人愿望陪伴产品，收集那些你不想错过的未来，并在你准备好时，陪你慢慢发生。

这里不是待办清单。它不计算逾期，不强调连续打卡，也不把未完成变成新的压力。适合放在这里的，是那些暂未开始、但值得被认真对待的事。

## 产品能力

- 匿名建立私人空间，用一句话、语音或照片随手种下一个愿望。
- Agent 提炼愿望中的感受、隐含条件与最小下一步；模型不可用时仍会先保存原话。
- 用季节、月份、空闲周末、疲惫信号等方式约定时机，让提醒在对的时候出现。
- 每位用户每周最多收到 3 条主动提醒，并支持顺延、暂停、安静放下与重新种下。
- 愿望发生后可以写成记忆页，长期沉淀为「已发生之书」。
- 内容按用户隔离，敏感字段使用应用层 AES-256-GCM 加密，媒体保存在 S3 兼容对象存储。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite 6、React Router 7、TanStack Query、Tailwind CSS 4、PWA |
| 后端 | FastAPI、Pydantic v2、SQLAlchemy 2.0 async、Alembic、APScheduler |
| 数据库 | SQLite 单文件，启用 WAL |
| 对象存储 | S3 兼容协议，本地开发使用文件系统后端，部署可选 MinIO 或云 OSS |
| 认证 | Argon2id、JWT access/refresh，refresh token 存 httpOnly Cookie |
| 部署 | Docker Compose、Caddy、Nginx、Uvicorn、独立 Scheduler 进程 |

## 目录结构

```text
frontend/                React 前端与静态站点构建
backend/                 FastAPI、迁移、调度器与测试
ops/                     部署、备份、环境检查与数据库运维脚本
scripts/                 冒烟测试与本地辅助脚本
logos/                   OpenLogos 需求、设计、API、测试与变更档案
docker-compose.yml       单机部署拓扑
.env.example             环境变量样例，不包含真实密钥
```

## 本地开发

准备 Python 3.12、uv、npm。如需媒体上传测试，准备可用的 Docker Compose 环境。

1. 安装依赖：

   ```bash
   cd backend
   uv sync --extra dev

   cd ../frontend
   npm install
   ```

2. 初始化数据库：

   ```bash
   cd backend
   uv run alembic upgrade head
   ```

3. 启动后端与调度器：

   ```bash
   uv run uvicorn app.main:app --reload --port 8000
   uv run python -m app.scheduler
   ```

4. 启动前端：

   ```bash
   cd frontend
   pnpm dev
   ```

默认访问入口是 `http://localhost:5173`，API 代理到 `http://127.0.0.1:8000`。后端 API 文档在 `http://127.0.0.1:8000/docs`。

本地环境默认使用 SQLite、本地文件对象存储和 mock 外部服务。纯文字功能无需启动 MinIO。

## 测试

后端：

```bash
cd backend
uv run pytest
uv run ruff check .
```

前端：

```bash
cd frontend
pnpm typecheck
pnpm test:run
pnpm build
```

## 构建

前端构建会产出 `frontend/dist`：

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm build
```

后端 API 与 Scheduler 共用同一个镜像：

```bash
docker build -t unhappened-api:<git-sha> ./backend
```

镜像 tag 使用当前 git sha，不使用 `latest`，以便发布和回滚都有确定目标。

## 部署

1. 复制并填写环境变量：

   ```bash
   cp .env.example .env
   chmod 600 .env
   ```

2. 使用项目根目录中的发布脚本：

   ```bash
   IMAGE_TAG=$(git rev-parse --short HEAD) bash ops/deploy.sh
   ```

发布流程会执行环境检查、导出迁移 SQL、备份数据库、应用迁移、更新 API、发布静态站点，最后重建 Scheduler。部署后可运行：

```bash
bash ops/post-deploy-check.sh
```

详细拓扑、迁移、回滚与冒烟检查见 [`logos/resources/prd/3-technical-plan/3-deployment/core-01-deployment-plan.md`](logos/resources/prd/3-technical-plan/3-deployment/core-01-deployment-plan.md)。

## 安全约定

- `.env` 不入库，其中包含数据库地址、JWT、加密密钥与外部服务凭证。
- `ENCRYPTION_KEY` 是唯一不可重建的密钥。丢失后已加密的用户内容将永久不可读。
- `ENCRYPTION_KEY` 与数据库备份必须分开存放，并保持至少两份离线冷备。
- 测试后门 `/api/test/*` 只在 `APP_ENV=test` 时注册。

## 开发流程

本项目使用 OpenLogos 管理 Why、What、How 三层文档。修改代码前先查看对应的变更提案；规格与实现必须保持可追溯。项目索引见 [`logos/logos-project.yaml`](logos/logos-project.yaml)。
