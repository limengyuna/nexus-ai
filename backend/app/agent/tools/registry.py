"""
工具基类与注册中心

设计原则：
- 工具用 Pydantic Schema 描述参数（自动生成 JSON Schema 给 LLM）
- 装饰器 @register_tool() 自动注册到全局
- 注册中心可一次性导出 OpenAI Function Calling schema 列表
"""
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Type

from loguru import logger
from pydantic import BaseModel


# ---------- 工具基类 ----------
class BaseTool(ABC):
    """
    工具基类，所有工具继承此类。

    子类必须实现：
    - name: 唯一名称（snake_case）
    - description: 给 LLM 看的功能描述
    - args_schema: Pydantic 模型，定义入参 schema
    - run(**kwargs): 实际执行逻辑
    """

    name: str = ""
    description: str = ""
    args_schema: Optional[Type[BaseModel]] = None

    @abstractmethod
    def run(self, **kwargs) -> Any:
        """执行工具，返回结果（任意可 JSON 序列化的类型）"""
        raise NotImplementedError

    def to_openai_schema(self) -> Dict[str, Any]:
        """转换为 OpenAI Function Calling 格式"""
        if self.args_schema is None:
            parameters = {"type": "object", "properties": {}, "required": []}
        else:
            # Pydantic v2 提供 model_json_schema()，直接得到符合 JSON Schema 标准的 dict
            parameters = self.args_schema.model_json_schema()
            # 去掉 pydantic 自带的 title 字段，避免污染 LLM 看到的 schema
            parameters.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }


# ---------- 注册中心 ----------
class ToolRegistry:
    """全局工具注册表"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if not tool.name:
            raise ValueError("Tool 必须定义 name")
        if tool.name in self._tools:
            logger.warning("工具 {} 已注册，覆盖", tool.name)
        self._tools[tool.name] = tool
        logger.info("✓ 注册工具: {}", tool.name)

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list(self) -> List[BaseTool]:
        return list(self._tools.values())

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """导出所有工具的 OpenAI Function Calling schema 列表"""
        return [t.to_openai_schema() for t in self._tools.values()]


# 全局单例
tool_registry = ToolRegistry()


# ---------- 装饰器：方便注册 ----------
def register_tool(tool_cls: Type[BaseTool]) -> Type[BaseTool]:
    """
    类装饰器：定义工具类后自动实例化并注册

    用法::

        @register_tool
        class WeatherTool(BaseTool):
            name = "weather"
            ...
    """
    tool_registry.register(tool_cls())
    return tool_cls


# ---------- 便捷别名 ----------
def get_tool(name: str) -> Optional[BaseTool]:
    return tool_registry.get(name)


def list_tools() -> List[BaseTool]:
    return tool_registry.list()
