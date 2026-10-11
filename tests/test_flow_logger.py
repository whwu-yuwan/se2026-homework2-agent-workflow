"""
执行日志测试
测试 FlowLogger 的日志记录和报告生成功能
"""

import time
import pytest
from io import StringIO
from unittest.mock import patch

from workflow.flow_logger import FlowLogger
from workflow.context import StepResult


class TestFlowLogger:
    """测试 FlowLogger"""

    def test_init_verbose(self):
        """测试初始化（verbose 模式）"""
        fl = FlowLogger(verbose=True)
        assert fl.verbose is True
        assert fl.records == []

    def test_init_quiet(self):
        """测试初始化（quiet 模式）"""
        fl = FlowLogger(verbose=False)
        assert fl.verbose is False

    def test_on_workflow_start_prints(self, capsys):
        """测试工作流开始打印"""
        fl = FlowLogger(verbose=True)
        fl.on_workflow_start("测试工作流")
        captured = capsys.readouterr()
        assert "测试工作流" in captured.out
        assert "开始" in captured.out

    def test_on_workflow_start_quiet(self, capsys):
        """测试 quiet 模式不打印"""
        fl = FlowLogger(verbose=False)
        fl.on_workflow_start("测试工作流")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_on_step_start_prints(self, capsys):
        """测试步骤开始打印"""
        fl = FlowLogger(verbose=True)
        fl.on_step_start("读取代码", "CodeAgent")
        captured = capsys.readouterr()
        assert "读取代码" in captured.out
        assert "CodeAgent" in captured.out

    def test_on_step_end_success(self, capsys):
        """测试步骤成功结束"""
        fl = FlowLogger(verbose=True)
        result = StepResult(
            step_name="测试步骤",
            agent_name="TestAgent",
            status="success",
            output="测试输出内容",
            duration=1.5,
        )
        fl.on_step_end(result)
        captured = capsys.readouterr()
        assert "✅" in captured.out
        assert "1.5s" in captured.out
        assert len(fl.records) == 1

    def test_on_step_end_failed(self, capsys):
        """测试步骤失败结束"""
        fl = FlowLogger(verbose=True)
        result = StepResult(
            step_name="失败步骤",
            agent_name="TestAgent",
            status="failed",
            output="错误信息",
            duration=0.5,
        )
        fl.on_step_end(result)
        captured = capsys.readouterr()
        assert "❌" in captured.out

    def test_on_step_end_skipped(self, capsys):
        """测试步骤跳过"""
        fl = FlowLogger(verbose=True)
        result = StepResult(
            step_name="跳过步骤",
            agent_name="TestAgent",
            status="skipped",
            output="(条件不满足)",
            duration=0.0,
        )
        fl.on_step_end(result)
        captured = capsys.readouterr()
        assert "⏭️" in captured.out

    def test_on_step_end_truncates_long_output(self, capsys):
        """测试长输出被截断"""
        fl = FlowLogger(verbose=True)
        long_output = "x" * 500
        result = StepResult(
            step_name="长输出",
            agent_name="TestAgent",
            status="success",
            output=long_output,
            duration=1.0,
        )
        fl.on_step_end(result)
        captured = capsys.readouterr()
        assert "..." in captured.out

    def test_on_loop_start(self, capsys):
        """测试循环开始打印"""
        fl = FlowLogger(verbose=True)
        fl.on_loop_start(1, 3)
        captured = capsys.readouterr()
        assert "第 1/3 轮" in captured.out

    def test_on_loop_end_passed(self, capsys):
        """测试循环结束（通过）"""
        fl = FlowLogger(verbose=True)
        fl.on_loop_end(2, passed=True)
        captured = capsys.readouterr()
        assert "审查通过" in captured.out

    def test_on_loop_end_continue(self, capsys):
        """测试循环结束（继续）"""
        fl = FlowLogger(verbose=True)
        fl.on_loop_end(1, passed=False)
        captured = capsys.readouterr()
        assert "继续修复" in captured.out

    def test_on_workflow_end_completed(self, capsys):
        """测试工作流完成"""
        fl = FlowLogger(verbose=True)
        fl.on_workflow_end("completed")
        captured = capsys.readouterr()
        assert "completed" in captured.out
        assert "总耗时" in captured.out

    def test_on_workflow_end_failed(self, capsys):
        """测试工作流失败"""
        fl = FlowLogger(verbose=True)
        fl.on_workflow_end("failed")
        captured = capsys.readouterr()
        assert "failed" in captured.out

    def test_get_summary_empty(self):
        """测试空摘要"""
        fl = FlowLogger(verbose=False)
        summary = fl.get_summary()
        assert "步骤数: 0" in summary

    def test_get_summary_with_records(self):
        """测试有记录的摘要"""
        fl = FlowLogger(verbose=False)
        # 模拟记录
        fl._records = [
            {"step": "读取", "agent": "CodeAgent", "status": "success", "duration": 1.0, "output_length": 100, "metadata": {}},
            {"step": "审查", "agent": "ReviewAgent", "status": "success", "duration": 2.0, "output_length": 200, "metadata": {}},
        ]
        summary = fl.get_summary()
        assert "步骤数: 2" in summary
        assert "成功: 2" in summary
        assert "失败: 0" in summary

    def test_records_property(self):
        """测试 records 属性返回副本"""
        fl = FlowLogger(verbose=False)
        result = StepResult("s1", "a1", "success", "out", 1.0)
        fl.on_step_end(result)
        records = fl.records
        assert len(records) == 1
        # 修改副本不影响原数据
        records.clear()
        assert len(fl.records) == 1

    def test_full_workflow_sequence(self, capsys):
        """测试完整的工作流日志序列"""
        fl = FlowLogger(verbose=True)

        fl.on_workflow_start("测试流程")
        fl.on_step_start("步骤1", "Agent1")
        fl.on_step_end(StepResult("步骤1", "Agent1", "success", "输出1", 1.0))
        fl.on_loop_start(1, 2)
        fl.on_step_start("步骤2", "Agent2")
        fl.on_step_end(StepResult("步骤2", "Agent2", "success", "输出2", 2.0))
        fl.on_loop_end(1, passed=False)
        fl.on_loop_start(2, 2)
        fl.on_step_start("步骤2", "Agent2")
        fl.on_step_end(StepResult("步骤2", "Agent2", "success", "输出3", 1.5))
        fl.on_loop_end(2, passed=True)
        fl.on_workflow_end("completed")

        captured = capsys.readouterr()
        assert "开始" in captured.out
        assert "完成" in captured.out
        assert len(fl.records) == 3