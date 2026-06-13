# NexusAI 后端镜像
# 基于 python:3.12-slim，多阶段构建以减小镜像体积
FROM python:3.12-slim AS base

# 设置工作目录
WORKDIR /app

# 系统依赖：psycopg2 / lxml 需要的编译工具 + Node.js（MCP stdio 传输需要 npx）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    gnupg \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxcb1 \
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

# ---------- 依赖层（独立缓存）----------
# 升级 pip 避免老版本解析依赖陷入死循环（ResolutionTooDeep）
# pip install 显式指定 pypi.org，避免被任何缓存的 pip 配置影响
RUN pip install --no-cache-dir --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://pypi.org/simple -r requirements.txt

# ---------- 应用代码 ----------
COPY . .

# 暴露端口（与 APP_PORT 一致）
EXPOSE 8002

# 默认启动命令：先跑数据库迁移 → 后台启动 Celery Worker → 前台启动 FastAPI
# 单 service 同时跑两个进程的策略，适用于 Railway 等不支持多 service 共享 Volume 的平台
# docker-compose 中会被 command 覆盖以分别启动 backend / celery worker（两个容器共享 volume）
CMD ["sh", "-c", "alembic upgrade head && celery -A app.tasks.celery_app worker --loglevel=info --pool=solo & python main.py"]
