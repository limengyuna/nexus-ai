"""
日志配置模块

基于 loguru 提供统一的日志格式与输出策略。
"""
import sys

from loguru import logger

from app.core.config import settings


def setup_logging() -> None:
    """初始化全局日志配置"""
    # 清除默认 handler
    logger.remove()

    # 控制台输出：彩色 + 简洁
    log_level = "DEBUG" if settings.APP_DEBUG else "INFO"
    logger.add(
        sys.stdout,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}:{function}:{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 文件输出：按大小滚动，保留 7 天
    logger.add(
        "logs/nexus_ai_{time:YYYY-MM-DD}.log",
        level="INFO",
        rotation="20 MB",
        retention="7 days",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
        enqueue=True,  # 线程安全
    )

    logger.info("日志系统初始化完成，级别={}", log_level)
