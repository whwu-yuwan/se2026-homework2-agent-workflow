"""
代码审查工作流定义
编排 CodeAgent → ReviewAgent → FixAgent 的完整流程
支持 Agent 间追问、registry 注入
"""

import re
from typing import Optional

import config
from workflow.engine import WorkflowEngine, Step, LoopGroup, AGENT_REQUEST_KEY, AGENT_RESPONSE_KEY
from workflow.context import WorkflowContext
from agents.registry import AgentRegistry, default_registry


def _parse_review_conclusion(review_output: str) -> bool:
    """解析审查报告的结论: True=NEEDS_FIX, False=PASS"""
    for line in review_output.split('\n'):
        stripped = line.strip()
        if stripped.startswith("NEEDS_FIX"):
            return True
        if stripped.startswith("PASS"):
            return False
    critical_count = len(re.findall(r'\[critical\]', review_output, re.IGNORECASE))
    return critical_count > 0


def _extract_agent_request(ctx: WorkflowContext, output: str, from_agent: str) -> None:
    """从 Agent 输出中提取追问请求

    约定格式: [REQUEST:AgentName] 请求内容
    """
    pattern = r'\[REQUEST:(\w+)\]\s*(.+?)(?:\n|$)'
    match = re.search(pattern, output)
    if match:
        target = match.group(1)
        message = match.group(2).strip()
        ctx.set(AGENT_REQUEST_KEY, {
            "to": target,
            "message": message,
            "from": from_agent,
        })
        history = ctx.get("agent_request_history", [])
        history.append({"from": from_agent, "to": target, "request": message})
        ctx.set("agent_request_history", history)


def _record_agent_response(ctx: WorkflowContext) -> None:
    """将上一轮的 Agent 响应记录到追问历史"""
    response = ctx.get(AGENT_RESPONSE_KEY)
    if not response:
        return
    history = ctx.get("agent_request_history", [])
    if history and "response" not in history[-1]:
        history[-1]["response"] = response[:500]
        ctx.set("agent_request_history", history)


# ─── 输入/输出函数 ──────────────────────────────────────────

def _read_code_input(ctx: WorkflowContext) -> str:
    return f"请读取并分析以下代码：\n\n{ctx.get('user_input', '')}"


def _store_code(ctx: WorkflowContext, output: str) -> None:
    ctx.set("code", output)


def _review_input(ctx: WorkflowContext) -> str:
    """构造审查输入，包含上一轮的 Agent 追问响应"""
    base = f"请审查以下代码，给出详细的审查报告：\n\n```python\n{ctx.get('code')}\n```"

    agent_response = ctx.get(AGENT_RESPONSE_KEY)
    if agent_response:
        base += f"\n\n## 补充信息（来自其他 Agent）\n{agent_response}"
        ctx.set(AGENT_RESPONSE_KEY, None)

    history = ctx.get("agent_request_history", [])
    if history:
        base += "\n\n## 追问历史\n"
        for h in history[-3:]:
            resp = h.get('response', '')
            base += f"- 请求: {h.get('request', '')}"
            if resp:
                base += f" → 响应: {resp[:200]}"
            base += "\n"

    return base


def _store_review(ctx: WorkflowContext, output: str) -> None:
    """存储审查结果，解析结论，提取追问请求，记录响应到历史"""
    ctx.set("review_result", output)
    ctx.set("has_critical_issues", _parse_review_conclusion(output))
    _extract_agent_request(ctx, output, "ReviewAgent")
    _record_agent_response(ctx)


def _fix_input(ctx: WorkflowContext) -> str:
    return (
        f"请根据以下审查报告修复代码。\n\n"
        f"## 原始代码\n```python\n{ctx.get('code')}\n```\n\n"
        f"## 审查报告\n{ctx.get('review_result')}"
    )


def _has_issues(ctx: WorkflowContext) -> bool:
    return ctx.get("has_critical_issues", False)


def _consume_response_on_pass(ctx: WorkflowContext, output: str) -> None:
    """PASS 路径：消费 Agent 响应并记录到历史，再标记无问题"""
    ctx.set("review_result", output)
    ctx.set("has_critical_issues", False)
    _record_agent_response(ctx)
    ctx.set(AGENT_RESPONSE_KEY, None)


# ─── 工作流构建 ─────────────────────────────────────────────

def build_code_review_workflow(
    verbose: bool = True,
    registry: Optional[AgentRegistry] = None,
) -> WorkflowEngine:
    """构建代码审查工作流

    Args:
        verbose: 是否实时打印执行日志
        registry: Agent 注册表（None 则使用默认注册表，支持注入）

    Returns:
        配置好的工作流引擎
    """
    reg = registry or default_registry

    code_agent = reg.create("CodeAgent")
    review_agent = reg.create("ReviewAgent")
    fix_agent = reg.create("FixAgent")

    engine = WorkflowEngine(name="代码审查工作流", verbose=verbose, fail_fast=True)

    engine.register_agent(code_agent)
    engine.register_agent(review_agent)
    engine.register_agent(fix_agent)

    engine.add_step(Step(
        name="读取代码",
        agent=code_agent,
        input_fn=_read_code_input,
        output_fn=_store_code,
    ))

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
        reset_agents=True,
    ))

    return engine


def run_code_review(user_input: str, verbose: bool = True) -> WorkflowContext:
    ctx = WorkflowContext(initial_data={"user_input": user_input})
    engine = build_code_review_workflow(verbose=verbose)
    return engine.run(ctx)