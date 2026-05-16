"""
安全认证模块

提供：
1. 密码哈希与校验（基于 bcrypt）
2. JWT 令牌的签发与校验
3. FastAPI 依赖注入函数：获取当前登录用户
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db


# ---------- 密码哈希工具 ----------
# 使用 bcrypt 算法（业界标准，抗暴力破解）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """对明文密码进行哈希"""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希值是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)


# ---------- JWT 令牌签发 ----------
def create_access_token(
    subject: str | int,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict] = None,
) -> str:
    """
    生成 JWT 访问令牌。

    :param subject: 令牌主体（通常是 user_id）
    :param expires_delta: 过期时间增量，None 则使用配置默认值
    :param extra_claims: 额外声明（如用户角色等）
    :return: 编码后的 JWT 字符串
    """
    now = datetime.now(timezone.utc)
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = now + expires_delta

    # 标准 JWT 声明
    payload = {
        "sub": str(subject),  # subject 必须是字符串
        "iat": now,           # 签发时间
        "exp": expire,        # 过期时间
        "type": "access",     # 令牌类型，便于后续扩展 refresh_token
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    解码并校验 JWT 令牌。

    :raises JWTError: 令牌无效、过期或被篡改时抛出
    :return: 解码后的 payload 字典
    """
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# ---------- FastAPI 依赖：从请求头提取令牌 ----------
# tokenUrl 指向登录接口的实际路径，Swagger UI 会自动用它来获取令牌
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    """
    依赖注入：从 JWT 中提取当前用户 ID。

    用于不需要查库、仅需要 user_id 的场景。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证凭据无效或已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id_str: Optional[str] = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        return int(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exception


def get_current_user(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    依赖注入：从数据库加载当前登录用户的完整对象。

    用于需要访问用户信息（如角色、用户名等）的场景。
    """
    # 在此处局部导入，避免循环引用（models 可能反过来依赖 core）
    from app.models.user import User

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )
    return user
