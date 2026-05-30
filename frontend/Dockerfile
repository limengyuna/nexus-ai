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

# 自定义 nginx 配置（含 ${BACKEND_URL} 占位符，启动时由 envsubst 替换）
# 注意：nginx 配置里的 $host / $remote_addr 等是 nginx 内置变量，envsubst 不能误伤
# 所以这里显式指定 envsubst 只替换 ${BACKEND_URL}，避免污染 nginx 自带变量
COPY nginx.conf /etc/nginx/conf.d/default.conf.template

# 默认后端地址（本地 docker-compose 用），Railway 部署时通过 service Variables 覆盖为
# http://nexus-ai.railway.internal:8002
ENV BACKEND_URL=http://backend:8000

EXPOSE 80

# 启动时：
# 1. 从 /etc/resolv.conf 提取容器实际的 DNS 解析器地址
# 2. envsubst 替换 $BACKEND_URL 和 $DNS_RESOLVER → 输出到正式配置
# 3. 启动 nginx
CMD ["sh", "-c", "export DNS_RESOLVER=$(grep nameserver /etc/resolv.conf | head -1 | awk '{print $2}'); envsubst '${BACKEND_URL} ${DNS_RESOLVER}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
