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
    """构造审查输入（包含上一轮的 Agent 追问响应）"""
    base = f"请审查以下代码，给出详细的审查报告：\n\n```python\n{ctx.get('code')}\n```"

    # 如果有上一轮的 Agent 追问响应，附加到输入中
    agent_response = ctx.get("_agent_response")
    if agent_response:
        base += f"\n\n## 补充信息（来自其他 Agent）\n{agent_response}"
        ctx.set("_agent_response", None)  # 消费掉响应

    # 如果有上一轮的追问历史，也附加
    history = ctx.get("agent_request_history", [])
    if history:
        base += "\n\n## 追问历史\n"
        for h in history[-3:]:  # 最多保留最近 3 条
            base += f"- 请求: {h.get('request', '')} → 响应: {h.get('response', '')[:200]}\n"

    return base


def _store_review(ctx: WorkflowContext, output: str) -> None:
    """存储审查结果，解析结论，并检查是否需要追问其他 Agent"""
    ctx.set("review_result", output)
    ctx.set("has_critical_issues", _parse_review_conclusion(output))

    # 检查 ReviewAgent 的输出中是否包含追问请求
    # 约定格式: Agent 可以在回复中写 "[REQUEST:CodeAgent] 请读取 xxx 文件"
    _extract_agent_request(ctx, output, "ReviewAgent")


def _extract_agent_request(ctx: WorkflowContext, output: str, from_agent: str) -> None:
    """从 Agent 输出中提取追问请求

    约定格式: [REQUEST:AgentName] 请求内容
    例如: [REQUEST:CodeAgent] 请读取 utils.py 查看 import 依赖
    """
    import re
    pattern = r'\[REQUEST:(\w+)\]\s*(.+?)(?:\n|$)'
    match = re.search(pattern, output)
    if match:
        target = match.group(1)
        message = match.group(2).strip()
        ctx.set("_agent_request", {
            "to": target,
            "message": message,
            "from": from_agent,
        })
        # 记录追问历史
        history = ctx.get("agent_request_history", [])
        history.append({"from": from_agent, "to": target, "request": message})
        ctx.set("agent_request_history", history)


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

    # 注册 Agent 用于 Agent 间请求路由
    engine.register_agent(code_agent)
    engine.register_agent(review_agent)
    engine.register_agent(fix_agent)

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