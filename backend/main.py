"""
NexusAI 后端服务入口

启动方式::

    # 开发模式（带热重载）
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

    # 或直接执行本文件
    python main.py
"""
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import auth, chat, document, health, knowledge_base, mcp, skill, task
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    启动时：初始化日志、打印配置信息
    关闭时：清理资源（暂无）
    """
    # ---------- 启动 ----------
    setup_logging()
    logger.info("=" * 60)
    logger.info("{} 启动中...", settings.APP_NAME)
    logger.info("环境: {}", settings.APP_ENV)
    logger.info("监听: {}:{}", settings.APP_HOST, settings.APP_PORT)
    logger.info("调试模式: {}", settings.APP_DEBUG)
    logger.info("=" * 60)

    yield  # 应用运行期间

    # ---------- 关闭 ----------
    logger.info("{} 已停止", settings.APP_NAME)


# ---------- 创建 FastAPI 应用实例 ----------
app = FastAPI(
    title=settings.APP_NAME,
    description="企业级智能知识库 + 多 Agent 协作平台",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ---------- 中间件：CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 全局异常处理 ----------
register_exception_handlers(app)


# ---------- 限流（slowapi）----------
# 把全局 limiter 挂到 app.state，路由的 @limiter.limit() 才能找到它
from app.core.ratelimit import limiter, RateLimitExceeded  # noqa: E402
from slowapi.middleware import SlowAPIMiddleware  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------- 注册路由 ----------
API_PREFIX = "/api/v1"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
# 阶段二：知识库 / 文档 / 任务
app.include_router(knowledge_base.router, prefix=API_PREFIX)
app.include_router(document.router, prefix=API_PREFIX)
app.include_router(task.router, prefix=API_PREFIX)
# 阶段三：对话（多 Agent 协作）+ MCP 外部 Server 管理 + Skills 只读管理
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(mcp.router, prefix=API_PREFIX)
app.include_router(skill.router, prefix=API_PREFIX)


# ---------- 根路由 ----------
@app.get("/", tags=["根路径"])
def root():
    """欢迎信息"""
    return {
        "app": settings.APP_NAME,
        "version": "0.1.0",
        "docs": "/docs",
        "message": "Welcome to NexusAI Backend API",
    }


# ---------- 直接执行入口 ----------
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_DEBUG,
    )
