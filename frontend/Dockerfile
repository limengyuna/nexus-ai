# NexusAI 前端镜像（多阶段构建）
# 阶段 1：用 node 构建生产包
# 阶段 2：用 nginx 托管静态文件（生产体积极小）

# ---------- 阶段 1: build ----------
FROM node:20-alpine AS builder

WORKDIR /app

# 设置 npm 源（淘宝，加速国内构建）
RUN npm config set registry https://registry.npmmirror.com

# 复制 package 文件，先装依赖（利用 docker 层缓存）
COPY package.json package-lock.json* ./
RUN npm install

# 复制源码
COPY . .

# 生产构建
RUN npm run build


# ---------- 阶段 2: nginx 托管 ----------
FROM nginx:alpine

# 复制 build 产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 自定义 nginx 配置：SPA fallback + /api 反代到 backend
# 放到 templates 目录让 nginx:alpine 启动时自动跑 envsubst 替换 ${BACKEND_URL} 等变量
# 见 https://hub.docker.com/_/nginx 的 "Using environment variables in nginx configuration"
COPY nginx.conf /etc/nginx/templates/default.conf.template

# 默认后端地址（本地 docker-compose 用），Railway 部署时通过 service Variables 覆盖为
# http://nexus-ai.railway.internal:8002
ENV BACKEND_URL=http://backend:8000

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
