FROM python:3.12-slim

WORKDIR /app

# 复制依赖声明文件
COPY requirements.txt .

# 使用官方源以极快速度安装依赖包
RUN pip install --no-cache-dir --index-url https://pypi.org/simple -r requirements.txt

# 复制当前目录下所有服务源码
COPY . .

# 设定默认运行时端口，完美兼容 Railway 动态 ${PORT} 环境变量端口映射
ENV PORT=8000
EXPOSE 8000

# 启动 uvicorn 极速 Web 服务
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
