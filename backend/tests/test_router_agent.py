"""
Router Agent 单测

验证：
1. Skill 关键词命中 → 直接路由到 tool（不调 LLM，省钱）
2. 带 kb_id 时强制走 LLM 分类（不能用关键词捷径）
3. LLM 失败 → 优雅降级到 chitchat
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.agent.nodes.router import router_node
from app.agent.state import make_initial_state


class TestRouter:
    def test_keyword_match_skips_llm(self):
        """命中 Skill 关键词应直接走 tool 路径，不调 LLM"""
        state = make_initial_state(
            user_input="我想去成都旅行三天",
            session_id=1, user_id=1, kb_id=None, summary="",
        )

        # 即使 LLM 不可用，关键词匹配也能工作（不调 LLM）
        with patch("app.agent.nodes.router.get_llm") as mock_get_llm:
            result = router_node(state)

        assert result["intent"] == "tool", "旅行关键词应路由到 tool"
        # 关键：未调用 LLM
        mock_get_llm.assert_not_called()
        assert "travel_planner" in result["route_reason"]

    def test_llm_classification_rag(self):
        """带 kb_id 时走 LLM 分类，mock LLM 返回 'rag'"""
        state = make_initial_state(
            user_input="文档里提到什么技术栈？",
            session_id=1, user_id=1, kb_id=42, summary="",  # 关联 KB
        )

        fake_llm = MagicMock()
        fake_llm.complete.return_value = json.dumps(
            {"intent": "rag", "reason": "用户询问文档内容"}
        )
        with patch("app.agent.nodes.router.get_llm", return_value=fake_llm):
            result = router_node(state)

        assert result["intent"] == "rag"
        fake_llm.complete.assert_called_once()

    def test_llm_failure_falls_back_to_chitchat(self):
        """LLM 抛异常 → 应降级到 chitchat 而不是崩溃"""
        state = make_initial_state(
            user_input="今天天气如何？这不是技能也不是 RAG",
            session_id=1, user_id=1, kb_id=None, summary="",
        )

        fake_llm = MagicMock()
        fake_llm.complete.side_effect = RuntimeError("LLM API timeout")
        with patch("app.agent.nodes.router.get_llm", return_value=fake_llm):
            result = router_node(state)

        # 不抛异常，降级到 chitchat
        assert result["intent"] == "chitchat"
        assert "降级" in result["route_reason"] or "failed" in result["route_reason"].lower()
