import json
from typing import Any, Literal, Dict, Optional, Tuple
from pydantic import BaseModel

ToolStatus = Literal[
    "completed",
    "completed_unverified",
    "failed",
    "blocked",
    "needs_confirmation",
]

TrustLevel = Literal[
    "execution_verified",
    "external_unverified",
    "post_checked",
    "model_inferred",
    "failed",
]

class ToolVerification(BaseModel):
    trust_level: TrustLevel
    trust_basis: str
    read_only: bool | None = None
    side_effect_risk: Literal["none", "low", "medium", "high", "unknown"] = "unknown"
    requires_review: bool = False
    post_checked: bool = False
    post_check_basis: str | None = None

class NormalizedToolResult(BaseModel):
    ok: bool
    status: ToolStatus
    tool_name: str
    tool_type: Literal["builtin", "business", "mcp", "unknown"]
    data: Any | None = None
    error: str | None = None
    summary: str | None = None
    verification: ToolVerification
    raw_ref: str | None = None
    elapsed_ms: int | None = None


def detect_mcp_error(raw: Any) -> Tuple[bool, Optional[str]]:
    """
    检查 MCP 或者外部工具的返回结果中是否包含软错误。
    返回: (is_error, error_message)
    """
    if isinstance(raw, Exception):
        return True, str(raw)

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return _detect_dict_error(parsed)
        except json.JSONDecodeError:
            pass
        return False, None

    if isinstance(raw, dict):
        return _detect_dict_error(raw)
        
    return False, None


def _detect_dict_error(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    # 1. MCP 协议自带的 isError 标志
    if data.get("isError") is True:
        # 尝试从常见字段提取错误信息
        err_msg = data.get("error") or data.get("message") or str(data)
        return True, str(err_msg)

    # 2. 常见业务包装：ok=false, success=false
    if data.get("ok") is False or data.get("success") is False:
        err_msg = data.get("error") or data.get("message") or "操作未成功返回 (ok=false)"
        return True, str(err_msg)

    # 3. 常见业务状态码：status=error/failed
    status = data.get("status")
    if isinstance(status, str) and status.lower() in {"error", "failed"}:
        err_msg = data.get("error") or data.get("message") or f"返回状态为 {status}"
        return True, str(err_msg)

    # 4. 直接暴露了顶层 error 字段（值为字符串时高度怀疑是报错）
    err_val = data.get("error")
    if isinstance(err_val, str) and err_val.strip() != "":
        return True, err_val

    # 5. 检查 MCP 业务返回（text 字段）是否包含被序列化包装的 JSON 报错
    # 兼容多段 JSON 按行拼接的情况（如 {"value": 1}\n{"ok": false}）
    text_val = data.get("text")
    if isinstance(text_val, str) and text_val.strip() != "":
        for line in text_val.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                parsed_text = json.loads(line)
                if isinstance(parsed_text, dict):
                    is_err, msg = _detect_dict_error(parsed_text)
                    if is_err:
                        return True, msg
            except Exception:
                pass

    return False, None


def compact_for_llm(data: Any, max_list_len: int = 10, max_str_len: int = 2000) -> Any:
    """
    精简发给大模型的数据，防止过度消耗 Token。
    """
    if isinstance(data, list):
        if len(data) > max_list_len:
            truncated = [compact_for_llm(item, max_list_len, max_str_len) for item in data[:max_list_len]]
            truncated.append(f"...(截断了剩余 {len(data) - max_list_len} 条记录)")
            return truncated
        return [compact_for_llm(item, max_list_len, max_str_len) for item in data]
        
    elif isinstance(data, dict):
        return {k: compact_for_llm(v, max_list_len, max_str_len) for k, v in data.items()}
        
    elif isinstance(data, str):
        if len(data) > max_str_len:
            return data[:max_str_len] + f"...(文本过长，截断 {len(data) - max_str_len} 字符)"
        return data
        
    return data


def build_llm_tool_payload(result: NormalizedToolResult) -> dict:
    """
    抽取只给大模型看的核心字段，剥离所有后端管理标签如 trust_level, elapsed_ms 等。
    """
    if not result.ok:
        return {
            "status": "failed",
            "error": result.error or "tool call failed",
        }

    payload: Dict[str, Any] = {
        "status": "ok",
    }

    if result.summary:
        payload["summary"] = result.summary

    if result.data is not None:
        raw_data = result.data
        if result.tool_type == "mcp" and isinstance(raw_data, dict) and "text" in raw_data:
            text_val = raw_data["text"]
            try:
                payload["data"] = compact_for_llm(json.loads(text_val))
            except Exception:
                payload["data"] = compact_for_llm(text_val)
        else:
            payload["data"] = compact_for_llm(raw_data)

    return payload
