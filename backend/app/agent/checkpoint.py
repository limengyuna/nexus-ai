"""
LangGraph Checkpointer 单例

职责：
- 提供全局唯一的 PostgresSaver 实例供 graph 编译时使用
- 启动时自动建表（checkpoints / checkpoint_writes / checkpoint_blobs）
- 失败时降级为 MemorySaver（开发兼容）

设计要点：
- 复用现有 PostgreSQL 实例（通过 settings.database_url 派生）
- 用 psycopg v3 driver（同步），与现有 psycopg2 共存
- 连接池形式管理，避免每次调用都新建连接
"""
from typing import Optional

from loguru import logger

from app.core.config import settings


_checkpointer = None
_pg_pool = None  # PostgreSQL 连接池（保持引用避免被回收）


def _build_pg_dsn() -> str:
    """从 settings 构造 psycopg v3 兼容的 DSN（不要 +psycopg2 后缀）"""
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


def get_checkpointer():
    """
    获取全局 Checkpointer 单例。

    优先使用 PostgresSaver（生产环境，跨进程持久化），
    若初始化失败则降级为 MemorySaver（仅当前进程内有效，重启丢失）。
    """
    global _checkpointer, _pg_pool
    if _checkpointer is not None:
        return _checkpointer

    # ---------- 优先：PostgresSaver ----------
    try:
        from psycopg_pool import ConnectionPool
        from langgraph.checkpoint.postgres import PostgresSaver

        dsn = _build_pg_dsn()
        # autocommit=True：Checkpointer 内部会自己管理事务
        # min_size=1 / max_size=4：Checkpoint 写入频率不高，小池足够
        _pg_pool = ConnectionPool(
            conninfo=dsn,
            max_size=4,
            min_size=1,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=True,
        )
        _checkpointer = PostgresSaver(_pg_pool)
        # 首次启动时建表（已存在则跳过，幂等操作）
        _checkpointer.setup()
        logger.info("[Checkpoint] PostgresSaver 初始化成功 (DB={})", settings.POSTGRES_DB)
        return _checkpointer
    except Exception as e:
        logger.warning("[Checkpoint] PostgresSaver 初始化失败，降级为 MemorySaver: {}", e)

    # ---------- 降级：MemorySaver（仅本进程有效）----------
    from langgraph.checkpoint.memory import MemorySaver
    _checkpointer = MemorySaver()
    logger.warning("[Checkpoint] 使用 MemorySaver（重启后状态丢失，仅适合开发）")
    return _checkpointer


def shutdown_checkpointer():
    """应用关闭时清理资源（main.py 的 lifespan 中调用）"""
    global _checkpointer, _pg_pool
    if _pg_pool is not None:
        try:
            _pg_pool.close()
            logger.info("[Checkpoint] PG 连接池已关闭")
        except Exception as e:
            logger.warning("[Checkpoint] 关闭 PG 连接池失败: {}", e)
    _checkpointer = None
    _pg_pool = None


def make_thread_config(user_msg_id: int) -> dict:
    """
    根据用户消息 ID 构造 LangGraph 配置（含 thread_id）。

    设计：每一轮用户消息独立一个 thread。
    - 多轮历史由应用层 DB 管理，不依赖 checkpoint
    - 单轮内部的中断/恢复才用 checkpoint，thread_id 唯一标识这一轮
    """
    return {"configurable": {"thread_id": f"turn-{user_msg_id}"}}
