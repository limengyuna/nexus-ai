"""
认证相关 API 路由

- POST /api/v1/auth/register  用户注册
- POST /api/v1/auth/login     用户登录（OAuth2 表单方式，Swagger 友好）
- GET  /api/v1/auth/me        获取当前登录用户信息
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.ratelimit import LIMIT_LOGIN, limiter
from app.core.security import create_access_token, get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse, TokenResponse
from app.schemas.user import UserCreate, UserOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post(
    "/register",
    response_model=ApiResponse[UserOut],
    summary="用户注册",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(LIMIT_LOGIN)
def register(request: Request, payload: UserCreate, db: Session = Depends(get_db)):
    """
    注册新用户

    - **username**: 3-64 位字母/数字/下划线/连字符
    - **password**: 6-64 位
    """
    try:
        user = AuthService.create_user(db, payload)
    except ValueError as e:
        # 用户名冲突等业务错误
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return ApiResponse.ok(data=UserOut.model_validate(user), message="注册成功")


@router.post(
    "/login",
    response_model=ApiResponse[TokenResponse],
    summary="用户登录",
)
@limiter.limit(LIMIT_LOGIN)
def login(
    request: Request,
    # 使用 OAuth2PasswordRequestForm，Swagger UI 会展示"Authorize"按钮，体验更好
    # 前端真实调用时使用 application/x-www-form-urlencoded
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    用户登录并获取 JWT 访问令牌

    使用 OAuth2 密码模式（form-data 提交）。
    """
    user = AuthService.authenticate(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 签发 JWT，将用户角色作为额外声明嵌入，便于后续权限校验
    access_token = create_access_token(
        subject=user.id,
        extra_claims={"role": user.role.value, "username": user.username},
    )
    token_data = TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return ApiResponse.ok(data=token_data, message="登录成功")


@router.get(
    "/me",
    response_model=ApiResponse[UserOut],
    summary="获取当前登录用户信息",
)
def get_me(current_user: User = Depends(get_current_user)):
    """
    需要在请求头携带 ``Authorization: Bearer <token>``
    """
    return ApiResponse.ok(data=UserOut.model_validate(current_user))
