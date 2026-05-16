"""
模型基础工具：时间戳混入类
"""
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """
    时间戳混入类

    为模型自动添加 created_at 与 updated_at 字段。
    - created_at: 行首次插入时由数据库填充当前时间
    - updated_at: 行被更新时由数据库自动刷新
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="最后更新时间",
    )
