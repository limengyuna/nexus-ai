"""
NexusAI 后端服务入口

启动方式::

    # 开发模式（带热重载）
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

    # 或直接执行本文件
    python main.py
"""
import sys
import asyncio

if sys.platform == "win32":
    # 强制在 Windows 上使用 ProactorEventLoopPolicy，以支持 stdio 子进程（MCP Server 启动）
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import auth, chat, document, health, knowledge_base, mcp, skill, task, memory, internal, memory_profile
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    启动时：初始化日志、打印配置信息、预加载核心资源（消除冷启动）
    关闭时：清理资源
    """
    # ---------- 1. 启动时的同步预热（必须在 yield 之前） ----------
    setup_logging()
    logger.info("=" * 60)
    logger.info("{} 启动中...", settings.APP_NAME)
    logger.info("环境: {}", settings.APP_ENV)
    logger.info("监听: {}:{}", settings.APP_HOST, settings.APP_PORT)
    logger.info("调试模式: {}", settings.APP_DEBUG)
    logger.info("=" * 60)
    
    # 0. 初始化 Memory Profile Slots
    from app.core.database import SessionLocal
    from app.memory.profile_store import MemoryProfileStore
    try:
        db = SessionLocal()
        MemoryProfileStore.init_default_slots(db)
        logger.info("系统预设的 Profile Slots 初始化完成。")
    except Exception as e:
        logger.error(f"初始化 Profile Slots 失败: {e}")
    finally:
        db.close()

    # 1. 预编译 LangGraph 主图与 PostgresSaver 数据库连接池
    try:
        from app.agent.graph import get_agent_graph
        get_agent_graph()
        logger.info("[Pre-warm] LangGraph 核心流主图预编译成功（数据库 checkpointer 连接池已建立）。")
    except Exception as e:
        logger.error(f"[Pre-warm] 预编译 LangGraph 主图失败: {e}")

    # 2. 预加载并建立 ChromaDB 客户端物理连接
    try:
        from app.rag.vector_store import get_vector_store
        get_vector_store()
        logger.info("[Pre-warm] ChromaDB 向量数据库客户端加载与连接完成。")
    except Exception as e:
        logger.error(f"[Pre-warm] 预热 ChromaDB 失败: {e}")

    # 3. 预加载 Embedding 向量化模型管理器
    try:
        from app.rag.embedder import get_embedder
        get_embedder()
        logger.info("[Pre-warm] Embedding 向量化模型客户端初始化完成。")
    except Exception as e:
        logger.error(f"[Pre-warm] 预热 Embedding 失败: {e}")

    # 4. 预实例化双模型 LLM 客户端
    try:
        from app.agent.llm import get_llm, get_llm_fast
        get_llm()
        get_llm_fast()
        logger.info("[Pre-warm] 双大语言模型 LLM 客户端初始化完成。")
    except Exception as e:
        logger.error(f"[Pre-warm] 预加载 LLM 客户端失败: {e}")

    # ---------- 2. 启动时的后台非阻塞异步预热（同样在 yield 之前，但异步运行不阻碍主线程） ----------

    # 5. 后台线程预加载 jieba 中文分词库字典
    # 💡 线程瞬间拉起并返回，不阻塞主服务对外监听
    def _warmup_jieba():
        try:
            import jieba
            jieba.initialize()
            logger.info("[Pre-warm] jieba 中文分词库字典后台加载完成。")
        except Exception as e:
            logger.error(f"[Pre-warm] 预热 jieba 词典失败: {e}")

    import threading
    threading.Thread(target=_warmup_jieba, daemon=True).start()

    # 6. 后台异步协程预热外部 API 网络连接通道（TLS/SSL 保持握手）
    # 💡 create_task 瞬间注册并返回，不阻塞主进程 yield！
    async def _warmup_llm_network():
        try:
            from app.agent.llm import get_llm_fast
            llm = get_llm_fast()
            await asyncio.to_thread(
                llm.complete,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1
            )
            logger.info("[Pre-warm] LLM 外部 API 网络通道 (TLS/SSL 保持连接池) 后台预热就绪。")
        except Exception as e:
            logger.warning(f"[Pre-warm] LLM 网络连接通道后台预热失败（不影响主业务）: {e}")

    asyncio.create_task(_warmup_llm_network())

    yield  # 应用运行期间

    # ---------- 3. 关闭时（应用真正退出时执行，yield 之后） ----------
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
app.include_router(memory.router, prefix=API_PREFIX)
app.include_router(memory_profile.router, prefix=API_PREFIX)
# 内部工具（面试 QA 导出等）
app.include_router(internal.router, prefix=API_PREFIX)


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
