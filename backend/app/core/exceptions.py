"""
全局异常处理

将各种异常统一转换为符合 ApiResponse 规范的 JSON 响应，
避免前端面对不一致的错误格式。
"""
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器"""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """处理 HTTP 类异常（如手动抛出的 HTTPException）"""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": exc.detail,
                "data": None,
            },
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """处理 Pydantic 请求体校验错误"""
        # 提取首个错误信息，简化前端展示
        errors = exc.errors()
        first_error = errors[0] if errors else {"msg": "请求参数校验失败"}
        loc = " -> ".join(str(x) for x in first_error.get("loc", []))
        message = f"参数校验失败: [{loc}] {first_error.get('msg', '')}"

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "message": message,
                "data": {"errors": errors},
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        """处理数据库异常，避免泄露 SQL 细节给前端"""
        logger.exception("数据库异常: {}", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "数据库操作失败，请稍后重试",
                "data": None,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """兜底处理未捕获的异常"""
        logger.exception("未处理的异常: {}", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "服务器内部错误",
                "data": None,
            },
        )
