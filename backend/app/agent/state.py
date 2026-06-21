"""
Agent 共享状态定义

LangGraph 的核心：所有节点读写同一个 State 对象，节点间通过修改 State 字段传递信息。
LangGraph 会自动用 reducer 合并 partial state（如 add_messages 自动追加消息）。

设计要点：
- 用 TypedDict 严格类型约束
- messages 用 Annotated + add_messages 实现"自动追加"语义
- 用 execution_trace 记录每个节点的执行细节，前端"思考过程"面板就靠它
"""
import operator
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


class FaithfulnessClaim(TypedDict, total=False):
    """单条忠实性声明校验结果"""
    text: str                        # 从回答中提取的事实声明
    supported: bool                  # 是否有资料支撑
    source_index: int                # 支撑该声明的资料编号（从 1 开始，0 表示无来源）
    reason: str                      # 判断理由（简短说明）


class FaithfulnessResult(TypedDict, total=False):
    """忠实性校验整体结果"""
    score: float                     # 忠实度评分（0.0 ~ 1.0，有来源支撑的声明占比）
    claims: list                     # List[FaithfulnessClaim]
    total_claims: int                # 声明总数
    supported_claims: int            # 有来源支撑的声明数
    elapsed_ms: int                  # 校验耗时（毫秒）


class ToolCallRecord(TypedDict, total=False):
    """工具/Skill 调用记录"""
    name: str                    # 工具或技能名
    kind: str                    # "tool" / "skill" / "mcp_tool"
    arguments: Dict[str, Any]    # 调用参数
    result: Any                  # 执行结果（可截断）
    elapsed_ms: int              # 耗时
    error: Optional[str]
    step: int                    # 归属的执行计划步骤编号


class BusinessContextRecord(TypedDict, total=False):
    """单条受控业务上下文记录"""
    name: str
    arguments: Dict[str, Any]
    result: Any
    elapsed_ms: int
    error: Optional[str]
    trust_level: str


class StepOutput(TypedDict, total=False):
    step: int
    agent: str
    instruction: str
    status: str
    answer: str
    summary: str
    evidence_refs: List[Dict[str, Any]]
    evidence_preview: List[Dict[str, Any]]
    artifacts: List[Dict[str, Any]]
    system_verified: List[Dict[str, Any]]
    external_unverified: List[Dict[str, Any]]
    inferred: List[Dict[str, Any]]
    model_generated: List[str]
    failures: List[str]
    risk_flags: List[str]


class SynthesisClaim(TypedDict, total=False):
    text: str
    source_step_ids: List[int]
    evidence_refs: List[Dict[str, Any]]
    trust_level: str
    risk_flags: List[str]


class AgentObservation(TypedDict, total=False):
    """分层结果契约：子 Agent 返回给 Supervisor 的结构化执行信号"""
    agent: str
    status: str
    summary: str
    quality_signals: Dict[str, Any]
    risk_flags: List[str]
    evidence: Dict[str, Any]
    public_answer_ref: str
    public_answer_preview: str
    system_verified: List[Dict[str, Any]]
    external_unverified: List[Dict[str, Any]]
    inferred: List[Dict[str, Any]]
    model_generated: List[str]
    failures: List[str]


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
    step_contexts: Dict[int, str]              # 每个 step 执行时需要的上下文（按 step number 索引，Supervisor 显式打包）

    # ---------- RAG ----------
    retrieved_docs: List[RetrievedDoc]         # 检索结果
    faithfulness: Dict[str, Any]               # 忠实性校验结果（FaithfulnessResult）

    # ---------- L2 Memory 事实库 ----------
    retrieved_memories: List[RetrievedMemory]   # 检索到的历史事实记忆
    
    # ---------- User Profile Slots ----------
    injected_profile_slots: Annotated[List[Dict[str, Any]], operator.add] # 注入的结构化长期偏好

    # ---------- Tool / Skill ----------
    tool_calls: List[ToolCallRecord]           # 本轮所有工具/技能调用记录
    skill_used: Optional[str]                  # 使用的技能名称（如有）

    # ---------- 输出 ----------
    final_answer: str                          # 最终回答（流式时也会逐步填充完整）
    retrieved_business_context: Annotated[List[BusinessContextRecord], operator.add]
    
    # ---------- 分层结果契约 ----------
    agent_observations: Annotated[List[AgentObservation], operator.add]
    latest_observation: Optional[AgentObservation]
    
    # ---------- Synthesis 架构支持 ----------
    step_outputs: Annotated[List[StepOutput], operator.add]
    response_mode: str                         # "pending", "direct", "deferred"
    public_answer_started: bool
    response_mode_locked: bool
    synthesis_required: bool
    synthesis_completed: bool

    # ---------- 可观测性 ----------
    execution_trace: List[TraceStep]           # 节点执行链路追踪
    total_tokens: int                          # 本轮 Token 总消耗
    error: Optional[str]                       # 全局错误（fallback 节点设置）

    # ---------- 中断/审批（Checkpoint + Interrupt 机制） ----------
    pending_approval: Optional[Dict[str, Any]] # 等待用户审批的危险操作详情（tool_agent 写入）
    approval_decision: Optional[Dict[str, Any]] # 用户审批决定（resume 时由 Command 注入）
    # 注：流式队列已从 state 移出，改用 app.agent.stream_queue 全局注册表
    # 原因：queue.Queue 无法被 LangGraph Checkpointer 序列化

    # ---------- 跨轮中断续跑 ----------
    # 上一轮被用户中断时持久化的 task_plan 元信息（来自 ChatMessage.task_plan_meta），
    # 由 chat_service 在调用 graph 前注入。结构：
    # {"task_plan": [{"step": 1, "agent": "tool_agent", "instruction": "...", "status": "completed"|"cancelled"}, ...],
    #  "interrupted": true}
    # supervisor 规划阶段读取此字段，让 LLM 跳过已完成的 step、重跑被中断的 step。
    last_task_plan_meta: Optional[Dict[str, Any]]


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
        step_contexts={},
        retrieved_docs=[],
        faithfulness={},
        retrieved_memories=[],
        injected_profile_slots=[],
        tool_calls=[],
        skill_used=None,
        final_answer="",
        retrieved_business_context=[],
        execution_trace=[],
        total_tokens=0,
        error=None,
        pending_approval=None,
        approval_decision=None,
        last_task_plan_meta=None,
        agent_observations=[],
        latest_observation=None,
        step_outputs=[],
        response_mode="pending",
        public_answer_started=False,
        response_mode_locked=False,
        synthesis_required=False,
        synthesis_completed=False,
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
