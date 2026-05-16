"""
通用 Schemas：统一响应格式、Token 响应等
"""
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """
    统一 API 响应包装器

    所有业务接口的成功返回都应包裹此结构，便于前端统一处理。

    示例::

        {
            "code": 0,
            "message": "success",
            "data": { ... }
        }
    """
    code: int = Field(default=0, description="业务状态码，0 表示成功")
    message: str = Field(default="success", description="提示信息")
    data: Optional[T] = Field(default=None, description="业务数据")

    @classmethod
    def ok(cls, data: Optional[T] = None, message: str = "success") -> "ApiResponse[T]":
        """快速构造成功响应"""
        return cls(code=0, message=message, data=data)

    @classmethod
    def fail(cls, message: str, code: int = -1) -> "ApiResponse[None]":
        """快速构造失败响应"""
        return cls(code=code, message=message, data=None)


class TokenResponse(BaseModel):
    """JWT 登录成功后返回的令牌数据"""
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="过期时间（秒）")
