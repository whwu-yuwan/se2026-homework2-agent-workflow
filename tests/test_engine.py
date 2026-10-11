"""
工作流引擎测试
测试 Step 执行、条件分支、循环控制、错误处理
"""

import pytest
from unittest.mock import MagicMock, patch

from workflow.engine import WorkflowEngine, Step, LoopGroup
from workflow.context import WorkflowContext, StepResult
from exceptions import StepError, EngineError


class MockAgent:
    """模拟 Agent，不实际调用 LLM"""

    def __init__(self, name="MockAgent", responses=None):
        self.name = name
        self._responses = responses or ["mock response"]
        self._call_count = 0

    def run(self, user_input: str) -> str:
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
        else:
            resp = self._responses[-1]
        self._call_count += 1
        return resp

    def reset(self):
        self._call_count = 0


class TestStep:
    """测试单步执行"""

    def test_step_basic_execution(self):
        """测试基本步骤执行"""
        agent = MockAgent(responses=["hello"])
        ctx = WorkflowContext({"input": "test"})

        engine = WorkflowEngine(verbose=False)
        engine.add_step(Step(
            name="test_step",
            agent=agent,
            input_fn=lambda ctx: ctx.get("input"),
            output_fn=lambda ctx, out: ctx.set("result", out),
        ))

        ctx = engine.run(ctx)

        assert ctx.status == "completed"
        assert ctx.get("result") == "hello"
        assert len(ctx.step_results) == 1
        assert ctx.step_results[0].status == "success"

    def test_step_with_condition_true(self):
        """测试条件为 True 时执行步骤"""
        agent = MockAgent(responses=["executed"])
        ctx = WorkflowContext()

        engine = WorkflowEngine(verbose=False)
        engine.add_step(Step(
            name="conditional_step",
            agent=agent,
            input_fn=lambda ctx: "input",
            output_fn=lambda ctx, out: ctx.set("result", out),
            condition=lambda ctx: True,
        ))

        ctx = engine.run(ctx)
        assert ctx.get("result") == "executed"

    def test_step_with_condition_false(self):
        """测试条件为 False 时跳过步骤"""
        agent = MockAgent(responses=["should not run"])
        ctx = WorkflowContext()

        engine = WorkflowEngine(verbose=False)
        engine.add_step(Step(
            name="skipped_step",
            agent=agent,
            input_fn=lambda ctx: "input",
            output_fn=lambda ctx, out: ctx.set("result", out),
            condition=lambda ctx: False,
        ))

        ctx = engine.run(ctx)
        assert ctx.get("result") is None
        assert ctx.step_results[0].status == "skipped"

    def test_step_failure_raises_error(self):
        """测试步骤失败时抛出错误"""
        class FailingAgent:
            name = "FailingAgent"
            def run(self, input):
                raise RuntimeError("agent failed")

        ctx = WorkflowContext()
        engine = WorkflowEngine(verbose=False)
        engine.add_step(Step(
            name="failing_step",
            agent=FailingAgent(),
            input_fn=lambda ctx: "input",
            output_fn=lambda ctx, out: ctx.set("result", out),
        ))

        with pytest.raises(EngineError):
            engine.run(ctx)

        assert ctx.status == "failed"


class TestLoopGroup:
    """测试循环组"""

    def test_loop_stops_on_condition(self):
        """测试循环在条件满足时停止"""
        # ReviewAgent 前两次返回 NEEDS_FIX，第三次返回 PASS
        review_agent = MockAgent(responses=[
            "NEEDS_FIX: found bugs",
            "NEEDS_FIX: still bugs",
            "PASS: all good",
        ])
        fix_agent = MockAgent(responses=["fixed code v1", "fixed code v2", "fixed code v3"])

        def parse_conclusion(output):
            return "NEEDS_FIX" in output

        ctx = WorkflowContext({"code": "original code"})

        engine = WorkflowEngine(verbose=False)
        engine.add_loop(LoopGroup(
            name="review-fix",
            steps=[
                Step(
                    name="review",
                    agent=review_agent,
                    input_fn=lambda ctx: ctx.get("code"),
                    output_fn=lambda ctx, out: (
                        ctx.set("review_result", out),
                        ctx.set("has_issues", parse_conclusion(out)),
                    ),
                ),
                Step(
                    name="fix",
                    agent=fix_agent,
                    input_fn=lambda ctx: ctx.get("code"),
                    output_fn=lambda ctx, out: ctx.set("code", out),
                    condition=lambda ctx: ctx.get("has_issues", False),
                ),
            ],
            condition=lambda ctx: ctx.get("has_issues", False),
            max_rounds=3,
        ))

        ctx = engine.run(ctx)

        assert ctx.status == "completed"
        assert ctx.get("review_result") == "PASS: all good"
        assert ctx.review_round == 3

    def test_loop_max_rounds(self):
        """测试循环达到最大轮次"""
        review_agent = MockAgent(responses=[
            "NEEDS_FIX: bugs",
            "NEEDS_FIX: bugs",
            "NEEDS_FIX: bugs",
        ])

        ctx = WorkflowContext({"code": "code"})

        engine = WorkflowEngine(verbose=False)
        engine.add_loop(LoopGroup(
            name="infinite-loop",
            steps=[
                Step(
                    name="review",
                    agent=review_agent,
                    input_fn=lambda ctx: ctx.get("code"),
                    output_fn=lambda ctx, out: ctx.set("has_issues", True),
                ),
            ],
            condition=lambda ctx: ctx.get("has_issues", False),
            max_rounds=3,
        ))

        ctx = engine.run(ctx)
        assert ctx.status == "completed"
        assert ctx.review_round == 3

    def test_loop_skips_fix_when_pass(self):
        """测试审查通过时跳过修复步骤"""
        review_agent = MockAgent(responses=["PASS: no issues"])
        fix_agent = MockAgent(responses=["should not run"])

        ctx = WorkflowContext({"code": "good code"})

        engine = WorkflowEngine(verbose=False)
        engine.add_loop(LoopGroup(
            name="review-fix",
            steps=[
                Step(
                    name="review",
                    agent=review_agent,
                    input_fn=lambda ctx: ctx.get("code"),
                    output_fn=lambda ctx, out: ctx.set("has_issues", "NEEDS_FIX" in out),
                ),
                Step(
                    name="fix",
                    agent=fix_agent,
                    input_fn=lambda ctx: ctx.get("code"),
                    output_fn=lambda ctx, out: ctx.set("code", out),
                    condition=lambda ctx: ctx.get("has_issues", False),
                ),
            ],
            condition=lambda ctx: ctx.get("has_issues", False),
            max_rounds=3,
        ))

        ctx = engine.run(ctx)

        assert ctx.status == "completed"
        assert ctx.get("code") == "good code"  # 未被修改


class TestWorkflowEngine:
    """测试引擎组合"""

    def test_sequential_steps(self):
        """测试顺序执行多个步骤"""
        agent1 = MockAgent(responses=["step1 output"])
        agent2 = MockAgent(responses=["step2 output"])

        ctx = WorkflowContext()
        engine = WorkflowEngine(verbose=False)

        engine.add_step(Step(
            name="step1",
            agent=agent1,
            input_fn=lambda ctx: "input1",
            output_fn=lambda ctx, out: ctx.set("s1", out),
        ))
        engine.add_step(Step(
            name="step2",
            agent=agent2,
            input_fn=lambda ctx: ctx.get("s1"),
            output_fn=lambda ctx, out: ctx.set("s2", out),
        ))

        ctx = engine.run(ctx)

        assert ctx.get("s1") == "step1 output"
        assert ctx.get("s2") == "step2 output"
        assert len(ctx.step_results) == 2

    def test_context_data_flow(self):
        """测试数据在步骤间正确流动"""
        # Step1: 读取 → Step2: 处理 → Step3: 输出
        agent1 = MockAgent(responses=["raw data"])
        agent2 = MockAgent(responses=["processed data"])
        agent3 = MockAgent(responses=["final output"])

        ctx = WorkflowContext({"source": "test.txt"})
        engine = WorkflowEngine(verbose=False)

        engine.add_step(Step(
            name="read",
            agent=agent1,
            input_fn=lambda ctx: ctx.get("source"),
            output_fn=lambda ctx, out: ctx.set("raw", out),
        ))
        engine.add_step(Step(
            name="process",
            agent=agent2,
            input_fn=lambda ctx: ctx.get("raw"),
            output_fn=lambda ctx, out: ctx.set("processed", out),
        ))
        engine.add_step(Step(
            name="output",
            agent=agent3,
            input_fn=lambda ctx: ctx.get("processed"),
            output_fn=lambda ctx, out: ctx.set("final", out),
        ))

        ctx = engine.run(ctx)

        assert ctx.get("raw") == "raw data"
        assert ctx.get("processed") == "processed data"
        assert ctx.get("final") == "final output"


class TestWorkflowContext:
    """测试工作流上下文"""

    def test_basic_get_set(self):
        ctx = WorkflowContext()
        ctx.set("key", "value")
        assert ctx.get("key") == "value"
        assert ctx.get("missing") is None
        assert ctx.get("missing", "default") == "default"

    def test_has(self):
        ctx = WorkflowContext()
        assert not ctx.has("key")
        ctx.set("key", "value")
        assert ctx.has("key")

    def test_update(self):
        ctx = WorkflowContext()
        ctx.update({"a": 1, "b": 2})
        assert ctx.get("a") == 1
        assert ctx.get("b") == 2

    def test_initial_data(self):
        ctx = WorkflowContext({"x": 10})
        assert ctx.get("x") == 10

    def test_step_results(self):
        ctx = WorkflowContext()
        result = StepResult("step1", "agent1", "success", "output", 1.0)
        ctx.add_step_result(result)
        assert len(ctx.step_results) == 1
        assert ctx.last_step.step_name == "step1"

    def test_status(self):
        ctx = WorkflowContext()
        assert ctx.status == "pending"
        ctx.status = "running"
        assert ctx.status == "running"

    def test_code_property(self):
        ctx = WorkflowContext()
        ctx.code = "print('hello')"
        assert ctx.code == "print('hello')"

    def test_review_properties(self):
        ctx = WorkflowContext()
        ctx.review_result = "PASS"
        ctx.review_round = 2
        ctx.has_critical_issues = False
        assert ctx.review_result == "PASS"
        assert ctx.review_round == 2
        assert not ctx.has_critical_issues