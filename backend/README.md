# NexusAI 后端

企业级智能知识库 + 多 Agent 协作平台的 FastAPI 后端服务。

---

## 1. 技术栈

| 类别 | 选型 |
|------|------|
| Web 框架 | FastAPI 0.115 |
| 数据库 | PostgreSQL + SQLAlchemy 2.0 + Alembic |
| 认证 | JWT (python-jose) + bcrypt (passlib) |
| 异步任务 | Celery 5 + Redis |
| 日志 | loguru |
| Python | 3.10+ |

---

## 2. 环境准备

### 2.1 安装 PostgreSQL

Windows 推荐方式（任选其一）：

**方式 A：官方安装包**
- 下载 https://www.postgresql.org/download/windows/
- 安装后记住 `postgres` 用户的密码，默认端口 `5432`

**方式 B：Docker（推荐）**

```powershell
docker run -d --name nexus-postgres `
  -e POSTGRES_USER=postgres `
  -e POSTGRES_PASSWORD=postgres `
  -e POSTGRES_DB=nexus_ai `
  -p 5432:5432 `
  postgres:16
```

### 2.2 安装 Redis

Windows 上 Redis 官方不再维护，推荐 Docker：

```powershell
docker run -d --name nexus-redis -p 6379:6379 redis:7
```

或使用 Memurai（Windows 原生 Redis 替代品）。

### 2.3 创建数据库

如果未通过 Docker 自动创建：

```sql
CREATE DATABASE nexus_ai;
```

---

## 3. 项目初始化

### 3.1 创建虚拟环境

```powershell
# 在 backend/ 目录下执行
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3.2 安装依赖

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

### 3.3 配置环境变量

```powershell
copy .env.example .env
# 编辑 .env，至少修改 JWT_SECRET_KEY 与数据库密码
```

生成 JWT 密钥：

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3.4 执行数据库迁移

```powershell
# 首次：生成初始迁移脚本
alembic revision --autogenerate -m "init schema"

# 应用迁移到数据库
alembic upgrade head
```

> 注意：如果首次执行 autogenerate 报错"can't locate revision"，先确保 alembic/versions 目录存在再重试。

---

## 4. 启动服务

### 4.1 启动 FastAPI

```powershell
# 方式一：直接执行
python main.py

# 方式二：uvicorn（带热重载，推荐开发用）
uvicorn main:app --reload --host 0.0.0.0 --port 8002
```

打开浏览器访问（端口在 `.env` 中由 `APP_PORT` 控制，默认 8002）：

- API 文档（Swagger）：http://localhost:8002/docs
- ReDoc 文档：http://localhost:8002/redoc
- 健康检查：http://localhost:8002/api/v1/health
- 当前 Embedder 调试：http://localhost:8002/api/v1/health/embedder

> 端口注记：原本默认 8000，但 Windows 上 uvicorn reload 模式被反复 kill 后会出现"幽灵 socket"残留，因此默认改用 8002。如果你想用其他端口，改 `.env` 的 `APP_PORT`，并把 `frontend/vite.config.ts` 的 proxy target 同步改掉即可。

### 4.2 启动 Celery Worker（异步任务）

新开终端窗口：

```powershell
.\.venv\Scripts\Activate.ps1
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

> Windows 必须加 `--pool=solo` 或 `--pool=threads`，因为默认 prefork 模式在 Windows 不可用。

---

## 5. API 速览（阶段一）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/v1/health` | 服务存活检查 |
| GET  | `/api/v1/health/db` | 数据库连通性检查 |
| POST | `/api/v1/auth/register` | 用户注册 |
| POST | `/api/v1/auth/login` | 登录获取 JWT |
| GET  | `/api/v1/auth/me` | 获取当前登录用户信息 |

### 5.1 注册用户

```powershell
curl -X POST http://localhost:8000/api/v1/auth/register `
  -H "Content-Type: application/json" `
  -d '{\"username\": \"admin\", \"password\": \"admin123\"}'
```

### 5.2 登录获取 Token

```powershell
curl -X POST http://localhost:8000/api/v1/auth/login `
  -H "Content-Type: application/x-www-form-urlencoded" `
  -d "username=admin&password=admin123"
```

### 5.3 携带 Token 访问受保护接口

```powershell
curl http://localhost:8000/api/v1/auth/me `
  -H "Authorization: Bearer <把上一步返回的 access_token 粘贴这里>"
```

---

## 6. 验证 Celery 链路

启动 Worker 后，新开 Python 交互：

```python
from app.tasks.example_tasks import add
result = add.delay(3, 4)
print(result.get(timeout=10))  # 应该输出 7
```

---

## 7. 目录结构

```text
backend/
├── alembic/                  # 数据库迁移
│   ├── env.py
│   └── versions/             # 迁移脚本（自动生成）
├── app/
│   ├── api/                  # API 路由层
│   │   ├── auth.py           # 认证接口
│   │   └── health.py         # 健康检查
│   ├── core/                 # 核心基础设施
│   │   ├── config.py         # 配置（基于 pydantic-settings）
│   │   ├── database.py       # SQLAlchemy 引擎与 Session
│   │   ├── exceptions.py     # 全局异常处理
│   │   ├── logging.py        # 日志配置（loguru）
│   │   └── security.py       # JWT + 密码哈希
│   ├── models/               # SQLAlchemy ORM 模型
│   │   ├── base.py           # TimestampMixin
│   │   ├── user.py
│   │   ├── knowledge_base.py
│   │   ├── document.py
│   │   ├── chat.py           # ChatSession + ChatMessage
│   │   ├── task.py           # TaskRecord
│   │   └── mcp_server.py     # MCPServerConfig
│   ├── schemas/              # Pydantic 请求/响应模型
│   │   ├── common.py         # ApiResponse, TokenResponse
│   │   └── user.py
│   ├── services/             # 业务逻辑层
│   │   └── auth_service.py
│   └── tasks/                # Celery 异步任务
│       ├── celery_app.py     # Celery 实例
│       └── example_tasks.py  # 示例任务
├── .env.example              # 环境变量模板
├── alembic.ini               # Alembic 配置
├── main.py                   # 应用入口
├── requirements.txt          # Python 依赖
└── README.md                 # 本文件
```

---

## 8. 阶段一已完成清单

- [x] 项目结构与依赖管理
- [x] 配置管理（pydantic-settings）+ 环境变量
- [x] 数据库连接（PostgreSQL + SQLAlchemy 2.0）
- [x] 全部 ORM 模型（User / KnowledgeBase / Document / ChatSession / ChatMessage / TaskRecord / MCPServerConfig）
- [x] JWT 认证（注册 / 登录 / 鉴权依赖）
- [x] 统一响应格式（ApiResponse） + 全局异常处理
- [x] CORS 跨域配置
- [x] 日志系统（loguru）
- [x] Alembic 数据库迁移
- [x] Celery + Redis 异步任务基础设施

后续阶段任务详见根目录 `plan.md`。
