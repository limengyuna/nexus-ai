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
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

# 设置 pip 源
# 本地构建用清华源加速；云端构建（Railway/海外）用官方源避免被墙
# 通过 PIP_INDEX_URL 环境变量在构建时覆盖（docker build --build-arg 或 Railway 默认）
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip config set global.index-url ${PIP_INDEX_URL}

# ---------- 依赖层（独立缓存）----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- 应用代码 ----------
COPY . .

# 暴露端口（与 APP_PORT 一致）
EXPOSE 8002

# 默认启动命令：先跑数据库迁移再启动 FastAPI
# 用 sh -c 串联两条命令；docker-compose 中会被 command 覆盖以分别启动 backend / celery worker
CMD ["sh", "-c", "alembic upgrade head && python main.py"]
