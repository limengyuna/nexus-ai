"""
内部工具接口（不对外暴露，仅开发/个人使用）

- 面试 QA 文档读取
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas.common import ApiResponse

router = APIRouter(prefix="/internal", tags=["内部工具"])

# 面试 QA 文档路径（相对于 backend 目录的上层项目根目录）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_INTERVIEW_QA_PATH = _PROJECT_ROOT / "docs" / "agent-tuning" / "resume-interview-qa.md"


@router.get("/interview-qa")
def get_interview_qa():
    """读取面试 QA markdown 文件内容"""
    if not _INTERVIEW_QA_PATH.exists():
        raise HTTPException(status_code=404, detail="面试 QA 文档不存在")
    content = _INTERVIEW_QA_PATH.read_text(encoding="utf-8")
    return ApiResponse.ok(data={"content": content})
