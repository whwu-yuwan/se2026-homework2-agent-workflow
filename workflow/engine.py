"""
工作流引擎
支持顺序执行、条件分支、循环控制、并行执行、动态扇出、错误恢复
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Any

from workflow.context import WorkflowContext, StepResult
from workflow.flow_logger import FlowLogger
from agents.base import BaseAgent
from exceptions import EngineError, StepError, WorkflowError

logger = logging.getLogger(__name__)

AGENT_REQUEST_KEY = "_agent_request"
AGENT_RESPONSE_KEY = "_agent_response"


class Step:
    """工作流步骤定义"""

    def __init__(
        self,
        name: str,
        agent: BaseAgent,
        input_fn: Callable[[WorkflowContext], str],
        output_fn: Callable[[WorkflowContext, str], None],
        condition: Optional[Callable[[WorkflowContext], bool]] = None,
    ):
        self.name = name
        self.agent = agent
        self.input_fn = input_fn
        self.output_fn = output_fn
        self.condition = condition


class LoopGroup:
    """循环步骤组：循环执行直到条件满足或达到最大轮次"""

    def __init__(
        self,
        name: str,
        steps: List[Step],
        condition: Callable[[WorkflowContext], bool],
        max_rounds: int = 3,
        reset_agents: bool = True,
    ):
        """
        Args:
            reset_agents: 每轮循环开始前是否重置 Agent 消息历史（防止 token 浪费）
        """
        self.name = name
        self.steps = steps
        self.condition = condition
        self.max_rounds = max_rounds
        self.reset_agents = reset_agents


class ParallelGroup:
    """并行步骤组：构建时确定全部步骤，同时并发执行"""

    def __init__(self, name: str, steps: List[Step], max_workers: int = 4):
        self.name = name
        self.steps = steps
        self.max_workers = max_workers


class MapParallelStep:
    """动态并行步骤：运行时根据上下文数据生成并行任务

    解决 ParallelGroup 必须在构建时确定 steps 的限制。
    运行时通过 items_fn 从上下文获取数据列表，为每个元素生成一个并行任务。

    适用场景：CodeAgent 发现 N 个文件 → N 个并行分析任务（N 运行时才知道）
    """

    def __init__(
        self,
        name: str,
        agent: BaseAgent,
        items_fn: Callable[[WorkflowContext], List[Any]],
        make_input_fn: Callable[[Any, WorkflowContext], str],
        make_output_fn: Callable[[Any, WorkflowContext, str], None],
        max_workers: int = 4,
    ):
        """
        Args:
            name: 步骤名称
            agent: 执行并行任务的 Agent
            items_fn: 从上下文获取待处理元素列表
            make_input_fn: (item, ctx) → 该元素的 Agent 输入
            make_output_fn: (item, ctx, output) → 将该元素的输出写入上下文
            max_workers: 最大并发数
        """
        self.name = name
        self.agent = agent
        self.items_fn = items_fn
        self.make_input_fn = make_input_fn
        self.make_output_fn = make_output_fn
        self.max_workers = max_workers


class WorkflowEngine:
    """工作流引擎

    功能：
    - 顺序执行步骤（Step）
    - 条件分支（Step.condition）
    - 循环控制（LoopGroup，支持每轮 reset Agent）
    - 静态并行（ParallelGroup，构建时确定步骤）
    - 动态并行（MapParallelStep，运行时根据数据生成任务）
    - 错误恢复（fail_fast 可配置，False 时记录错误继续执行）
    - Agent 间追问（_agent_request/_agent_response 机制）
    """

    def __init__(self, name: str = "workflow", verbose: bool = True, fail_fast: bool = True):
        """
        Args:
            fail_fast: True=单步失败立即中断; False=记录错误继续执行（错误恢复）
        """
        self.name = name
        self._steps: List[Step] = []
        self._loop_groups: List[LoopGroup] = []
        self._parallel_groups: List[ParallelGroup] = []
        self._map_steps: List[MapParallelStep] = []
        self._execution_order: List[str] = []
        self._flow_logger = FlowLogger(verbose=verbose)
        self._fail_fast = fail_fast
        self._agent_registry: Dict[str, BaseAgent] = {}

    def register_agent(self, agent: BaseAgent) -> "WorkflowEngine":
        """注册 Agent 用于 Agent 间请求路由"""
        self._agent_registry[agent.name] = agent
        return self

    def add_step(self, step: Step) -> "WorkflowEngine":
        self._steps.append(step)
        self._execution_order.append(f"step:{step.name}")
        return self

    def add_loop(self, loop: LoopGroup) -> "WorkflowEngine":
        self._loop_groups.append(loop)
        self._execution_order.append(f"loop:{loop.name}")
        return self

    def add_parallel(self, parallel: ParallelGroup) -> "WorkflowEngine":
        self._parallel_groups.append(parallel)
        self._execution_order.append(f"parallel:{parallel.name}")
        return self

    def add_map_parallel(self, map_step: MapParallelStep) -> "WorkflowEngine":
        """添加动态并行步骤"""
        self._map_steps.append(map_step)
        self._execution_order.append(f"map:{map_step.name}")
        return self

    # ─── 步骤执行 ──────────────────────────────────────────────

    def _run_step(self, step: Step, ctx: WorkflowContext) -> StepResult:
        """执行单个步骤"""
        if step.condition and not step.condition(ctx):
            result = StepResult(
                step_name=step.name, agent_name=step.agent.name,
                status="skipped", output="(条件不满足，跳过)", duration=0.0,
            )
            self._flow_logger.on_step_end(result)
            ctx.add_step_result(result)
            return result

        self._flow_logger.on_step_start(step.name, step.agent.name)
        start_time = time.time()

        try:
            user_input = step.input_fn(ctx)
            output = step.agent.run(user_input)
            step.output_fn(ctx, output)
            duration = time.time() - start_time
            result = StepResult(
                step_name=step.name, agent_name=step.agent.name,
                status="success", output=output, duration=duration,
            )
        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"步骤 '{step.name}' 执行失败: {error_msg}")
            result = StepResult(
                step_name=step.name, agent_name=step.agent.name,
                status="failed", output=error_msg, duration=duration,
                metadata={"error": str(e), "error_type": type(e).__name__},
            )

        self._flow_logger.on_step_end(result)
        ctx.add_step_result(result)

        if result.status == "failed" and self._fail_fast:
            raise StepError(step.name, result.output)

        if self._agent_registry:
            self._check_and_dispatch_request(ctx, self._agent_registry)

        return result

    # ─── Agent 间请求路由 ──────────────────────────────────────

    def _check_and_dispatch_request(self, ctx: WorkflowContext, agents: Dict[str, BaseAgent]) -> None:
        """检查并分发 Agent 间请求"""
        if not ctx.has(AGENT_REQUEST_KEY):
            return

        request = ctx.get(AGENT_REQUEST_KEY)
        if not request:
            return

        target_name = request.get("to", "")
        message = request.get("message", "")

        if not target_name or not message:
            ctx.set(AGENT_REQUEST_KEY, None)
            return

        target_agent = agents.get(target_name)
        if not target_agent:
            logger.warning(f"Agent 请求目标不存在: {target_name}")
            ctx.set(AGENT_RESPONSE_KEY, f"[错误] 未找到 Agent: {target_name}")
            ctx.set(AGENT_REQUEST_KEY, None)
            return

        self._flow_logger.on_step_start(f"Agent请求→{target_name}", target_name)
        start_time = time.time()

        try:
            response = target_agent.run(message)
            ctx.set(AGENT_RESPONSE_KEY, response)
            result = StepResult(
                step_name=f"Agent请求→{target_name}", agent_name=target_name,
                status="success", output=response, duration=time.time() - start_time,
                metadata={"request_from": request.get("from", "unknown")},
            )
        except Exception as e:
            ctx.set(AGENT_RESPONSE_KEY, f"[错误] {e}")
            result = StepResult(
                step_name=f"Agent请求→{target_name}", agent_name=target_name,
                status="failed", output=str(e), duration=time.time() - start_time,
            )

        self._flow_logger.on_step_end(result)
        ctx.add_step_result(result)
        ctx.set(AGENT_REQUEST_KEY, None)

    # ─── 循环执行 ──────────────────────────────────────────────

    def _run_loop(self, loop: LoopGroup, ctx: WorkflowContext) -> None:
        """执行循环组，每轮开始前可选 reset Agent"""
        for round_num in range(1, loop.max_rounds + 1):
            # 通用轮次计数器（唯一，不写业务字段）
            ctx.set(f"{loop.name}_round", round_num)

            # 每轮 reset Agent 消息历史，防止 token 浪费
            if loop.reset_agents and round_num > 1:
                for step in loop.steps:
                    step.agent.reset()

            self._flow_logger.on_loop_start(round_num, loop.max_rounds)

            for step in loop.steps:
                self._run_step(step, ctx)

            should_continue = loop.condition(ctx)
            self._flow_logger.on_loop_end(round_num, not should_continue)

            if not should_continue:
                break
        else:
            logger.warning(f"循环 '{loop.name}' 达到最大轮次 {loop.max_rounds}")

    # ─── 静态并行 ──────────────────────────────────────────────

    def _run_parallel(self, parallel: ParallelGroup, ctx: WorkflowContext) -> None:
        """并行执行一组步骤（构建时确定）"""
        self._flow_logger.on_step_start(parallel.name, f"并行({len(parallel.steps)}个)")
        start_time = time.time()
        results = self._execute_parallel_steps(parallel.steps, ctx, parallel.max_workers)

        duration = time.time() - start_time
        success_count = sum(1 for r in results.values() if r.status == "success")
        group_result = StepResult(
            step_name=parallel.name, agent_name=f"并行组({len(parallel.steps)})",
            status="success" if success_count == len(results) else "failed",
            output=f"{success_count}/{len(results)} 成功", duration=duration,
        )
        self._flow_logger.on_step_end(group_result)
        ctx.add_step_result(group_result)

    # ─── 动态并行（map_parallel）──────────────────────────────

    def _run_map_parallel(self, map_step: MapParallelStep, ctx: WorkflowContext) -> None:
        """动态并行：运行时从上下文获取元素列表，为每个元素生成并行任务"""
        items = map_step.items_fn(ctx)
        if not items:
            result = StepResult(
                step_name=map_step.name, agent_name=map_step.agent.name,
                status="skipped", output="(无待处理元素)", duration=0.0,
            )
            self._flow_logger.on_step_end(result)
            ctx.add_step_result(result)
            return

        self._flow_logger.on_step_start(map_step.name, f"动态并行({len(items)}个)")
        start_time = time.time()

        # 为每个元素生成 Step
        parallel_steps = []
        for item in items:
            step = Step(
                name=f"{map_step.name}::{item}",
                agent=map_step.agent,
                input_fn=lambda ctx, i=item: map_step.make_input_fn(i, ctx),
                output_fn=lambda ctx, output, i=item: map_step.make_output_fn(i, ctx, output),
            )
            parallel_steps.append(step)

        results = self._execute_parallel_steps(parallel_steps, ctx, map_step.max_workers)

        duration = time.time() - start_time
        success_count = sum(1 for r in results.values() if r.status == "success")
        group_result = StepResult(
            step_name=map_step.name, agent_name=map_step.agent.name,
            status="success" if success_count == len(results) else "failed",
            output=f"{success_count}/{len(items)} 成功", duration=duration,
        )
        self._flow_logger.on_step_end(group_result)
        ctx.add_step_result(group_result)

    def _execute_parallel_steps(self, steps: List[Step], ctx: WorkflowContext, max_workers: int) -> Dict[str, StepResult]:
        """通用并行执行逻辑，返回 {step_name: StepResult}"""
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_step = {}
            for step in steps:
                if step.condition and not step.condition(ctx):
                    continue
                future = executor.submit(self._run_step, step, ctx)
                future_to_step[future] = step

            for future in as_completed(future_to_step):
                step = future_to_step[future]
                try:
                    results[step.name] = future.result()
                except Exception as e:
                    logger.error(f"并行步骤 '{step.name}' 异常: {e}")
                    results[step.name] = StepResult(
                        step_name=step.name, agent_name=step.agent.name,
                        status="failed", output=str(e), duration=0.0,
                    )
        return results

    # ─── 主执行入口 ──────────────────────────────────────────

    def run(self, ctx: WorkflowContext) -> WorkflowContext:
        """执行工作流"""
        self._flow_logger.on_workflow_start(self.name)
        ctx.status = "running"

        try:
            for entry in self._execution_order:
                kind, name = entry.split(":", 1)

                if kind == "step":
                    step = next((s for s in self._steps if s.name == name), None)
                    if step:
                        self._run_step(step, ctx)

                elif kind == "loop":
                    loop = next((l for l in self._loop_groups if l.name == name), None)
                    if loop:
                        self._run_loop(loop, ctx)

                elif kind == "parallel":
                    parallel = next((p for p in self._parallel_groups if p.name == name), None)
                    if parallel:
                        self._run_parallel(parallel, ctx)

                elif kind == "map":
                    map_step = next((m for m in self._map_steps if m.name == name), None)
                    if map_step:
                        self._run_map_parallel(map_step, ctx)

            ctx.status = "completed"
            self._flow_logger.on_workflow_end("completed")

        except StepError as e:
            ctx.status = "failed"
            self._flow_logger.on_workflow_end("failed")
            raise EngineError(f"工作流执行失败: {e}") from e
        except Exception as e:
            ctx.status = "failed"
            self._flow_logger.on_workflow_end("failed")
            raise EngineError(f"工作流执行异常: {e}") from e

        return ctx

    @property
    def flow_logger(self) -> FlowLogger:
        return self._flow_logger