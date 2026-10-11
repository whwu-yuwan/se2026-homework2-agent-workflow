"""
代码审查工作流定义
编排 CodeAgent → ReviewAgent → FixAgent 的完整流程
使用 AgentRegistry 进行动态 Agent 创建
"""

import re

import config
from workflow.engine import WorkflowEngine, Step, LoopGroup
from workflow.context import WorkflowContext
from agents.registry import default_registry


def _parse_review_conclusion(review_output: str) -> bool:
    """解析审查报告的结论

    Returns:
        True 表示有严重问题需要修复（NEEDS_FIX），False 表示通过（PASS）
    """
    for line in review_output.split('\n'):
        stripped = line.strip()
        if stripped.startswith("NEEDS_FIX"):
            return True
        if stripped.startswith("PASS"):
            return False
    critical_count = len(re.findall(r'\[critical\]', review_output, re.IGNORECASE))
    return critical_count > 0


# ─── 通用化的输入/输出函数 ────────────────────────────────────

def _read_code_input(ctx: WorkflowContext) -> str:
    """从上下文提取用户输入"""
    return f"请读取并分析以下代码：\n\n{ctx.get('user_input', '')}"


def _store_code(ctx: WorkflowContext, output: str) -> None:
    """将 Agent 输出存为代码"""
    ctx.set("code", output)


def _review_input(ctx: WorkflowContext) -> str:
    """构造审查输入"""
    return f"请审查以下代码，给出详细的审查报告：\n\n```python\n{ctx.get('code')}\n```"


def _store_review(ctx: WorkflowContext, output: str) -> None:
    """存储审查结果并解析结论"""
    ctx.set("review_result", output)
    ctx.set("has_critical_issues", _parse_review_conclusion(output))


def _fix_input(ctx: WorkflowContext) -> str:
    """构造修复输入"""
    return (
        f"请根据以下审查报告修复代码。\n\n"
        f"## 原始代码\n```python\n{ctx.get('code')}\n```\n\n"
        f"## 审查报告\n{ctx.get('review_result')}"
    )


def _has_issues(ctx: WorkflowContext) -> bool:
    """检查是否有严重问题"""
    return ctx.get("has_critical_issues", False)


def build_code_review_workflow(verbose: bool = True) -> WorkflowEngine:
    """构建代码审查工作流

    流程：
    1. CodeAgent 读取代码
    2. [循环] ReviewAgent 审查 → 判断 → FixAgent 修复（最多 MAX_REVIEW_ROUNDS 轮）

    Args:
        verbose: 是否实时打印执行日志

    Returns:
        配置好的工作流引擎
    """
    # 通过注册表创建 Agent 实例
    code_agent = default_registry.create("CodeAgent")
    review_agent = default_registry.create("ReviewAgent")
    fix_agent = default_registry.create("FixAgent")

    engine = WorkflowEngine(name="代码审查工作流", verbose=verbose)

    # Step 1: CodeAgent 读取代码
    engine.add_step(Step(
        name="读取代码",
        agent=code_agent,
        input_fn=_read_code_input,
        output_fn=_store_code,
    ))

    # LoopGroup: 审查 → 修复 循环
    engine.add_loop(LoopGroup(
        name="审查-修复循环",
        steps=[
            Step(
                name="代码审查",
                agent=review_agent,
                input_fn=_review_input,
                output_fn=_store_review,
            ),
            Step(
                name="代码修复",
                agent=fix_agent,
                input_fn=_fix_input,
                output_fn=_store_code,
                condition=_has_issues,
            ),
        ],
        condition=_has_issues,
        max_rounds=config.MAX_REVIEW_ROUNDS,
    ))

    return engine


def run_code_review(user_input: str, verbose: bool = True) -> WorkflowContext:
    """运行代码审查工作流（便捷入口）"""
    ctx = WorkflowContext(initial_data={"user_input": user_input})
    engine = build_code_review_workflow(verbose=verbose)
    return engine.run(ctx)