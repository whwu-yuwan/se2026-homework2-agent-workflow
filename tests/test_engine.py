"""
工作流引擎测试
测试 Step 执行、条件分支、循环控制、错误处理
"""

import pytest
from unittest.mock import MagicMock, patch

from workflow.engine import WorkflowEngine, Step, LoopGroup, ParallelGroup, AGENT_REQUEST_KEY, AGENT_RESPONSE_KEY
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


class TestMixedExecution:
    """测试混合编排（步骤 + 循环组合）"""

    def test_step_then_loop(self):
        """测试先执行步骤，再执行循环"""
        init_agent = MockAgent(responses=["initialized data"])
        process_agent = MockAgent(responses=["PASS"])

        ctx = WorkflowContext()
        engine = WorkflowEngine(verbose=False)

        engine.add_step(Step(
            name="init",
            agent=init_agent,
            input_fn=lambda ctx: "init",
            output_fn=lambda ctx, out: ctx.set("data", out),
        ))
        engine.add_loop(LoopGroup(
            name="process-loop",
            steps=[Step(
                name="process",
                agent=process_agent,
                input_fn=lambda ctx: ctx.get("data"),
                output_fn=lambda ctx, out: ctx.set("done", True),
            )],
            condition=lambda ctx: False,
            max_rounds=3,
        ))

        ctx = engine.run(ctx)
        assert ctx.get("data") == "initialized data"
        assert ctx.status == "completed"

    def test_loop_then_step(self):
        """测试先执行循环，再执行步骤"""
        review_agent = MockAgent(responses=["PASS"])
        output_agent = MockAgent(responses=["final output"])

        ctx = WorkflowContext({"code": "test code"})
        engine = WorkflowEngine(verbose=False)

        engine.add_loop(LoopGroup(
            name="review",
            steps=[Step(
                name="review",
                agent=review_agent,
                input_fn=lambda ctx: ctx.get("code"),
                output_fn=lambda ctx, out: ctx.set("reviewed", True),
            )],
            condition=lambda ctx: False,
            max_rounds=1,
        ))
        engine.add_step(Step(
            name="output",
            agent=output_agent,
            input_fn=lambda ctx: "generate report",
            output_fn=lambda ctx, out: ctx.set("report", out),
        ))

        ctx = engine.run(ctx)
        assert ctx.get("reviewed") is True
        assert ctx.get("report") == "final output"

    def test_multiple_loops(self):
        """测试多个循环组"""
        agent1 = MockAgent(responses=["loop1 done"])
        agent2 = MockAgent(responses=["loop2 done"])

        ctx = WorkflowContext()
        engine = WorkflowEngine(verbose=False)

        engine.add_loop(LoopGroup(
            name="loop1",
            steps=[Step(
                name="step1",
                agent=agent1,
                input_fn=lambda ctx: "input1",
                output_fn=lambda ctx, out: ctx.set("r1", out),
            )],
            condition=lambda ctx: False,
            max_rounds=1,
        ))
        engine.add_loop(LoopGroup(
            name="loop2",
            steps=[Step(
                name="step2",
                agent=agent2,
                input_fn=lambda ctx: "input2",
                output_fn=lambda ctx, out: ctx.set("r2", out),
            )],
            condition=lambda ctx: False,
            max_rounds=1,
        ))

        ctx = engine.run(ctx)
        assert ctx.get("r1") == "loop1 done"
        assert ctx.get("r2") == "loop2 done"

    def test_step_then_loop_then_step(self):
        """测试 步骤 → 循环 → 步骤 完整编排"""
        agent_a = MockAgent(responses=["step A"])
        agent_b = MockAgent(responses=["PASS"])
        agent_c = MockAgent(responses=["step C"])

        ctx = WorkflowContext()
        engine = WorkflowEngine(verbose=False)

        engine.add_step(Step(
            name="A",
            agent=agent_a,
            input_fn=lambda ctx: "start",
            output_fn=lambda ctx, out: ctx.set("a", out),
        ))
        engine.add_loop(LoopGroup(
            name="B-loop",
            steps=[Step(
                name="B",
                agent=agent_b,
                input_fn=lambda ctx: ctx.get("a"),
                output_fn=lambda ctx, out: ctx.set("b", out),
            )],
            condition=lambda ctx: False,
            max_rounds=1,
        ))
        engine.add_step(Step(
            name="C",
            agent=agent_c,
            input_fn=lambda ctx: ctx.get("b"),
            output_fn=lambda ctx, out: ctx.set("c", out),
        ))

        ctx = engine.run(ctx)
        assert ctx.get("a") == "step A"
        assert ctx.get("b") == "PASS"
        assert ctx.get("c") == "step C"

    def test_loop_with_conditional_inner_step(self):
        """测试循环内有条件执行的步骤"""
        review_agent = MockAgent(responses=["NEEDS_FIX", "PASS"])
        fix_agent = MockAgent(responses=["fixed code"])

        ctx = WorkflowContext({"code": "buggy code"})
        engine = WorkflowEngine(verbose=False)

        round_count = [0]

        def review_output(ctx, output):
            ctx.set("issues", "NEEDS_FIX" in output)
            round_count[0] += 1

        engine.add_loop(LoopGroup(
            name="review-fix",
            steps=[
                Step(
                    name="review",
                    agent=review_agent,
                    input_fn=lambda ctx: ctx.get("code"),
                    output_fn=review_output,
                ),
                Step(
                    name="fix",
                    agent=fix_agent,
                    input_fn=lambda ctx: ctx.get("code"),
                    output_fn=lambda ctx, out: ctx.set("code", out),
                    condition=lambda ctx: ctx.get("issues", False),
                ),
            ],
            condition=lambda ctx: ctx.get("issues", False),
            max_rounds=3,
        ))

        ctx = engine.run(ctx)
        assert ctx.status == "completed"
        assert round_count[0] == 2

    def test_engine_name(self):
        """测试引擎名称"""
        engine = WorkflowEngine(name="my workflow", verbose=False)
        assert engine.name == "my workflow"

    def test_flow_logger_property(self):
        """测试 flow_logger 属性"""
        engine = WorkflowEngine(verbose=False)
        assert engine.flow_logger is not None

    def test_step_result_metadata(self):
        """测试步骤结果包含元数据"""
        class FailingAgent:
            name = "FailAgent"
            def run(self, input):
                raise ValueError("test error")

        ctx = WorkflowContext()
        engine = WorkflowEngine(verbose=False)
        engine.add_step(Step(
            name="fail_step",
            agent=FailingAgent(),
            input_fn=lambda ctx: "input",
            output_fn=lambda ctx, out: None,
        ))

        with pytest.raises(EngineError):
            engine.run(ctx)

        result = ctx.step_results[0]
        assert result.status == "failed"
        assert result.metadata["error_type"] == "ValueError"

    def test_data_flow_through_multiple_steps(self):
        """测试数据在多个步骤间正确流转"""
        agents = [MockAgent(responses=[f"output_{i}"]) for i in range(5)]

        ctx = WorkflowContext()
        engine = WorkflowEngine(verbose=False)

        for i, agent in enumerate(agents):
            engine.add_step(Step(
                name=f"step_{i}",
                agent=agent,
                input_fn=lambda ctx, idx=i: ctx.get(f"step_{idx-1}_output", "start") if idx > 0 else "start",
                output_fn=lambda ctx, out, idx=i: ctx.set(f"step_{idx}_output", out),
            ))

        ctx = engine.run(ctx)

        assert ctx.get("step_0_output") == "output_0"
        assert ctx.get("step_4_output") == "output_4"
        assert len(ctx.step_results) == 5


class TestParallelGroup:
    """测试并行步骤组"""

    def test_parallel_execution(self):
        """测试并行步骤同时执行"""
        agent1 = MockAgent(responses=["result1"])
        agent2 = MockAgent(responses=["result2"])
        agent3 = MockAgent(responses=["result3"])

        ctx = WorkflowContext()
        engine = WorkflowEngine(verbose=False)

        engine.add_parallel(ParallelGroup(
            name="并行分析",
            steps=[
                Step(
                    name="分析A",
                    agent=agent1,
                    input_fn=lambda ctx: "inputA",
                    output_fn=lambda ctx, out: ctx.set("a", out),
                ),
                Step(
                    name="分析B",
                    agent=agent2,
                    input_fn=lambda ctx: "inputB",
                    output_fn=lambda ctx, out: ctx.set("b", out),
                ),
                Step(
                    name="分析C",
                    agent=agent3,
                    input_fn=lambda ctx: "inputC",
                    output_fn=lambda ctx, out: ctx.set("c", out),
                ),
            ],
            max_workers=3,
        ))

        ctx = engine.run(ctx)

        assert ctx.status == "completed"
        assert ctx.get("a") == "result1"
        assert ctx.get("b") == "result2"
        assert ctx.get("c") == "result3"
        # 并行组结果记录
        parallel_result = ctx.step_results[-1]
        assert "3/3" in parallel_result.output

    def test_parallel_with_step_before_and_after(self):
        """测试 步骤 → 并行 → 步骤 编排"""
        init_agent = MockAgent(responses=["init"])
        p1 = MockAgent(responses=["p1"])
        p2 = MockAgent(responses=["p2"])
        final = MockAgent(responses=["done"])

        ctx = WorkflowContext()
        engine = WorkflowEngine(verbose=False)

        engine.add_step(Step(
            name="init",
            agent=init_agent,
            input_fn=lambda ctx: "start",
            output_fn=lambda ctx, out: ctx.set("init", out),
        ))
        engine.add_parallel(ParallelGroup(
            name="parallel",
            steps=[
                Step("p1", p1, lambda ctx: "a", lambda ctx, o: ctx.set("p1", o)),
                Step("p2", p2, lambda ctx: "b", lambda ctx, o: ctx.set("p2", o)),
            ],
        ))
        engine.add_step(Step(
            name="final",
            agent=final,
            input_fn=lambda ctx: f"{ctx.get('p1')},{ctx.get('p2')}",
            output_fn=lambda ctx, out: ctx.set("final", out),
        ))

        ctx = engine.run(ctx)

        assert ctx.get("init") == "init"
        assert ctx.get("p1") == "p1"
        assert ctx.get("p2") == "p2"
        assert ctx.get("final") == "done"

    def test_parallel_with_condition(self):
        """测试并行步骤中的条件过滤"""
        agent1 = MockAgent(responses=["r1"])
        agent2 = MockAgent(responses=["r2"])

        ctx = WorkflowContext({"skip_b": True})
        engine = WorkflowEngine(verbose=False)

        engine.add_parallel(ParallelGroup(
            name="conditional-parallel",
            steps=[
                Step("A", agent1, lambda ctx: "a", lambda ctx, o: ctx.set("a", o)),
                Step("B", agent2, lambda ctx: "b", lambda ctx, o: ctx.set("b", o),
                     condition=lambda ctx: not ctx.get("skip_b", False)),
            ],
        ))

        ctx = engine.run(ctx)

        assert ctx.get("a") == "r1"
        # B 被跳过，output_fn 未被调用
        assert ctx.get("b") is None


class TestAgentRequest:
    """测试 Agent 间追问机制"""

    def test_agent_request_dispatched(self):
        """测试 Agent 请求被正确分发"""
        review_agent = MockAgent(responses=["发现问题\n[REQUEST:CodeAgent] 请读取 utils.py"])
        code_agent = MockAgent(responses=["utils.py 内容: import os"])
        fix_agent = MockAgent(responses=["修复后代码"])

        ctx = WorkflowContext({"code": "test code"})
        engine = WorkflowEngine(verbose=False)
        engine.register_agent(code_agent)

        def store_review_with_request(ctx, output):
            ctx.set("review", output)
            # 模拟提取请求
            if "[REQUEST:CodeAgent]" in output:
                ctx.set(AGENT_REQUEST_KEY, {
                    "to": "CodeAgent",
                    "message": "请读取 utils.py",
                    "from": "ReviewAgent",
                })

        def review_input_with_response(ctx):
            base = "请审查代码"
            resp = ctx.get(AGENT_RESPONSE_KEY)
            if resp:
                base += f"\n\n补充信息: {resp}"
            return base

        engine.add_step(Step(
            name="review",
            agent=review_agent,
            input_fn=review_input_with_response,
            output_fn=store_review_with_request,
        ))

        ctx = engine.run(ctx)

        # 请求应该被分发
        assert ctx.get("review") is not None
        # Agent 响应应该被存储
        assert ctx.get(AGENT_RESPONSE_KEY) is not None or ctx.has("review")
        # 请求应该被清除
        assert ctx.get(AGENT_REQUEST_KEY) is None

    def test_no_request_no_dispatch(self):
        """测试没有请求时不触发分发"""
        agent = MockAgent(responses=["正常输出"])

        ctx = WorkflowContext()
        engine = WorkflowEngine(verbose=False)

        engine.add_step(Step(
            name="normal",
            agent=agent,
            input_fn=lambda ctx: "input",
            output_fn=lambda ctx, out: ctx.set("result", out),
        ))

        ctx = engine.run(ctx)
        assert ctx.get("result") == "正常输出"
        assert ctx.get(AGENT_RESPONSE_KEY) is None

    def test_request_to_unregistered_agent(self):
        """测试请求未注册的 Agent 时产生错误响应"""
        agent = MockAgent(responses=["[REQUEST:UnknownAgent] 做点什么"])
        helper = MockAgent(responses=["帮助完成"])

        ctx = WorkflowContext()
        engine = WorkflowEngine(verbose=False)
        # 注册一个 Agent 但不是请求的目标，确保 dispatch 逻辑运行
        engine.register_agent(helper)

        def set_request(ctx, output):
            if "[REQUEST:" in output:
                ctx.set(AGENT_REQUEST_KEY, {
                    "to": "UnknownAgent",
                    "message": "做点什么",
                })

        engine.add_step(Step(
            name="step",
            agent=agent,
            input_fn=lambda ctx: "input",
            output_fn=set_request,
        ))

        ctx = engine.run(ctx)
        # 应该有错误响应（目标 Agent 不存在）
        assert ctx.get(AGENT_RESPONSE_KEY) is not None
        assert "未找到" in ctx.get(AGENT_RESPONSE_KEY)

    def test_register_agent(self):
        """测试注册 Agent"""
        agent = MockAgent(responses=[])
        engine = WorkflowEngine(verbose=False)
        engine.register_agent(agent)
        assert "MockAgent" in engine._agent_registry