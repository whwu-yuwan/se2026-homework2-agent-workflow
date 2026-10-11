"""
端到端工作流测试
测试完整的代码审查工作流
"""

import pytest
from unittest.mock import patch, MagicMock

from workflow.context import WorkflowContext
from workflows.code_review import _parse_review_conclusion, _extract_agent_request, build_code_review_workflow
from workflows.doc_generation import build_doc_generation_workflow


class TestReviewConclusionParser:
    """测试审查结论解析"""

    def test_pass_conclusion(self):
        """测试 PASS 结论"""
        report = "## 审查报告\n\n代码质量良好。\n\n### 结论\n\nPASS"
        assert _parse_review_conclusion(report) is False

    def test_needs_fix_conclusion(self):
        """测试 NEEDS_FIX 结论"""
        report = "## 审查报告\n\n发现问题。\n\n### 结论\n\nNEEDS_FIX"
        assert _parse_review_conclusion(report) is True

    def test_critical_issues_detected(self):
        """测试检测到 critical 问题"""
        report = "## 审查报告\n\n1. [critical] SQL 注入漏洞\n\n### 结论\n\nNEEDS_FIX"
        assert _parse_review_conclusion(report) is True

    def test_no_conclusion_with_critical(self):
        """测试没有结论行但有 critical 问题"""
        report = "## 审查报告\n\n1. [critical] 严重问题"
        assert _parse_review_conclusion(report) is True

    def test_no_conclusion_no_critical(self):
        """测试没有结论行也没有 critical 问题"""
        report = "## 审查报告\n\n1. [warning] 小问题"
        assert _parse_review_conclusion(report) is False

    def test_pass_case_insensitive(self):
        """测试 PASS 大小写不敏感"""
        report = "结论: pass"
        # PASS 需要精确匹配行首
        assert _parse_review_conclusion(report) is False


class TestWorkflowContext:
    """测试工作流上下文在完整流程中的表现"""

    def test_context_data_flow_simulation(self):
        """模拟数据在工作流中的流动"""
        ctx = WorkflowContext({"user_input": "test.py"})

        # Step 1: CodeAgent 输出
        ctx.code = "def divide(a, b):\n    return a / b"
        assert ctx.code is not None

        # Step 2: ReviewAgent 输出
        ctx.review_result = "[critical] 除零风险\n\nNEEDS_FIX"
        ctx.has_critical_issues = True
        assert ctx.has_critical_issues is True

        # Step 3: FixAgent 输出
        ctx.code = "def divide(a, b):\n    if b == 0:\n        raise ValueError\n    return a / b"
        ctx.review_round = 1

        # Step 4: 再次审查
        ctx.review_result = "PASS"
        ctx.has_critical_issues = False
        ctx.review_round = 2

        assert ctx.has_critical_issues is False
        assert ctx.review_round == 2
        assert "ValueError" in ctx.code

    def test_context_status_lifecycle(self):
        """测试上下文状态生命周期"""
        ctx = WorkflowContext()
        assert ctx.status == "pending"

        ctx.status = "running"
        assert ctx.status == "running"

        ctx.status = "completed"
        assert ctx.status == "completed"


class TestWorkflowBuild:
    """测试工作流构建"""

    @patch("agents.base.ChatOpenAI")
    def test_build_workflow_returns_engine(self, mock_llm):
        """测试构建工作流返回引擎"""
        engine = build_code_review_workflow(verbose=False)
        assert engine is not None
        assert engine.name == "代码审查工作流"

    @patch("agents.base.ChatOpenAI")
    def test_build_workflow_has_steps_and_loops(self, mock_llm):
        """测试工作流包含步骤和循环"""
        engine = build_code_review_workflow(verbose=False)
        # 应该有 1 个步骤（读取代码）和 1 个循环组（审查-修复）
        assert len(engine._steps) == 1
        assert len(engine._loop_groups) == 1


class TestEndToEndWorkflow:
    """端到端工作流集成测试（Mock Agent）"""

    def _make_mock_agent(self, name, responses):
        from unittest.mock import MagicMock
        agent = MagicMock()
        agent.name = name
        agent._responses = list(responses)
        agent._call_count = 0

        def side_effect(user_input):
            if agent._call_count < len(agent._responses):
                resp = agent._responses[agent._call_count]
            else:
                resp = agent._responses[-1]
            agent._call_count += 1
            return resp

        agent.run = side_effect
        return agent

    def test_pass_first_round(self):
        """测试第一轮审查就通过（无需修复）"""
        from unittest.mock import MagicMock

        mock_registry = MagicMock()
        mock_registry.create.side_effect = [
            self._make_mock_agent("CodeAgent", ["def hello(): pass"]),
            self._make_mock_agent("ReviewAgent", ["代码良好\n\nPASS"]),
            self._make_mock_agent("FixAgent", ["should not run"]),
        ]

        with patch("workflows.code_review.default_registry", mock_registry):
            ctx = WorkflowContext({"user_input": "test.py"})
            engine = build_code_review_workflow(verbose=False)
            ctx = engine.run(ctx)

        assert ctx.status == "completed"
        assert ctx.code == "def hello(): pass"
        assert ctx.has_critical_issues is False

    def test_fix_then_pass(self):
        """测试第一轮有问题，修复后通过"""
        from unittest.mock import MagicMock

        mock_registry = MagicMock()
        mock_registry.create.side_effect = [
            self._make_mock_agent("CodeAgent", ["def div(a,b): return a/b"]),
            self._make_mock_agent("ReviewAgent", [
                "发现除零风险\n\nNEEDS_FIX",
                "修复后代码良好\n\nPASS",
            ]),
            self._make_mock_agent("FixAgent", [
                "def div(a,b):\n    if b==0: raise ValueError\n    return a/b"
            ]),
        ]

        with patch("workflows.code_review.default_registry", mock_registry):
            ctx = WorkflowContext({"user_input": "test.py"})
            engine = build_code_review_workflow(verbose=False)
            ctx = engine.run(ctx)

        assert ctx.status == "completed"
        assert "ValueError" in ctx.code
        assert ctx.review_round == 2

    def test_max_rounds_reached(self):
        """测试达到最大循环轮次"""
        import config as cfg
        from unittest.mock import MagicMock

        mock_registry = MagicMock()
        mock_registry.create.side_effect = [
            self._make_mock_agent("CodeAgent", ["buggy code"]),
            self._make_mock_agent("ReviewAgent", [
                "问题1\n\nNEEDS_FIX",
                "问题2\n\nNEEDS_FIX",
                "问题3\n\nNEEDS_FIX",
            ]),
            self._make_mock_agent("FixAgent", ["fix1", "fix2", "fix3"]),
        ]

        with patch("workflows.code_review.default_registry", mock_registry):
            ctx = WorkflowContext({"user_input": "test.py"})
            engine = build_code_review_workflow(verbose=False)
            ctx = engine.run(ctx)

        assert ctx.status == "completed"
        assert ctx.review_round == cfg.MAX_REVIEW_ROUNDS


class TestDocGenerationWorkflow:
    """测试文档生成工作流"""

    @patch("agents.base.ChatOpenAI")
    def test_build_doc_workflow(self, mock_llm):
        """测试构建文档生成工作流"""
        engine = build_doc_generation_workflow(verbose=False)
        assert engine is not None
        assert engine.name == "文档生成工作流"
        assert len(engine._steps) == 3
        assert len(engine._loop_groups) == 0

    @patch("workflows.doc_generation.default_registry")
    def test_doc_workflow_steps(self, mock_registry):
        """测试文档生成工作流步骤编排"""
        from unittest.mock import MagicMock

        # CodeAgent: 发现文件 + 并行分析
        mock_code_agent = MagicMock()
        mock_code_agent.name = "CodeAgent"
        mock_code_agent.run = MagicMock(side_effect=[
            "test.py\nutils.py",          # 发现文件
            "模块分析: test.py 和 utils.py",  # 并行分析
        ])

        # FixAgent: 生成文档
        mock_fix_agent = MagicMock()
        mock_fix_agent.name = "FixAgent"
        mock_fix_agent.run = MagicMock(return_value="# README\nDocumentation")

        mock_registry.create.side_effect = [mock_code_agent, mock_fix_agent]

        ctx = WorkflowContext({"user_input": "test.py"})
        engine = build_doc_generation_workflow(verbose=False)
        ctx = engine.run(ctx)

        assert ctx.status == "completed"
        assert ctx.get("file_list") == ["test.py", "utils.py"]
        assert ctx.get("analysis") is not None
        assert ctx.get("documentation") == "# README\nDocumentation"


class TestAgentRequestExtraction:
    """测试 Agent 间追问请求提取"""

    def test_extract_request(self):
        """测试从 Agent 输出中提取请求"""
        ctx = WorkflowContext()
        output = "发现问题\n[REQUEST:CodeAgent] 请读取 utils.py 的 import 依赖"
        _extract_agent_request(ctx, output, "ReviewAgent")

        request = ctx.get("_agent_request")
        assert request is not None
        assert request["to"] == "CodeAgent"
        assert "请读取 utils.py" in request["message"]
        assert request["from"] == "ReviewAgent"

    def test_no_request_in_output(self):
        """测试输出中没有请求"""
        ctx = WorkflowContext()
        output = "代码质量良好\nPASS"
        _extract_agent_request(ctx, output, "ReviewAgent")
        assert ctx.get("_agent_request") is None

    def test_request_history(self):
        """测试追问历史记录"""
        ctx = WorkflowContext()
        _extract_agent_request(ctx, "[REQUEST:CodeAgent] 读取 a.py", "ReviewAgent")
        ctx.set("_agent_request", None)  # 模拟已处理
        _extract_agent_request(ctx, "[REQUEST:CodeAgent] 读取 b.py", "ReviewAgent")

        history = ctx.get("agent_request_history")
        assert len(history) == 2
        assert history[0]["request"] == "读取 a.py"