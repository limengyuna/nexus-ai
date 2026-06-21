"""
受控业务上下文工具
允许 Tool Agent 读取当前登录用户在系统内的业务上下文信息，但不暴露任意 SQL 查询权限。
"""
from dataclasses import dataclass
import json
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func

from app.agent.tools.registry import BaseTool
from app.core.database import SessionLocal
from app.models.chat import ChatSession
from app.models.document import Document, DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.mcp_server import MCPServerConfig
from app.models.user import User


@dataclass(frozen=True)
class AgentRuntimeContext:
    """Agent 运行时上下文，由框架注入，防伪造"""
    user_id: Optional[int]
    session_id: Optional[int]
    kb_id: Optional[int]


class BusinessContextTool(BaseTool):
    """业务上下文工具基类"""
    needs_agent_context = True

    def run(self, **kwargs) -> Any:
        raise NotImplementedError("BusinessContextTool 必须通过 run_with_context 调用")

    def run_with_context(
        self,
        arguments: Dict[str, Any],
        context: AgentRuntimeContext,
    ) -> Any:
        raise NotImplementedError


# -----------------------------------------------------------------------------
# 1. get_user_workspace_summary
# -----------------------------------------------------------------------------
class WorkspaceSummaryArgs(BaseModel):
    pass


class WorkspaceSummaryTool(BusinessContextTool):
    name = "get_user_workspace_summary"
    description = (
        "获取当前登录用户在 NexusAI 中的工作区概览，包括账号、知识库数量、文档处理状态、"
        "MCP 配置数量和会话数量。只能读取当前用户的数据，适合回答用户询问自己账号、知识库、"
        "文档处理情况或系统使用情况的问题。"
    )
    args_schema = WorkspaceSummaryArgs

    def run_with_context(self, arguments: Dict[str, Any], context: AgentRuntimeContext) -> Any:
        if not context.user_id:
            return {"error": "缺少用户上下文，无法查询工作区概览"}

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == context.user_id).first()
            if not user:
                return {"error": "用户不存在"}

            # 知识库数
            kb_count = db.query(func.count(KnowledgeBase.id)).filter(KnowledgeBase.created_by == context.user_id).scalar() or 0

            # 文档统计
            # 先找到该用户所有的知识库 ID
            kb_ids = [kb.id for kb in db.query(KnowledgeBase.id).filter(KnowledgeBase.created_by == context.user_id).all()]
            doc_stats = {
                "total": 0,
                "completed": 0,
                "processing": 0,
                "failed": 0,
                "total_chunks": 0
            }
            if kb_ids:
                doc_total = db.query(func.count(Document.id)).filter(Document.kb_id.in_(kb_ids)).scalar() or 0
                doc_completed = db.query(func.count(Document.id)).filter(Document.kb_id.in_(kb_ids), Document.status == DocumentStatus.COMPLETED).scalar() or 0
                doc_failed = db.query(func.count(Document.id)).filter(Document.kb_id.in_(kb_ids), Document.status == DocumentStatus.FAILED).scalar() or 0
                total_chunks = db.query(func.sum(Document.chunk_count)).filter(Document.kb_id.in_(kb_ids)).scalar() or 0
                doc_stats = {
                    "total": doc_total,
                    "completed": doc_completed,
                    "processing": doc_total - doc_completed - doc_failed,
                    "failed": doc_failed,
                    "total_chunks": int(total_chunks)
                }

            # MCP数
            mcp_total = db.query(func.count(MCPServerConfig.id)).filter(MCPServerConfig.created_by == context.user_id).scalar() or 0
            mcp_active = db.query(func.count(MCPServerConfig.id)).filter(MCPServerConfig.created_by == context.user_id, MCPServerConfig.is_active.is_(True)).scalar() or 0

            # 会话数
            chat_total = db.query(func.count(ChatSession.id)).filter(ChatSession.user_id == context.user_id).scalar() or 0

            return {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role.value,
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat() if user.created_at else None
                },
                "knowledge_bases": {
                    "total": kb_count
                },
                "documents": doc_stats,
                "mcp_servers": {
                    "total": mcp_total,
                    "active": mcp_active
                },
                "chat_sessions": {
                    "total": chat_total
                }
            }
        except Exception as e:
            logger.error("查询工作区概览失败: {}", e)
            return {"error": str(e)}
        finally:
            db.close()


# -----------------------------------------------------------------------------
# 2. get_knowledge_base_overview
# -----------------------------------------------------------------------------
class KnowledgeBaseOverviewArgs(BaseModel):
    limit: int = Field(default=5, description="返回的最大知识库数量，最大10")
    keyword: Optional[str] = Field(default=None, description="按知识库名称或描述的模糊搜索关键词")
    include_recent_documents: bool = Field(default=False, description="是否包含最近最多3个文档信息")


class KnowledgeBaseOverviewTool(BusinessContextTool):
    name = "get_knowledge_base_overview"
    description = (
        "获取当前用户的知识库概览，包括知识库名称、描述、分块配置、文档数量、处理状态和 chunk 数。"
        "适合分析用户当前知识库建设情况、文档是否处理完成、还需要补充哪些资料。支持按关键词搜索，默认只返回少量摘要。"
    )
    args_schema = KnowledgeBaseOverviewArgs

    def run_with_context(self, arguments: Dict[str, Any], context: AgentRuntimeContext) -> Any:
        if not context.user_id:
            return {"error": "缺少用户上下文，无法查询知识库概览"}

        limit = min(arguments.get("limit", 5), 10)
        keyword = arguments.get("keyword")
        include_recent_documents = arguments.get("include_recent_documents", False)

        if keyword and len(keyword) > 100:
            keyword = keyword[:100]

        db = SessionLocal()
        try:
            query = db.query(KnowledgeBase).filter(KnowledgeBase.created_by == context.user_id)
            if keyword:
                search_term = f"%{keyword}%"
                query = query.filter((KnowledgeBase.name.ilike(search_term)) | (KnowledgeBase.description.ilike(search_term)))
            
            total_count = query.count()
            kbs = query.order_by(KnowledgeBase.created_at.desc()).limit(limit).all()

            items = []
            for kb in kbs:
                doc_total = db.query(func.count(Document.id)).filter(Document.kb_id == kb.id).scalar() or 0
                doc_completed = db.query(func.count(Document.id)).filter(Document.kb_id == kb.id, Document.status == DocumentStatus.COMPLETED).scalar() or 0
                doc_failed = db.query(func.count(Document.id)).filter(Document.kb_id == kb.id, Document.status == DocumentStatus.FAILED).scalar() or 0
                total_chunks = db.query(func.sum(Document.chunk_count)).filter(Document.kb_id == kb.id).scalar() or 0

                item = {
                    "id": kb.id,
                    "name": kb.name,
                    "description": kb.description,
                    "chunk_strategy": kb.chunk_strategy.value,
                    "chunk_size": kb.chunk_size,
                    "chunk_overlap": kb.chunk_overlap,
                    "enable_llm_clean": kb.enable_llm_clean,
                    "document_count": doc_total,
                    "completed_documents": doc_completed,
                    "failed_documents": doc_failed,
                    "total_chunks": int(total_chunks),
                    "created_at": kb.created_at.isoformat() if kb.created_at else None
                }

                if include_recent_documents:
                    recent_docs = db.query(Document).filter(Document.kb_id == kb.id).order_by(Document.created_at.desc()).limit(3).all()
                    item["recent_documents"] = [
                        {
                            "id": d.id,
                            "file_name": d.file_name,
                            "file_type": d.file_type,
                            "status": d.status.value,
                            "chunk_count": d.chunk_count,
                            "created_at": d.created_at.isoformat() if d.created_at else None
                        } for d in recent_docs
                    ]
                
                items.append(item)

            return {
                "total": total_count,
                "items": items
            }
        except Exception as e:
            logger.error("查询知识库概览失败: {}", e)
            return {"error": str(e)}
        finally:
            db.close()


# -----------------------------------------------------------------------------
# 3. get_current_session_summary
# -----------------------------------------------------------------------------
class CurrentSessionSummaryArgs(BaseModel):
    pass


class CurrentSessionSummaryTool(BusinessContextTool):
    name = "get_current_session_summary"
    description = (
        "获取当前对话会话的摘要信息，包括会话标题、关联知识库和消息数量。"
        "适合回答当前会话上下文、关联知识库、最近讨论内容等问题。"
    )
    args_schema = CurrentSessionSummaryArgs

    def run_with_context(self, arguments: Dict[str, Any], context: AgentRuntimeContext) -> Any:
        if not context.user_id:
            return {"error": "缺少用户上下文，无法查询会话信息"}
        if not context.session_id:
            return {"error": "当前没有在具体的会话中，无法获取会话上下文"}

        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter(
                ChatSession.id == context.session_id,
                ChatSession.user_id == context.user_id
            ).first()

            if not session:
                return {"error": "会话不存在或无权访问"}

            # 获取关联的知识库名称，确保只有自己的知识库才能获取名称避免间接越权
            kb_name = None
            if session.kb_id:
                kb = db.query(KnowledgeBase.name).filter(
                    KnowledgeBase.id == session.kb_id,
                    KnowledgeBase.created_by == context.user_id
                ).first()
                if kb:
                    kb_name = kb[0]

            from app.models.chat import ChatMessage
            message_count = db.query(func.count(ChatMessage.id)).filter(ChatMessage.session_id == session.id).scalar() or 0

            return {
                "session": {
                    "id": session.id,
                    "title": session.title,
                    "kb_id": session.kb_id,
                    "kb_name": kb_name,
                    "message_count": message_count,
                    "created_at": session.created_at.isoformat() if session.created_at else None,
                    "updated_at": session.updated_at.isoformat() if session.updated_at else None
                }
            }
        except Exception as e:
            logger.error("查询当前会话概览失败: {}", e)
            return {"error": str(e)}
        finally:
            db.close()


# -----------------------------------------------------------------------------
# 4. get_mcp_server_overview
# -----------------------------------------------------------------------------
class MCPServerOverviewArgs(BaseModel):
    limit: int = Field(default=5, description="返回的最大配置数量，最大10")
    include_tools: bool = Field(default=False, description="是否包含子工具名称和描述，最多返回前5个")


class MCPServerOverviewTool(BusinessContextTool):
    name = "get_mcp_server_overview"
    description = "获取当前用户 MCP 配置概览，包含外部工具信息。"
    args_schema = MCPServerOverviewArgs

    def run_with_context(self, arguments: Dict[str, Any], context: AgentRuntimeContext) -> Any:
        if not context.user_id:
            return {"error": "缺少用户上下文，无法查询 MCP 配置"}

        limit = min(arguments.get("limit", 5), 10)
        include_tools = arguments.get("include_tools", False)

        db = SessionLocal()
        try:
            query = db.query(MCPServerConfig).filter(MCPServerConfig.created_by == context.user_id)
            total_count = query.count()
            active_count = db.query(func.count(MCPServerConfig.id)).filter(
                MCPServerConfig.created_by == context.user_id,
                MCPServerConfig.is_active.is_(True)
            ).scalar() or 0
            
            configs = query.order_by(MCPServerConfig.created_at.desc()).limit(limit).all()

            items = []
            for c in configs:
                item = {
                    "id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "transport_type": c.transport_type.value,
                    "is_active": c.is_active,
                    "tool_count": c.tool_count,
                    "created_at": c.created_at.isoformat() if c.created_at else None
                }
                if include_tools and c.cached_tools:
                    item["tools"] = [
                        {
                            "name": t.get("name"),
                            "description": t.get("description")
                        } for t in c.cached_tools[:5]
                    ]
                elif include_tools:
                    item["tools"] = []
                
                items.append(item)

            return {
                "total": total_count,
                "active": active_count,
                "items": items
            }
        except Exception as e:
            logger.error("查询 MCP 配置概览失败: {}", e)
            return {"error": str(e)}
        finally:
            db.close()


# -----------------------------------------------------------------------------
# 5. get_knowledge_base_documents
# -----------------------------------------------------------------------------
class KnowledgeBaseDocumentsArgs(BaseModel):
    kb_ids: List[int] = Field(description="[必填] 要查询的知识库 ID 列表。例如: [24, 25]。如果只查一个也请放在列表中，如 [24]。绝不能省略此参数！")
    limit: int = Field(default=10, description="返回的最大文档数量，最大50")
    offset: int = Field(default=0, description="分页偏移量")
    status: Optional[str] = Field(default=None, description="按处理状态过滤，例如：completed, failed, processing 等")
    keyword: Optional[str] = Field(default=None, description="按文件名模糊搜索关键词")


class KnowledgeBaseDocumentsTool(BusinessContextTool):
    name = "get_knowledge_base_documents"
    description = (
        "获取当前用户指定知识库下的具体文档列表。"
        "必须明确提供 kb_ids 列表来查询特定的知识库。如果不知道目标知识库的 ID，必须先调用 get_knowledge_base_overview 工具查询以获取它，绝不能凭空猜测或省略 kb_ids 参数。"
    )
    args_schema = KnowledgeBaseDocumentsArgs

    def run_with_context(self, arguments: Dict[str, Any], context: AgentRuntimeContext) -> Any:
        if not context.user_id:
            return {"error": "缺少用户上下文，无法查询知识库文档"}

        kb_ids = self._normalize_kb_ids(arguments)

        if not kb_ids:
            return {"error": "缺少必填参数 kb_ids：请明确指定要查询的知识库 ID 列表"}

        limit = min(arguments.get("limit", 10), 50)
        offset = max(arguments.get("offset", 0), 0)
        status = arguments.get("status")
        keyword = arguments.get("keyword")

        db = SessionLocal()
        try:
            # 校验指定知识库的所有权，过滤掉越权或不存在的 ID
            valid_kbs = db.query(KnowledgeBase.id).filter(
                KnowledgeBase.id.in_(kb_ids),
                KnowledgeBase.created_by == context.user_id
            ).all()
            valid_kb_ids = [k.id for k in valid_kbs]
            
            if not valid_kb_ids:
                return {"error": f"指定的知识库(IDs: {kb_ids})均不存在或无权访问"}

            query = db.query(Document).filter(Document.kb_id.in_(valid_kb_ids))

            if status:
                try:
                    # 尝试转换枚举，如果不匹配直接用字符串过滤可能报错
                    status_enum = DocumentStatus(status)
                    query = query.filter(Document.status == status_enum)
                except ValueError:
                    return {"error": f"无效的文档状态: {status}"}
                    
            if keyword:
                search_term = f"%{keyword[:100]}%"
                query = query.filter(Document.file_name.ilike(search_term))
            
            total_count = query.count()
            docs = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()

            items = []
            for d in docs:
                items.append({
                    "id": d.id,
                    "kb_id": d.kb_id,
                    "file_name": d.file_name,
                    "file_type": d.file_type,
                    "file_size": d.file_size,
                    "status": d.status.value,
                    "chunk_count": d.chunk_count,
                    "error_msg": d.error_msg,
                    "created_at": d.created_at.isoformat() if d.created_at else None
                })

            return {
                "total": total_count,
                "items": items
            }
        except Exception as e:
            logger.error("查询知识库文档失败: {}", e)
            return {"error": str(e)}
        finally:
            db.close()

    @staticmethod
    def _normalize_kb_ids(arguments: Dict[str, Any]) -> List[int]:
        raw_values = arguments.get("kb_ids")
        if raw_values is None:
            raw_values = arguments.get("kb_id")

        if isinstance(raw_values, str):
            try:
                parsed = json.loads(raw_values)
                raw_values = parsed
            except json.JSONDecodeError:
                raw_values = [raw_values]
        elif isinstance(raw_values, int):
            raw_values = [raw_values]

        if not isinstance(raw_values, list):
            return []

        kb_ids: List[int] = []
        for value in raw_values:
            if isinstance(value, int):
                kb_ids.append(value)
            elif isinstance(value, str) and value.strip().isdigit():
                kb_ids.append(int(value.strip()))

        return list(dict.fromkeys(kb_ids))


_BUSINESS_CONTEXT_TOOLS = [
    WorkspaceSummaryTool(),
    KnowledgeBaseOverviewTool(),
    KnowledgeBaseDocumentsTool(),
    CurrentSessionSummaryTool(),
    MCPServerOverviewTool(),
]

def list_business_context_tools() -> List[BusinessContextTool]:
    return list(_BUSINESS_CONTEXT_TOOLS)

def get_business_context_tool(name: str) -> Optional[BusinessContextTool]:
    for tool in _BUSINESS_CONTEXT_TOOLS:
        if tool.name == name:
            return tool
    return None
