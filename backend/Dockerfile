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

# 设置 pip 源（清华，加速国内构建）
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- 依赖层（独立缓存）----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- 应用代码 ----------
COPY . .

# 暴露端口
EXPOSE 8000

# 默认启动命令：FastAPI（被 docker-compose 覆盖以分别启动 backend / celery worker）
CMD ["python", "main.py"]
