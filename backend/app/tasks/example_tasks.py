"""
示例任务

仅用于阶段一验证 Celery + Redis 链路是否打通。
后续阶段会被真实任务（如 document_tasks.py）取代/补充。
"""
import time

from loguru import logger

from app.tasks.celery_app import celery_app


@celery_app.task(name="example.add", bind=True)
def add(self, x: int, y: int) -> int:
    """
    最简单的加法任务，用于链路连通性测试。

    在 Python 交互环境调用::

        from app.tasks.example_tasks import add
        result = add.delay(3, 4)
        print(result.get(timeout=10))  # 7
    """
    logger.info("Celery 任务执行: add({}, {}) [task_id={}]", x, y, self.request.id)
    time.sleep(1)  # 模拟耗时
    return x + y


@celery_app.task(name="example.long_running")
def long_running(seconds: int = 5) -> str:
    """模拟长任务，用于验证超时机制"""
    logger.info("开始长任务，预计耗时 {} 秒", seconds)
    time.sleep(seconds)
    return f"完成耗时 {seconds} 秒的任务"
