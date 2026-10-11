"""
端到端工作流测试
测试完整的代码审查工作流
"""

import pytest
from unittest.mock import patch, MagicMock

from workflow.context import WorkflowContext
from workflows.code_review import _parse_review_conclusion, build_code_review_workflow


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