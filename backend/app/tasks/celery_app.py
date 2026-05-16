"""
Celery 应用实例配置

启动 Worker 的命令（在 backend/ 目录下）::

    celery -A app.tasks.celery_app worker --loglevel=info --pool=solo

Windows 上 Celery 5.x 必须使用 ``--pool=solo`` 或 ``--pool=threads``，
默认的 prefork 模式在 Windows 上不可用。
"""
from celery import Celery

from app.core.config import settings

# ---------- 创建 Celery 实例 ----------
celery_app = Celery(
    "nexus_ai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    # include: 启动 Worker 时自动导入的任务模块
    # 阶段二开始追加 "app.tasks.document_tasks" 等
    include=[
        "app.tasks.example_tasks",
        "app.tasks.document_tasks",  # 阶段二：文档处理管道
    ],
)

# ---------- 全局配置 ----------
celery_app.conf.update(
    # 时区
    timezone="Asia/Shanghai",
    enable_utc=False,

    # 序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # 结果保留时间（秒）
    result_expires=3600 * 24,

    # 任务超时（秒），防止单任务卡死
    task_soft_time_limit=600,   # 软超时：抛 SoftTimeLimitExceeded
    task_time_limit=900,        # 硬超时：直接 kill worker

    # Worker 取任务数：每次仅预取 1 个，避免单 worker 饿死其他
    worker_prefetch_multiplier=1,

    # 任务执行完后才确认（保证可靠性）
    task_acks_late=True,

    # 失败重试基础配置
    task_default_retry_delay=10,
    task_max_retries=3,
)


# ---------- 路由示例（按需启用）----------
# 不同优先级任务路由到不同队列
# celery_app.conf.task_routes = {
#     "app.tasks.document_tasks.*": {"queue": "documents"},
#     "app.tasks.example_tasks.*": {"queue": "default"},
# }
