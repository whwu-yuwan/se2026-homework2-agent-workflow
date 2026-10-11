"""
Agent 注册表测试
"""

import pytest
from unittest.mock import patch

from agents.registry import AgentRegistry, default_registry
from agents.code_agent import CodeAgent
from agents.review_agent import ReviewAgent
from agents.fix_agent import FixAgent


class TestAgentRegistry:
    """测试 Agent 注册表"""

    def test_default_registry_has_all_agents(self):
        """测试默认注册表包含所有内置 Agent"""
        assert default_registry.has("CodeAgent")
        assert default_registry.has("ReviewAgent")
        assert default_registry.has("FixAgent")
        assert len(default_registry.list_agents()) == 3

    @patch("agents.base.ChatOpenAI")
    def test_create_agent_by_name(self, mock_llm):
        """测试通过名称创建 Agent"""
        agent = default_registry.create("CodeAgent")
        assert isinstance(agent, CodeAgent)
        assert agent.name == "CodeAgent"

    @patch("agents.base.ChatOpenAI")
    def test_create_agent_with_custom_prompt(self, mock_llm):
        """测试创建时传入自定义参数"""
        agent = default_registry.create("ReviewAgent", system_prompt="自定义提示")
        assert agent.system_prompt == "自定义提示"

    def test_create_unknown_agent_raises_error(self):
        """测试创建未注册的 Agent 抛出 KeyError"""
        with pytest.raises(KeyError, match="未注册的 Agent"):
            default_registry.create("UnknownAgent")

    def test_custom_registry(self):
        """测试自定义注册表"""
        registry = AgentRegistry()
        assert not registry.has("CodeAgent")

        registry.register(CodeAgent)
        assert registry.has("CodeAgent")
        assert "CodeAgent" in registry.list_agents()

    @patch("agents.base.ChatOpenAI")
    def test_register_and_create(self, mock_llm):
        """测试注册后创建"""
        registry = AgentRegistry()
        registry.register(FixAgent)
        agent = registry.create("FixAgent")
        assert isinstance(agent, FixAgent)