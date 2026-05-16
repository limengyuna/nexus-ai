"""
认证业务逻辑层

封装用户注册、登录验证等业务规则。
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.user import UserCreate


class AuthService:
    """认证相关业务方法集合"""

    @staticmethod
    def get_user_by_username(db: Session, username: str) -> Optional[User]:
        """按用户名查询用户"""
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def create_user(
        db: Session,
        payload: UserCreate,
        role: UserRole = UserRole.USER,
    ) -> User:
        """
        创建新用户

        :raises ValueError: 用户名已存在
        """
        # 检查用户名是否已被占用
        existing = AuthService.get_user_by_username(db, payload.username)
        if existing is not None:
            raise ValueError(f"用户名 '{payload.username}' 已被注册")

        # 构造并入库
        user = User(
            username=payload.username,
            hashed_password=hash_password(payload.password),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def authenticate(db: Session, username: str, password: str) -> Optional[User]:
        """
        校验用户名密码。

        :return: 验证通过返回 User 对象，失败返回 None
        """
        user = AuthService.get_user_by_username(db, username)
        if user is None:
            return None
        if not user.is_active:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
