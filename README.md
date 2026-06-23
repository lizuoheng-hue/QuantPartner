# QuantPartner 开放公测版

QuantPartner 将自然语言交易想法转换为可审阅的结构化策略，通过可复现的回测引擎验证，并用可解释的指标和图表呈现结果。项目已经结束路演阶段，当前目标是建设可对外开放公测的产品化版本。

## 快速开始

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000/docs

未配置行情或模型密钥时，本地开发环境会使用确定性的演示行情与规则解析器。开放公测环境禁止静默降级为演示行情，必须明确返回数据源状态。

### 本地开发

一键启动两个服务（后台运行）：

```bash
./scripts/start-local.sh
```

停止服务：

```bash
./scripts/stop-local.sh
```

也可以分别启动：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

## 核心约束

- LLM 只生成经过 Pydantic 校验的 `StrategySpecV1`，不执行模型生成的任意代码。
- Python 代码预览由结构化策略确定性生成。
- 交易信号在 T 日收盘生成，最早于 T+1 开盘成交。
- 所有税费参数均通过环境变量配置。
- 数据市场覆盖沪深 300、港股和美股，历史区间为 2019 年至最新可用交易日。
- 模拟盘交易属于开放公测范围；实盘交易通过统一交易网关预留并默认关闭，完成实名、适当性、风控、审计和合规审查后方可启用。
- 禁止收益承诺和未经用户确认的个股推荐或自动下单。

## 当前阶段

- 交付目标：开放公测，而非路演演示。
- 现有单一演示工作区仅用于本地开发和迁移期验证。
- 产品化必须补齐账号体系、租户/工作区隔离、全市场数据、持久任务队列、权限、审计与监控。
- 详细范围与发布门槛见 [产品化计划](docs/PRODUCTIZATION_PLAN.md)。

## 已落地的公测基础能力

- 邮箱密码注册、登录、30 天可撤销会话和 PBKDF2 密码哈希。
- 用户、工作区、策略、版本、回测、订单和审计事件的服务端隔离。
- PostgreSQL/Alembic 迁移基线；公测环境使用 Redis 持久任务队列和独立 worker。
- `CN_A`、`HK`、`US` 三市场策略契约，以及沪深300、恒生指数、标普500基准映射。
- 模拟订单提交、幂等、查询、撤单和审计；实盘默认关闭。
- 公测环境行情失败关闭，禁止静默降级为演示数据。

当前港股、美股真实行情以及实盘券商适配器需要配置有授权的数据供应商和券商凭据；本地开发会明确显示“演示数据”。

### 三市场真实行情

- A 股/沪深300基准：Tushare Pro `index_daily`。
- 港股/恒生指数基准：Twelve Data 日线，供应商代码默认 `HSI`。
- 美股/标普500基准：Twelve Data 日线，供应商代码默认 `SPY`。

在项目根目录创建 `.env`：

```bash
cp .env.example .env
```

至少填写：

```dotenv
TUSHARE_TOKEN=你的_token
TWELVE_DATA_API_KEY=你的_api_key
```

首次同步并校验 2019 年至最新数据：

```bash
cd backend
python -m scripts.sync_market_data
```

原始规范化快照保存在 `backend/data/cache/{provider}/{market}/`。每个 CSV 都有对应的 `.meta.json`，记录供应商、市场、证券、下载时间、日期范围、行数和内容哈希。Docker 使用 `market_data_cache` 持久卷在 API 与 worker 间共享数据。

数据库不保存整张日线行情，而是保存 `market_data_snapshots` 快照登记表：供应商、市场、symbol、日期范围、频率、行数、内容哈希、文件路径和抓取时间。每次回测完成后，`backtests.data_snapshot_id` 会关联到本次使用的快照，接口结果也会返回 `result.data_snapshot`，用于追溯和复现。

查询运行状态：`GET /api/v1/data/status`。设置 `APP_ENV=beta` 或 `production` 后，任何缺少密钥、空数据、非法价格或哈希不一致都会终止回测，绝不使用演示数据代替。

查询已登记快照：`GET /api/v1/data/snapshots`，需要登录后的 Bearer Token。

### 数据库迁移与任务 worker

```bash
cd backend
alembic upgrade head
python -m app.worker
```

Docker Compose 已包含 `api`、`worker`、`postgres`、`redis` 和 `web` 服务。部署公测环境时设置 `APP_ENV=beta`，否则本地开发默认使用进程内任务与确定性测试行情。

### 新增 API

- `POST /api/v1/auth/register`、`/auth/login`、`/auth/logout`
- `GET /api/v1/auth/me`、`/audit-events`
- `POST/GET /api/v1/paper/orders`
- `DELETE /api/v1/paper/orders/{id}`

## 测试

```bash
cd backend && pytest
cd frontend && npm run lint && npm run build
```

详见 [演示手册](docs/DEMO.md) 与 [架构说明](docs/ARCHITECTURE.md)。

重置本地演示工作区：

```bash
cd backend
python -m scripts.reset_demo
```
