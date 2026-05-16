"""
天气查询工具（Mock 实现）

为了避免依赖外部 API Key 与网络稳定性，这里返回伪造但合理的数据。
真实场景可以替换为调用 wttr.in / OpenWeather / 心知天气 等 API。
"""
import random
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.tools.registry import BaseTool, register_tool


class WeatherArgs(BaseModel):
    """天气查询工具的参数 schema"""
    city: str = Field(..., description="城市名称，例如：北京、上海、Tokyo")
    unit: Literal["celsius", "fahrenheit"] = Field(
        default="celsius",
        description="温度单位",
    )


@register_tool
class WeatherTool(BaseTool):
    """查询指定城市的当前天气"""

    name = "get_weather"
    description = "查询指定城市的当前天气状况，包括温度、湿度、风力等"
    args_schema = WeatherArgs

    # mock 天气池
    _conditions = ["晴", "多云", "小雨", "阴", "雷阵雨", "雾", "小雪"]

    def run(self, **kwargs) -> dict:
        args = WeatherArgs.model_validate(kwargs)
        # 用城市名 hash 保证同一城市每次查询结果一致（演示用稳定）
        seed = sum(ord(c) for c in args.city) % 1000
        random.seed(seed)

        temp_c = random.randint(-5, 35)
        if args.unit == "fahrenheit":
            temp = round(temp_c * 9 / 5 + 32, 1)
            unit_symbol = "°F"
        else:
            temp = temp_c
            unit_symbol = "°C"

        return {
            "city": args.city,
            "condition": random.choice(self._conditions),
            "temperature": f"{temp}{unit_symbol}",
            "humidity": f"{random.randint(40, 90)}%",
            "wind": f"{random.choice(['东', '南', '西', '北'])}风 {random.randint(1, 5)} 级",
            "source": "mock weather provider (for demo only)",
        }
