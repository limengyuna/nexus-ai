"""
数据库连接与会话管理模块

提供 SQLAlchemy 引擎、Session 工厂、声明式 Base 类，
以及供 FastAPI 路由使用的依赖注入函数 get_db。
"""
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


# ---------- 数据库引擎 ----------
# pool_pre_ping: 每次取连接前先 ping 一下，避免使用失效连接
# pool_recycle: 连接最长保持时间（秒），防止数据库主动断开
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.APP_DEBUG and not settings.is_production,  # 调试模式打印 SQL
)

# ---------- Session 工厂 ----------
# autocommit=False: 手动控制事务提交
# autoflush=False: 不自动 flush，避免意外的数据库往返
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # commit 后对象不过期，便于继续访问属性
)


# ---------- 声明式基类 ----------
class Base(DeclarativeBase):
    """所有 ORM 模型的基类（SQLAlchemy 2.0 声明式风格）"""
    pass


# ---------- FastAPI 依赖注入：获取数据库会话 ----------
def get_db() -> Generator[Session, None, None]:
    """
    数据库会话依赖注入函数。

    使用方式（在 FastAPI 路由中）::

        from fastapi import Depends
        from sqlalchemy.orm import Session
        from app.core.database import get_db

        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...

    每个请求开始时创建新 Session，请求结束（无论成功或异常）时自动关闭。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
