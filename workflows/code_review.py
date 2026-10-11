"""
代码审查工作流定义
编排 CodeAgent → ReviewAgent → FixAgent 的完整流程
"""

import re

import config
from workflow.engine import WorkflowEngine, Step, LoopGroup
from workflow.context import WorkflowContext
from agents.code_agent import CodeAgent
from agents.review_agent import ReviewAgent
from agents.fix_agent import FixAgent


def _parse_review_conclusion(review_output: str) -> bool:
    """解析审查报告的结论

    Returns:
        True 表示有严重问题需要修复（NEEDS_FIX），False 表示通过（PASS）
    """
    # 查找结论行
    for line in review_output.split('\n'):
        stripped = line.strip()
        if stripped.startswith("NEEDS_FIX"):
            return True
        if stripped.startswith("PASS"):
            return False

    # 兜底：检查是否有 critical 问题
    critical_count = len(re.findall(r'\[critical\]', review_output, re.IGNORECASE))
    return critical_count > 0


def build_code_review_workflow(verbose: bool = True) -> WorkflowEngine:
    """构建代码审查工作流

    流程：
    1. CodeAgent 读取代码
    2. [循环] ReviewAgent 审查 → 判断 → FixAgent 修复
       （最多 MAX_REVIEW_ROUNDS 轮）
    3. 输出最终结果

    Args:
        verbose: 是否实时打印执行日志

    Returns:
        配置好的工作流引擎
    """
    # 创建 Agent 实例
    code_agent = CodeAgent()
    review_agent = ReviewAgent()
    fix_agent = FixAgent()

    # 创建引擎
    engine = WorkflowEngine(name="代码审查工作流", verbose=verbose)

    # Step 1: CodeAgent 读取代码
    engine.add_step(Step(
        name="读取代码",
        agent=code_agent,
        input_fn=lambda ctx: f"请读取并分析以下代码：\n\n{ctx.get('user_input', '')}",
        output_fn=lambda ctx, output: ctx.set("code", output),
    ))

    # LoopGroup: 审查 → 修复 循环
    engine.add_loop(LoopGroup(
        name="审查-修复循环",
        steps=[
            # Step 2: ReviewAgent 审查
            Step(
                name="代码审查",
                agent=review_agent,
                input_fn=lambda ctx: (
                    f"请审查以下代码，给出详细的审查报告：\n\n"
                    f"```python\n{ctx.code}\n```"
                ),
                output_fn=lambda ctx, output: (
                    ctx.set("review_result", output),
                    ctx.set("has_critical_issues", _parse_review_conclusion(output)),
                ),
            ),
            # Step 3: FixAgent 修复（仅在有问题时执行）
            Step(
                name="代码修复",
                agent=fix_agent,
                input_fn=lambda ctx: (
                    f"请根据以下审查报告修复代码。\n\n"
                    f"## 原始代码\n```python\n{ctx.code}\n```\n\n"
                    f"## 审查报告\n{ctx.review_result}"
                ),
                output_fn=lambda ctx, output: ctx.set("code", output),
                condition=lambda ctx: ctx.has_critical_issues,
            ),
        ],
        # 继续循环的条件：审查发现严重问题 且 未超过最大轮次
        condition=lambda ctx: ctx.has_critical_issues,
        max_rounds=config.MAX_REVIEW_ROUNDS,
    ))

    return engine


def run_code_review(user_input: str, verbose: bool = True) -> WorkflowContext:
    """运行代码审查工作流（便捷入口）

    Args:
        user_input: 用户输入（文件路径或代码内容）
        verbose: 是否实时打印执行日志

    Returns:
        工作流上下文（包含最终代码、审查报告等）
    """
    ctx = WorkflowContext(initial_data={"user_input": user_input})
    engine = build_code_review_workflow(verbose=verbose)
    return engine.run(ctx)