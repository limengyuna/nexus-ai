from typing import Any, Dict, List, Optional

# ==========================================
# 风险标记常量 (Risk Flags)
# ==========================================
RISK_AGENT_FAILED = "agent_failed"
RISK_AGENT_PARTIAL = "agent_partial"
RISK_LOW_FAITHFULNESS = "low_faithfulness"
RISK_UNSUPPORTED_CLAIMS = "unsupported_claims"
RISK_NO_RETRIEVED_DOCS = "no_retrieved_docs"
RISK_TOOL_CALL_FAILED = "tool_call_failed"
RISK_APPROVAL_REQUIRED = "approval_required"
RISK_SIDE_EFFECT_DETECTED = "side_effect_detected"
RISK_EMPTY_TOOL_RESULT = "empty_tool_result"
RISK_BUSINESS_QUERY_FAILED = "business_query_failed"
RISK_INVALID_DATA_SCOPE = "invalid_data_scope"
RISK_NON_READ_ONLY_BUSINESS_TOOL = "non_read_only_business_tool"
RISK_EMPTY_BUSINESS_CONTEXT = "empty_business_context"
RISK_PERMISSION_ERROR = "permission_error"
RISK_MISSING_REQUIRED_CONTEXT = "missing_required_context"
RISK_ANSWER_TOOL_MISMATCH = "answer_tool_mismatch"
RISK_FAKE_CITATION = "fake_citation"
RISK_MISMATCHED_CITATION = "mismatched_citation"
RISK_MISSING_CITATION_FORMAT = "missing_citation_format"

KNOWN_RISK_FLAGS = {
    RISK_AGENT_FAILED,
    RISK_AGENT_PARTIAL,
    RISK_LOW_FAITHFULNESS,
    RISK_UNSUPPORTED_CLAIMS,
    RISK_NO_RETRIEVED_DOCS,
    RISK_TOOL_CALL_FAILED,
    RISK_APPROVAL_REQUIRED,
    RISK_SIDE_EFFECT_DETECTED,
    RISK_EMPTY_TOOL_RESULT,
    RISK_BUSINESS_QUERY_FAILED,
    RISK_INVALID_DATA_SCOPE,
    RISK_NON_READ_ONLY_BUSINESS_TOOL,
    RISK_EMPTY_BUSINESS_CONTEXT,
    RISK_PERMISSION_ERROR,
    RISK_MISSING_REQUIRED_CONTEXT,
    RISK_ANSWER_TOOL_MISMATCH,
    RISK_FAKE_CITATION,
    RISK_MISMATCHED_CITATION,
    RISK_MISSING_CITATION_FORMAT,
}

def normalize_risk_flags(flags: List[str]) -> List[str]:
    """过滤未知的风险标记"""
    return [flag for flag in flags if flag in KNOWN_RISK_FLAGS]


# ==========================================
# Supervisor 消费策略
# ==========================================
def select_review_mode(observation: Dict[str, Any], step: Dict[str, Any]) -> str:
    """决定 Supervisor 读取上下文的模式：summary / evidence / full"""
    status = observation.get("status")
    
    if status == "failed":
        return "full"

    if status == "partial":
        return "evidence"

    if observation.get("evidence", {}).get("external_unverified_tools"):
        return "evidence"

    if observation.get("risk_flags"):
        return "evidence"

    if step.get("needs_previous_output"):
        return "evidence"

    return "summary"


# ==========================================
# 构造函数
# ==========================================
def build_rag_observation(
    retrieved_docs: List[Dict[str, Any]],
    faithfulness: Optional[Dict[str, Any]],
    answer: str,
    is_error: bool = False,
    extra_risk_flags: List[str] = None
) -> Dict[str, Any]:
    total_claims = faithfulness.get("total_claims", 0) if faithfulness else 0
    supported_claims = faithfulness.get("supported_claims", 0) if faithfulness else 0
    unsupported_claims = max(total_claims - supported_claims, 0)
    faithfulness_score = faithfulness.get("score") if faithfulness else None

    risk_flags = []
    status = "success"

    if is_error:
        risk_flags.append(RISK_AGENT_FAILED)
        status = "failed"
    elif not retrieved_docs:
        risk_flags.append(RISK_NO_RETRIEVED_DOCS)
        status = "failed"
    
    if faithfulness_score is not None and faithfulness_score >= 0 and faithfulness_score < 0.8:
        risk_flags.append(RISK_LOW_FAITHFULNESS)
    if unsupported_claims > 0:
        risk_flags.append(RISK_UNSUPPORTED_CLAIMS)
        
    if extra_risk_flags:
        risk_flags.extend(extra_risk_flags)

    if status != "failed" and risk_flags:
        status = "partial"

    adopted_docs = sum(1 for d in retrieved_docs if d.get("adopted")) if retrieved_docs else 0
    top_score = retrieved_docs[0].get("score") if retrieved_docs and "score" in retrieved_docs[0] else None

    return {
        "agent": "rag_agent",
        "status": status,
        "summary": f"RAG 检索 {len(retrieved_docs)} 段资料，回答 {len(answer)} 字",
        "quality_signals": {
            "faithfulness_score": faithfulness_score,
            "retrieved_docs_count": len(retrieved_docs),
            "adopted_docs_count": adopted_docs,
            "unsupported_claims": unsupported_claims,
            "top_score": top_score,
        },
        "risk_flags": normalize_risk_flags(risk_flags),
        "evidence": {
            "retrieved_docs_summary": [
                {"source": d.get("metadata", {}).get("title") or d.get("metadata", {}).get("file_name", "未知来源"), "summary": str(d.get("content", ""))[:100]}
                for d in (retrieved_docs or [])
            ]
        },
        "public_answer_ref": "state.final_answer",
        "public_answer_preview": answer[:1500] if answer else "",
    }


def build_tool_observation(tool_calls: List[Dict[str, Any]], answer: str) -> Dict[str, Any]:
    from app.agent.tools.danger import is_dangerous_tool
    
    total_calls = len(tool_calls)
    failed_calls = 0
    successful_calls = 0
    used_mcp = False
    has_side_effects = False
    needs_approval = False
    error_count = 0
    
    system_verified = []
    external_unverified = []
    failures = []

    for tc in tool_calls:
        raw_kind = tc.get("kind", "")
        used_mcp = used_mcp or raw_kind == "mcp_tool"
        danger_kind = "internal" if raw_kind == "tool" else "mcp" if raw_kind == "mcp_tool" else raw_kind
        if is_dangerous_tool(tc.get("name", ""), danger_kind):
            has_side_effects = True
            needs_approval = True

        res = tc.get("result", {})
        trust = "unknown"
        if isinstance(res, dict) and "verification" in res:
            trust = res["verification"].get("trust_level", "unknown")
            is_err = not res.get("ok", True)
        else:
            is_err = tc.get("error") or (isinstance(res, dict) and res.get("error"))
            
        if is_err:
            failed_calls += 1
            error_count += 1
        else:
            successful_calls += 1
            
        preview = str(res)[:200]
        ev = {
            "name": tc.get("name"), 
            "status": "failed" if is_err else "success",
            "trust_level": trust,
            "tool_type": res.get("tool_type", "unknown") if isinstance(res, dict) else "unknown",
            "result_preview": preview
        }
        
        if is_err:
            failures.append(ev)
        elif trust == "execution_verified":
            system_verified.append(ev)
        elif trust == "external_unverified":
            external_unverified.append(ev)
        else:
            external_unverified.append(ev)
    
    risk_flags = []
    if failed_calls > 0:
        risk_flags.append(RISK_TOOL_CALL_FAILED)
    if needs_approval:
        risk_flags.append(RISK_APPROVAL_REQUIRED)
    if has_side_effects:
        risk_flags.append(RISK_SIDE_EFFECT_DETECTED)
    if total_calls > 0 and all(not str(tc.get("result", "")).strip() for tc in tool_calls):
         risk_flags.append(RISK_EMPTY_TOOL_RESULT)

    status = "success"
    if failed_calls == total_calls and total_calls > 0:
        status = "failed"
    elif risk_flags or (total_calls == 0 and len(answer) > 0): # 生成了回答但没调用工具
        status = "partial"

    return {
        "agent": "tool_agent",
        "status": status,
        "summary": f"执行了 {total_calls} 次工具调用，{successful_calls} 成功，{failed_calls} 失败",
        "quality_signals": {
            "tool_calls_count": total_calls,
            "successful_tool_calls": successful_calls,
            "failed_tool_calls": failed_calls,
            "used_mcp": used_mcp,
            "has_side_effects": has_side_effects,
            "needs_approval": needs_approval,
        },
        "risk_flags": normalize_risk_flags(risk_flags),
        "evidence": {
            "system_verified_tools": system_verified,
            "external_unverified_tools": external_unverified,
            "failed_tools": failures
        },
        "public_answer_ref": "state.final_answer",
        "public_answer_preview": answer[:1500] if answer else "",
    }


def build_business_context_observation(context_records: List[Dict[str, Any]], answer: str) -> Dict[str, Any]:
    total_queries = len(context_records)
    def _is_failed_record(record: Dict[str, Any]) -> bool:
        if record.get("trust_level") == "failed" or record.get("status") == "failed" or record.get("error"):
            return True
        result = record.get("result")
        return isinstance(result, dict) and bool(result.get("error"))

    failed_queries = sum(1 for c in context_records if _is_failed_record(c))
    successful_queries = total_queries - failed_queries
    
    has_empty_result = False
    system_verified = []
    failures = []
    
    for c in context_records:
        res = c.get("result")
        if not res or (isinstance(res, list) and len(res) == 0):
            has_empty_result = True
            
        trust = c.get("trust_level", "execution_verified")
        is_err = _is_failed_record(c) or trust == "failed"
        
        preview = str(res)[:200]
        ev = {
            "name": c.get("name") or c.get("tool"),
            "status": "failed" if is_err else "success",
            "result_preview": preview
        }
        if is_err:
            failures.append(ev)
        else:
            system_verified.append(ev)
            
    risk_flags = []
    if failed_queries > 0:
        risk_flags.append(RISK_BUSINESS_QUERY_FAILED)
    if has_empty_result:
        risk_flags.append(RISK_EMPTY_BUSINESS_CONTEXT)
        
    status = "success"
    if failed_queries == total_queries and total_queries > 0:
        status = "failed"
    elif risk_flags:
        status = "partial"
        
    return {
        "agent": "business_context_agent",
        "status": status,
        "summary": f"执行了 {total_queries} 次业务数据查询，{successful_queries} 成功，{failed_queries} 失败",
        "quality_signals": {
            "business_tools_count": total_queries,
            "successful_queries": successful_queries,
            "failed_queries": failed_queries,
            "data_scope": "current_user",
            "read_only": True,
            "has_empty_result": has_empty_result,
        },
        "risk_flags": normalize_risk_flags(risk_flags),
        "evidence": {
            "system_verified_context": system_verified,
            "failed_context": failures
        },
        "public_answer_ref": "state.final_answer",
        "public_answer_preview": answer[:1500] if answer else "",
    }
