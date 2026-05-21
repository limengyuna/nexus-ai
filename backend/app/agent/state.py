"""
Agent 共享状态定义

LangGraph 的核心：所有节点读写同一个 State 对象，节点间通过修改 State 字段传递信息。
LangGraph 会自动用 reducer 合并 partial state（如 add_messages 自动追加消息）。

设计要点：
- 用 TypedDict 严格类型约束
- messages 用 Annotated + add_messages 实现"自动追加"语义
- 用 execution_trace 记录每个节点的执行细节，前端"思考过程"面板就靠它
"""
import time
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph.message import add_messages


# ---------- 子结构 ----------
class TraceStep(TypedDict, total=False):
    """单个 Agent 节点的执行记录"""
    node: str                    # 节点名（如 "router" / "rag_agent"）
    started_at: float            # 起始时间戳
    elapsed_ms: int              # 耗时（毫秒）
    input: Dict[str, Any]        # 关键输入摘要
    output: Dict[str, Any]       # 关键输出摘要
    error: Optional[str]         # 错误信息（如有）


class RetrievedDoc(TypedDict, total=False):
    """RAG 检索回来的单条结果"""
    chunk_id: str
    content: str
    score: float
    metadata: Dict[str, Any]
    adopted: bool  # 是否通过软过滤被 LLM 实际采用


class RetrievedMemory(TypedDict, total=False):
    """L2 检索出来的单条事实"""
    id: int
    content: str
    fact_type: str
    importance: float


class ToolCallRecord(TypedDict, total=False):
    """工具/Skill 调用记录"""
    name: str                    # 工具或技能名
    kind: str                    # "tool" / "skill" / "mcp_tool"
    arguments: Dict[str, Any]    # 调用参数
    result: Any                  # 执行结果（可截断）
    elapsed_ms: int              # 耗时
    error: Optional[str]


# ---------- 主 State ----------
class AgentState(TypedDict, total=False):
    """LangGraph 全局共享状态"""

    # ---------- 输入 ----------
    user_input: str                            # 当前用户原始输入
    session_id: Optional[int]                  # 关联的 ChatSession ID
    user_id: Optional[int]                     # 用户 ID
    kb_id: Optional[int]                       # 关联的知识库 ID（启用 RAG 时必填）

    # ---------- 上下文记忆 ----------
    summary: str                               # LLM 压缩的历史对话摘要
    messages: Annotated[List[Dict[str, Any]], add_messages]  # 当前轮次对话消息（追加式）
    context_messages: List[Dict[str, Any]]     # context_prep 统一注入的上下文（纯 dict，不经过 reducer）

    # ---------- Supervisor 决策 ----------
    intent: str                                # 意图标签：rag / tool / chitchat
    route_reason: str                          # Supervisor 的推理说明
    next_agent: str                            # Supervisor 当前决策：rag_agent / tool_agent / FINISH
    supervisor_instruction: str                # Supervisor 给子 Agent 的指令
    agent_iterations: int                      # Supervisor 循环计数（防止无限循环）
    task_plan: List[Dict[str, Any]]            # Supervisor 动态任务计划

    # ---------- RAG ----------
    retrieved_docs: List[RetrievedDoc]         # 检索结果

    # ---------- L2 Memory 事实库 ----------
    retrieved_memories: List[RetrievedMemory]   # 检索到的历史事实记忆

    # ---------- Tool / Skill ----------
    tool_calls: List[ToolCallRecord]           # 本轮所有工具/技能调用记录
    skill_used: Optional[str]                  # 使用的技能名称（如有）

    # ---------- 输出 ----------
    final_answer: str                          # 最终回答（流式时也会逐步填充完整）

    # ---------- 可观测性 ----------
    execution_trace: List[TraceStep]           # 节点执行链路追踪
    total_tokens: int                          # 本轮 Token 总消耗
    error: Optional[str]                       # 全局错误（fallback 节点设置）

    # ---------- 流式推送（仅 SSE 模式注入） ----------
    _token_queue: Any                          # queue.Queue，终端节点通过它实时推送 token 给前端


# ---------- 工具函数 ----------
def make_initial_state(
    user_input: str,
    *,
    session_id: Optional[int] = None,
    user_id: Optional[int] = None,
    kb_id: Optional[int] = None,
    summary: str = "",
) -> AgentState:
    """构造初始 AgentState"""
    return AgentState(
        user_input=user_input,
        session_id=session_id,
        user_id=user_id,
        kb_id=kb_id,
        summary=summary,
        messages=[],
        context_messages=[],
        intent="",
        route_reason="",
        next_agent="",
        supervisor_instruction="",
        agent_iterations=0,
        task_plan=[],
        retrieved_docs=[],
        retrieved_memories=[],
        tool_calls=[],
        skill_used=None,
        final_answer="",
        execution_trace=[],
        total_tokens=0,
        error=None,
    )


def append_trace(
    state: AgentState,
    node: str,
    started_at: float,
    input_summary: Optional[Dict[str, Any]] = None,
    output_summary: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> List[TraceStep]:
    """
    生成单步 trace 记录（返回 list 形式，便于 LangGraph state merge）

    LangGraph state merge 规则：
    - 没有 reducer 的字段直接覆盖
    - execution_trace 字段没用 reducer，所以节点要返回**完整新 list**
    - 我们的策略：每个节点读取 state["execution_trace"] + 自己的步骤，返回合并后的 list
    """
    elapsed_ms = int((time.time() - started_at) * 1000)
    step: TraceStep = {
        "node": node,
        "started_at": started_at,
        "elapsed_ms": elapsed_ms,
        "input": input_summary or {},
        "output": output_summary or {},
        "error": error,
    }
    return list(state.get("execution_trace", [])) + [step]
