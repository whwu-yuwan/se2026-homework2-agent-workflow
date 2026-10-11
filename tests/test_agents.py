"""
Agent 测试
测试 Agent 初始化、消息管理、工具执行
"""

import pytest
from unittest.mock import patch, MagicMock

from agents.base import BaseAgent
from agents.code_agent import CodeAgent
from agents.review_agent import ReviewAgent
from agents.fix_agent import FixAgent
from exceptions import ContextError


class TestBaseAgent:
    """测试 BaseAgent"""

    @patch("agents.base.ChatOpenAI")
    def test_agent_initialization(self, mock_llm):
        """测试 Agent 初始化"""
        agent = CodeAgent()
        assert agent.name == "CodeAgent"
        assert len(agent.messages) == 1  # SystemMessage
        assert agent.total_tokens_used == 0

    @patch("agents.base.ChatOpenAI")
    def test_agent_reset(self, mock_llm):
        """测试对话重置"""
        agent = CodeAgent()
        agent.messages.append(MagicMock(type="human", content="test"))
        agent.total_tokens_used = 100
        agent.reset()
        assert len(agent.messages) == 1
        assert agent.total_tokens_used == 0

    @patch("agents.base.ChatOpenAI")
    def test_message_count(self, mock_llm):
        """测试消息计数"""
        agent = CodeAgent()
        assert agent.message_count == 1  # 只有 SystemMessage

    @patch("agents.base.ChatOpenAI")
    def test_get_summary(self, mock_llm):
        """测试获取摘要"""
        agent = CodeAgent()
        summary = agent.get_summary()
        assert "CodeAgent" in summary

    @patch("agents.base.ChatOpenAI")
    def test_estimate_tokens(self, mock_llm):
        """测试 token 估算"""
        agent = CodeAgent()
        tokens = agent._estimate_tokens()
        assert tokens > 0  # SystemMessage 有内容

    @patch("agents.base.ChatOpenAI")
    def test_truncate_tool_result_short(self, mock_llm):
        """测试短结果不截断"""
        agent = CodeAgent()
        result = "short result"
        assert agent._truncate_tool_result(result) == result

    @patch("agents.base.ChatOpenAI")
    def test_input_too_long_raises_context_error(self, mock_llm):
        """测试输入过长抛出 ContextError"""
        agent = CodeAgent()
        # 构造一个超长输入
        long_input = "x" * 1000000
        with pytest.raises(ContextError):
            agent.run(long_input)

    @patch("agents.base.ChatOpenAI")
    def test_review_agent_no_tools(self, mock_llm):
        """测试 ReviewAgent 没有工具"""
        agent = ReviewAgent()
        assert agent.tools == []
        assert agent.tool_map == {}

    @patch("agents.base.ChatOpenAI")
    def test_fix_agent_no_tools(self, mock_llm):
        """测试 FixAgent 没有工具"""
        agent = FixAgent()
        assert agent.tools == []
        assert agent.tool_map == {}

    @patch("agents.base.ChatOpenAI")
    def test_code_agent_has_tools(self, mock_llm):
        """测试 CodeAgent 有工具"""
        agent = CodeAgent()
        assert len(agent.tools) > 0
        assert "read_file" in agent.tool_map
        assert "list_directory" in agent.tool_map
        assert "search_code" in agent.tool_map