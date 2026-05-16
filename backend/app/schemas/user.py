"""
用户相关 Schemas：注册、登录、用户信息响应
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserRole


class UserCreate(BaseModel):
    """用户注册请求"""
    username: str = Field(
        ...,
        min_length=3,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="用户名，3-64 位字母/数字/下划线/连字符",
    )
    password: str = Field(
        ...,
        min_length=6,
        max_length=64,
        description="密码，6-64 位",
    )


class UserLogin(BaseModel):
    """用户登录请求（JSON 方式，可选）"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserOut(BaseModel):
    """用户信息响应（脱敏，不返回密码哈希）"""
    model_config = ConfigDict(from_attributes=True)  # 允许从 ORM 对象转换

    id: int
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime
