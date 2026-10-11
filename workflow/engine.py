"""
工作流引擎
支持顺序执行、条件分支、循环控制、并行步骤、错误恢复
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
        """定义一个工作流步骤

        Args:
            name: 步骤名称
            agent: 执行此步骤的 Agent
            input_fn: 从上下文提取输入的函数
            output_fn: 将输出写入上下文的函数
            condition: 执行条件（返回 True 才执行，None 表示无条件执行）
        """
        self.name = name
        self.agent = agent
        self.input_fn = input_fn
        self.output_fn = output_fn
        self.condition = condition


class LoopGroup:
    """循环步骤组

    包含一组步骤，循环执行直到条件满足或达到最大轮次
    """

    def __init__(
        self,
        name: str,
        steps: List[Step],
        condition: Callable[[WorkflowContext], bool],
        max_rounds: int = 3,
    ):
        """定义循环步骤组

        Args:
            name: 循环名称
            steps: 循环内的步骤列表
            condition: 继续循环的条件（返回 True 继续，False 停止）
            max_rounds: 最大循环轮次
        """
        self.name = name
        self.steps = steps
        self.condition = condition
        self.max_rounds = max_rounds


class ParallelGroup:
    """并行步骤组

    包含一组步骤，同时并发执行（适用于独立任务，如同时审查多个文件）
    """

    def __init__(self, name: str, steps: List[Step], max_workers: int = 4):
        """定义并行步骤组

        Args:
            name: 并行组名称
            steps: 并行执行的步骤列表
            max_workers: 最大并发数
        """
        self.name = name
        self.steps = steps
        self.max_workers = max_workers


class WorkflowEngine:
    """工作流引擎

    功能：
    - 顺序执行步骤
    - 条件分支（通过 Step.condition）
    - 循环控制（通过 LoopGroup）
    - 并行执行（通过 ParallelGroup，适用于独立任务）
    - 错误恢复（单步失败可配置是否中断）
    - 执行日志与状态追踪
    """

    def __init__(self, name: str = "workflow", verbose: bool = True):
        """初始化引擎

        Args:
            name: 工作流名称
            verbose: 是否实时打印执行日志
        """
        self.name = name
        self._steps: List[Step] = []
        self._loop_groups: List[LoopGroup] = []
        self._parallel_groups: List[ParallelGroup] = []
        self._execution_order: List[str] = []  # "step:name" | "loop:name" | "parallel:name"
        self._flow_logger = FlowLogger(verbose=verbose)
        self._fail_fast = True

    def add_step(self, step: Step) -> "WorkflowEngine":
        """添加一个步骤"""
        self._steps.append(step)
        self._execution_order.append(f"step:{step.name}")
        return self

    def add_loop(self, loop: LoopGroup) -> "WorkflowEngine":
        """添加一个循环组"""
        self._loop_groups.append(loop)
        self._execution_order.append(f"loop:{loop.name}")
        return self

    def add_parallel(self, parallel: ParallelGroup) -> "WorkflowEngine":
        """添加一个并行组"""
        self._parallel_groups.append(parallel)
        self._execution_order.append(f"parallel:{parallel.name}")
        return self

    def _run_step(self, step: Step, ctx: WorkflowContext) -> StepResult:
        """执行单个步骤

        Args:
            step: 步骤定义
            ctx: 工作流上下文

        Returns:
            步骤执行结果
        """
        # 检查条件
        if step.condition and not step.condition(ctx):
            result = StepResult(
                step_name=step.name,
                agent_name=step.agent.name,
                status="skipped",
                output="(条件不满足，跳过)",
                duration=0.0,
            )
            self._flow_logger.on_step_end(result)
            ctx.add_step_result(result)
            return result

        # 执行步骤
        self._flow_logger.on_step_start(step.name, step.agent.name)
        start_time = time.time()

        try:
            # 从上下文提取输入
            user_input = step.input_fn(ctx)

            # 调用 Agent
            output = step.agent.run(user_input)

            # 将输出写入上下文
            step.output_fn(ctx, output)

            duration = time.time() - start_time
            result = StepResult(
                step_name=step.name,
                agent_name=step.agent.name,
                status="success",
                output=output,
                duration=duration,
            )

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"步骤 '{step.name}' 执行失败: {error_msg}")
            result = StepResult(
                step_name=step.name,
                agent_name=step.agent.name,
                status="failed",
                output=error_msg,
                duration=duration,
                metadata={"error": str(e), "error_type": type(e).__name__},
            )

        self._flow_logger.on_step_end(result)
        ctx.add_step_result(result)

        if result.status == "failed" and self._fail_fast:
            raise StepError(step.name, result.output)

        return result

    def _run_loop(self, loop: LoopGroup, ctx: WorkflowContext) -> None:
        """执行循环组

        Args:
            loop: 循环组定义
            ctx: 工作流上下文
        """
        for round_num in range(1, loop.max_rounds + 1):
            # 使用通用轮次计数器（同时兼容 review_round 便捷属性）
            ctx.set(f"{loop.name}_round", round_num)
            if hasattr(ctx, 'review_round'):
                ctx.review_round = round_num

            self._flow_logger.on_loop_start(round_num, loop.max_rounds)

            # 执行循环内的每个步骤
            for step in loop.steps:
                self._run_step(step, ctx)

            # 检查是否应该继续循环
            should_continue = loop.condition(ctx)
            self._flow_logger.on_loop_end(round_num, not should_continue)

            if not should_continue:
                logger.info(f"循环 '{loop.name}' 在第 {round_num} 轮结束（条件不满足）")
                break
        else:
            logger.warning(f"循环 '{loop.name}' 达到最大轮次 {loop.max_rounds}")

    def _run_parallel(self, parallel: ParallelGroup, ctx: WorkflowContext) -> None:
        """并行执行一组步骤

        Args:
            parallel: 并行组定义
            ctx: 工作流上下文
        """
        self._flow_logger.on_step_start(parallel.name, f"并行({len(parallel.steps)}个)")
        start_time = time.time()

        results = {}
        with ThreadPoolExecutor(max_workers=parallel.max_workers) as executor:
            future_to_step = {}
            for step in parallel.steps:
                if step.condition and not step.condition(ctx):
                    continue
                future = executor.submit(self._run_step, step, ctx)
                future_to_step[future] = step

            for future in as_completed(future_to_step):
                step = future_to_step[future]
                try:
                    result = future.result()
                    results[step.name] = result
                except Exception as e:
                    logger.error(f"并行步骤 '{step.name}' 异常: {e}")
                    results[step.name] = StepResult(
                        step_name=step.name,
                        agent_name=step.agent.name,
                        status="failed",
                        output=str(e),
                        duration=0.0,
                    )

        duration = time.time() - start_time
        success_count = sum(1 for r in results.values() if r.status == "success")
        status = "success" if success_count == len(results) else "failed"

        group_result = StepResult(
            step_name=parallel.name,
            agent_name=f"并行组({len(parallel.steps)})",
            status=status,
            output=f"{success_count}/{len(results)} 成功",
            duration=duration,
        )
        self._flow_logger.on_step_end(group_result)
        ctx.add_step_result(group_result)

    def run(self, ctx: WorkflowContext) -> WorkflowContext:
        """执行工作流

        Args:
            ctx: 工作流上下文

        Returns:
            更新后的上下文

        Raises:
            EngineError: 工作流执行失败
        """
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