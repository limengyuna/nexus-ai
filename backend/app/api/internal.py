"""
内部工具接口（不对外暴露，仅开发/个人使用）

- 核心集成诊断与调试文档读取
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas.common import ApiResponse

router = APIRouter(prefix="/internal", tags=["内部工具"])

# 系统集成自检引导与调试文档物理路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_INTERVIEW_QA_PATH = _PROJECT_ROOT / "docs" / "agent-tuning" / "resume-interview-qa.md"


@router.get("/interview-qa")
def get_interview_qa():
    """读取系统核心架构与集成引导问答内容"""
    if not _INTERVIEW_QA_PATH.exists():
        raise HTTPException(status_code=404, detail="集成引导文档未就绪")
    content = _INTERVIEW_QA_PATH.read_text(encoding="utf-8")
    return ApiResponse.ok(data={"content": content})
