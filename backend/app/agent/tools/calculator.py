"""
计算器工具

用安全的 ast.parse 解析表达式，避免 eval 注入。
只允许 + - * / ** % 以及基本数学函数。
"""
import ast
import math
import operator
from typing import Any

from pydantic import BaseModel, Field

from app.agent.tools.registry import BaseTool, register_tool


# ---------- 安全表达式求值 ----------
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_ALLOWED_FUNCS = {
    "sqrt": math.sqrt,
    "pow": math.pow,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "round": round,
    "max": max,
    "min": min,
}
_ALLOWED_NAMES = {"pi": math.pi, "e": math.e}


def _safe_eval(node: ast.AST) -> Any:
    """递归求值 AST 节点，仅允许安全操作"""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_BINOPS:
            raise ValueError(f"不允许的二元运算: {op_type.__name__}")
        return _ALLOWED_BINOPS[op_type](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARYOPS:
            raise ValueError(f"不允许的一元运算: {op_type.__name__}")
        return _ALLOWED_UNARYOPS[op_type](_safe_eval(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise ValueError(f"不允许的函数调用")
        args = [_safe_eval(a) for a in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    if isinstance(node, ast.Name):
        if node.id not in _ALLOWED_NAMES:
            raise ValueError(f"未知标识符: {node.id}")
        return _ALLOWED_NAMES[node.id]
    raise ValueError(f"不允许的表达式节点: {type(node).__name__}")


class CalculatorArgs(BaseModel):
    expression: str = Field(
        ...,
        description="数学表达式字符串，支持 + - * / ** %、常量(pi, e)、函数(sqrt, log, sin, cos 等)。例：(1+2)*3、sqrt(16)+log(100,10)",
    )


@register_tool
class CalculatorTool(BaseTool):
    """安全的数学表达式计算器"""

    name = "calculate"
    description = "执行数学计算。支持四则运算、幂运算、常用数学函数（sqrt/log/sin/cos 等）和常量（pi、e）。"
    args_schema = CalculatorArgs

    def run(self, **kwargs) -> dict:
        args = CalculatorArgs.model_validate(kwargs)
        try:
            tree = ast.parse(args.expression, mode="eval")
            result = _safe_eval(tree)
            return {"expression": args.expression, "result": result}
        except Exception as e:
            return {"expression": args.expression, "error": str(e)}
