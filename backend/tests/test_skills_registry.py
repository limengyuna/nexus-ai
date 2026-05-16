"""
Skills 注册中心单测

验证：
1. 5 个 Skill 在启动时被自动注册
2. 触发关键词能正确预匹配到 Skill
"""
import pytest

from app.agent.skills import skill_registry  # 触发副作用注册


class TestSkillsRegistry:
    def test_all_skills_registered(self):
        """启动时应至少注册 5 个 Skill"""
        skills = skill_registry.list()
        names = {s.name for s in skills}
        assert "travel_planner" in names
        assert "data_analyst" in names
        assert "email_drafter" in names
        assert "document_summarizer" in names
        assert "research_assistant" in names

    def test_match_by_keyword(self):
        """关键词预匹配应能命中对应 Skill"""
        # "旅行" 命中 travel_planner
        skill = skill_registry.match_by_keywords("我想去成都旅行三天")
        assert skill is not None
        assert skill.name == "travel_planner"

        # "邮件" 命中 email_drafter
        skill = skill_registry.match_by_keywords("帮我起草一封请假邮件")
        assert skill is not None
        assert skill.name == "email_drafter"

        # 不相关问题应匹配不到
        skill = skill_registry.match_by_keywords("你好啊")
        assert skill is None
