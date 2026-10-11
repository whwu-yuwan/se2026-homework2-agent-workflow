"""
Agent 测试
测试 Agent 初始化、消息管理、工具执行、run() 循环、上下文裁剪
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from agents.base import BaseAgent
from agents.code_agent import CodeAgent
from agents.review_agent import ReviewAgent
from agents.fix_agent import FixAgent
from exceptions import ContextError, APIError


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
    def test_review_agent_has_tools(self, mock_llm):
        """测试 ReviewAgent 绑定了工具"""
        agent = ReviewAgent()
        assert len(agent.tools) > 0
        assert "read_file" in agent.tool_map
        assert "search_code" in agent.tool_map

    @patch("agents.base.ChatOpenAI")
    def test_fix_agent_has_tools(self, mock_llm):
        """测试 FixAgent 绑定了工具"""
        agent = FixAgent()
        assert len(agent.tools) > 0
        assert "read_file" in agent.tool_map
        assert "execute_python" in agent.tool_map

    @patch("agents.base.ChatOpenAI")
    def test_code_agent_has_tools(self, mock_llm):
        """测试 CodeAgent 有工具"""
        agent = CodeAgent()
        assert len(agent.tools) > 0
        assert "read_file" in agent.tool_map
        assert "list_directory" in agent.tool_map
        assert "search_code" in agent.tool_map

    @patch("agents.base.ChatOpenAI")
    def test_custom_system_prompt(self, mock_llm):
        """测试构造函数传入自定义 system_prompt"""
        custom_prompt = "你是自定义助手"
        agent = CodeAgent(system_prompt=custom_prompt)
        assert agent.system_prompt == custom_prompt
        assert agent.messages[0].content == custom_prompt

    @patch("agents.base.ChatOpenAI")
    def test_default_system_prompt(self, mock_llm):
        """测试默认 system_prompt"""
        agent = CodeAgent()
        assert agent.system_prompt == CodeAgent.default_system_prompt

    @patch("agents.base.ChatOpenAI")
    def test_custom_tools(self, mock_llm):
        """测试构造函数传入自定义 tools"""
        from tools import read_file
        agent = CodeAgent(tools=[read_file])
        assert len(agent.tools) == 1
        assert "read_file" in agent.tool_map

    # ─── run() 方法测试 ───────────────────────────────────────

    @patch("agents.base.ChatOpenAI")
    def test_run_simple_response(self, mock_llm_cls):
        """测试 run() 正常文本回复（无工具调用）"""
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        # 模拟 LLM 返回文本回复
        response = AIMessage(content="这是回复")
        response.tool_calls = []
        response.usage_metadata = {"total_tokens": 50}
        mock_llm.invoke.return_value = response

        agent = ReviewAgent()
        # 覆盖 llm_with_tools 为同一个 mock（ReviewAgent 现在有工具）
        agent.llm_with_tools = mock_llm

        result = agent.run("请审查这段代码")

        assert result == "这是回复"
        assert agent.message_count == 3  # System + Human + AI

    @patch("agents.base.ChatOpenAI")
    def test_run_with_tool_calls(self, mock_llm_cls):
        """测试 run() 包含工具调用的循环"""
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        # 第一次返回工具调用，第二次返回文本
        tool_response = AIMessage(content="")
        tool_response.tool_calls = [{
            "name": "read_file",
            "args": {"file_path": "test.py"},
            "id": "call_123",
        }]
        tool_response.usage_metadata = {"total_tokens": 30}

        text_response = AIMessage(content="代码分析结果")
        text_response.tool_calls = []
        text_response.usage_metadata = {"total_tokens": 50}

        mock_llm.invoke.side_effect = [tool_response, text_response]

        # 模拟工具执行
        mock_tool = MagicMock()
        mock_tool.name = "read_file"
        mock_tool.invoke.return_value = "print('hello')"

        agent = CodeAgent()
        agent.tool_map = {"read_file": mock_tool}

        # 需要让 llm_with_tools 也返回正确的值
        agent.llm_with_tools = mock_llm

        result = agent.run("读取 test.py")

        assert "代码分析结果" in result
        assert mock_tool.invoke.called

    @patch("agents.base.ChatOpenAI")
    def test_run_empty_response_fallback(self, mock_llm_cls):
        """测试 run() LLM 返回空内容时的兜底"""
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        response = AIMessage(content="")
        response.tool_calls = []
        response.usage_metadata = {"total_tokens": 10}
        mock_llm.invoke.return_value = response

        agent = ReviewAgent()
        agent.llm_with_tools = mock_llm

        result = agent.run("test")
        assert "未生成有效回复" in result

    @patch("agents.base.ChatOpenAI")
    def test_run_api_error_rollback(self, mock_llm_cls):
        """测试 run() API 错误时回滚消息历史"""
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        mock_llm.invoke.side_effect = Exception("API connection failed")

        agent = ReviewAgent()
        agent.llm_with_tools = mock_llm

        initial_count = agent.message_count

        with pytest.raises(APIError):
            agent.run("test")

        # 应该回滚到初始状态
        assert agent.message_count == initial_count

    @patch("agents.base.ChatOpenAI")
    def test_run_tool_error_handled(self, mock_llm_cls):
        """测试 run() 工具执行错误被捕获并转为 ToolMessage"""
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        # 第一次返回工具调用
        tool_response = AIMessage(content="")
        tool_response.tool_calls = [{
            "name": "read_file",
            "args": {"file_path": "nonexistent.py"},
            "id": "call_456",
        }]
        tool_response.usage_metadata = {"total_tokens": 30}

        # 第二次返回文本（包含错误信息的回复）
        text_response = AIMessage(content="文件不存在，请检查路径")
        text_response.tool_calls = []
        text_response.usage_metadata = {"total_tokens": 50}

        mock_llm.invoke.side_effect = [tool_response, text_response]

        # 模拟工具抛出异常
        mock_tool = MagicMock()
        mock_tool.name = "read_file"
        mock_tool.invoke.side_effect = Exception("文件不存在")

        agent = CodeAgent()
        agent.tool_map = {"read_file": mock_tool}
        agent.llm_with_tools = mock_llm

        result = agent.run("读取 nonexistent.py")

        # 工具错误应该被捕获，Agent 继续运行
        assert "文件不存在" in result
        # 应该有 ToolMessage 记录错误
        tool_msgs = [m for m in agent.messages if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 1
        assert "工具执行异常" in tool_msgs[0].content

    @patch("agents.base.ChatOpenAI")
    def test_run_max_iterations_force_response(self, mock_llm_cls):
        """测试 run() 达到最大工具调用轮次时强制回复"""
        import config as cfg
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        # 构造 MAX_TOOL_CALLS_PER_TURN 个工具调用响应
        def make_tool_response(idx):
            resp = AIMessage(content="")
            resp.tool_calls = [{
                "name": "read_file",
                "args": {"file_path": "test.py"},
                "id": f"call_{idx}",
            }]
            resp.usage_metadata = {"total_tokens": 10}
            return resp

        # 强制回复
        force_response = AIMessage(content="最终回复")
        force_response.usage_metadata = {"total_tokens": 20}

        # side_effect: N 次工具调用 + 1 次强制回复
        side_effects = [make_tool_response(i) for i in range(cfg.MAX_TOOL_CALLS_PER_TURN)]
        side_effects.append(force_response)
        mock_llm.invoke.side_effect = side_effects

        mock_tool = MagicMock()
        mock_tool.name = "read_file"
        mock_tool.invoke.return_value = "file content"

        agent = CodeAgent()
        agent.tool_map = {"read_file": mock_tool}
        agent.llm_with_tools = mock_llm

        result = agent.run("test")
        assert "最终回复" in result

    @patch("agents.base.ChatOpenAI")
    def test_context_trimming(self, mock_llm_cls):
        """测试上下文裁剪功能"""
        import config as cfg
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        agent = ReviewAgent()

        # 手动添加大量消息模拟上下文溢出
        # 添加多对 HumanMessage + AIMessage
        original_threshold = cfg.TRIM_THRESHOLD_TOKENS
        try:
            # 临时降低阈值以便触发裁剪
            cfg.TRIM_THRESHOLD_TOKENS = 100

            # 添加大量消息
            for i in range(20):
                agent.messages.append(HumanMessage(content=f"消息 {i} " * 50))
                agent.messages.append(AIMessage(content=f"回复 {i} " * 50))

            initial_count = len(agent.messages)
            agent._trim_context()

            # 裁剪后消息数应该减少
            assert len(agent.messages) < initial_count
            # SystemMessage 应该保留
            assert isinstance(agent.messages[0], SystemMessage)
        finally:
            cfg.TRIM_THRESHOLD_TOKENS = original_threshold

    @patch("agents.base.ChatOpenAI")
    def test_estimate_msg_tokens(self, mock_llm_cls):
        """测试单条消息 token 估算"""
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        agent = ReviewAgent()

        msg = HumanMessage(content="hello world")
        tokens = agent._estimate_msg_tokens(msg)
        assert tokens > 0

    @patch("agents.base.ChatOpenAI")
    def test_truncate_tool_result_long(self, mock_llm_cls):
        """测试长工具结果被截断"""
        import config as cfg
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        agent = CodeAgent()

        # 创建超过限制的长结果
        long_result = "x" * 50000
        truncated = agent._truncate_tool_result(long_result)

        # 应该被截断
        assert len(truncated) < len(long_result)
        assert "截断" in truncated

    @patch("agents.base.ChatOpenAI")
    def test_update_token_stats(self, mock_llm_cls):
        """测试 token 统计更新"""
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        agent = ReviewAgent()

        response = AIMessage(content="test")
        response.usage_metadata = {"total_tokens": 100}
        agent._update_token_stats(response)
        assert agent.total_tokens_used == 100

        response2 = AIMessage(content="test2")
        response2.usage_metadata = {"total_tokens": 50}
        agent._update_token_stats(response2)
        assert agent.total_tokens_used == 150

    @patch("agents.base.ChatOpenAI")
    def test_update_token_stats_no_metadata(self, mock_llm_cls):
        """测试无 metadata 时不更新统计"""
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        agent = ReviewAgent()

        response = AIMessage(content="test")
        response.usage_metadata = None
        agent._update_token_stats(response)
        assert agent.total_tokens_used == 0