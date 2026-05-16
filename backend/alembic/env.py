"""
Alembic 迁移环境配置

关键点：
1. 从 app.core.config.settings 动态读取数据库 URL
2. 显式导入所有 ORM 模型，让 Alembic autogenerate 能发现全部表
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------- 将项目根加入 sys.path ----------
# 这样 alembic 才能 import app.* 模块
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------- 导入 ORM 模型（必须！否则 autogenerate 检测不到表）----------
from app.core.config import settings  # noqa: E402
from app.core.database import Base    # noqa: E402
import app.models  # noqa: E402, F401  显式导入触发所有模型注册


# Alembic Config 对象
config = context.config

# 注入数据库 URL（从环境变量读取，不硬编码）
config.set_main_option("sqlalchemy.url", settings.database_url)

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标元数据 —— 让 autogenerate 知道当前模型结构
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    离线模式：仅生成 SQL 脚本，不实际连接数据库
    使用场景：CI 中预览迁移内容
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,         # 检测字段类型变化
        compare_server_default=True,  # 检测默认值变化
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    在线模式：连接数据库并执行迁移
    使用场景：日常 alembic upgrade head
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
