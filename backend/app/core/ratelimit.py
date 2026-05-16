"""
速率限制（Rate Limiting）

基于 slowapi（FastAPI 上常用的 starlette-limiter 派生库）。

设计：
- 按用户（JWT 里的 sub）做限流，未登录时按 IP
- 不同接口有不同档位：
    * LLM 类接口（chat / skill test）—— 30 次 / 分钟（防滥用 token 成本）
    * 文档上传 —— 20 次 / 分钟
    * 默认 —— 不限（让普通查询畅快）

用法（在路由上）：
    @limiter.limit(LIMIT_LLM)
    def my_endpoint(request: Request, ...):
        ...

注意：slowapi 要求被装饰的函数第一个参数必须是 `request: Request`
"""
from typing import Optional

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# 各档位 Key（直接当 limit 字符串）
LIMIT_LLM = "30/minute"          # LLM 调用类
LIMIT_UPLOAD = "20/minute"       # 文档上传
LIMIT_LOGIN = "10/minute"        # 登录/注册（防暴力）


def _key_func(request: Request) -> str:
    """
    优先按当前用户限流；JWT 未携带或解析失败时回落到 IP。
    """
    # 中间件场景下还没走 Depends，所以直接读 header 解析 sub
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:]
        sub = _peek_jwt_sub(token)
        if sub:
            return f"user:{sub}"
    return f"ip:{get_remote_address(request)}"


def _peek_jwt_sub(token: str) -> Optional[str]:
    """
    轻量解 JWT payload 拿 sub，不做签名校验（限流不需要可信，能区分用户即可）。
    """
    try:
        import base64
        import json
        parts = token.split(".")
        if len(parts) < 2:
            return None
        # base64url -> base64
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload_b64 = payload_b64.replace("-", "+").replace("_", "/")
        payload = json.loads(base64.b64decode(payload_b64))
        sub = payload.get("sub")
        return str(sub) if sub is not None else None
    except Exception:
        return None


# 全局 limiter 单例
limiter = Limiter(key_func=_key_func)

# 重新导出 RateLimitExceeded 便于 main.py 注册 handler
__all__ = ["limiter", "RateLimitExceeded", "LIMIT_LLM", "LIMIT_UPLOAD", "LIMIT_LOGIN"]
