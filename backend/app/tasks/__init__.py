"""
Celery 异步任务模块

阶段一：仅搭建 Celery 实例与示例任务，验证基础设施可用。
阶段二开始接入真实业务任务（文档处理等）。
"""
from app.tasks.celery_app import celery_app

__all__ = ["celery_app"]
