"""
健康检查接口

提供：
- GET /health        简单存活探测
- GET /health/db     数据库连通性检测（可选，便于排查环境问题）
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.schemas.common import ApiResponse

router = APIRouter(tags=["健康检查"])


@router.get("/health", summary="服务存活检查")
def health_check():
    """简单返回应用名与版本，用于 Docker 健康探测"""
    return ApiResponse.ok(
        data={
            "app": settings.APP_NAME,
            "env": settings.APP_ENV,
            "status": "ok",
        }
    )


@router.get("/health/db", summary="数据库连通性检查")
def health_db(db: Session = Depends(get_db)):
    """执行一次 SELECT 1 验证数据库连接"""
    try:
        db.execute(text("SELECT 1"))
        return ApiResponse.ok(data={"database": "connected"})
    except Exception as e:
        return ApiResponse.fail(message=f"数据库连接失败: {e}")


@router.get("/health/embedder", summary="调试：当前 Embedder 类型")
def health_embedder():
    """返回后端进程实际加载的 embedder 类型与维度，用于诊断"""
    from app.rag.embedder import get_embedder
    emb = get_embedder()
    return ApiResponse.ok(data={
        "type": type(emb).__name__,
        "dimension": emb.dimension,
        "provider_config": settings.EMBEDDING_PROVIDER,
        "has_api_key": bool(settings.DASHSCOPE_API_KEY.strip()),
        "api_key_prefix": settings.DASHSCOPE_API_KEY[:6] if settings.DASHSCOPE_API_KEY else "",
    })
