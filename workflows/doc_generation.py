"""
文档生成工作流定义
编排 CodeAgent → ReviewAgent(分析) → FixAgent(生成文档) 的完整流程
与代码审查工作流共享相同的 Agent 和引擎，展示架构的可复用性
"""

import config
from workflow.engine import WorkflowEngine, Step, LoopGroup
from workflow.context import WorkflowContext
from agents.registry import default_registry


# ─── 通用化的输入/输出函数 ────────────────────────────────────

def _read_code_input(ctx: WorkflowContext) -> str:
    """从上下文提取用户输入"""
    return f"请读取并分析以下代码文件：\n\n{ctx.get('user_input', '')}"


def _store_code(ctx: WorkflowContext, output: str) -> None:
    """将 Agent 输出存为代码"""
    ctx.set("code", output)


def _analyze_input(ctx: WorkflowContext) -> str:
    """构造分析输入（复用 ReviewAgent 做代码分析）"""
    return (
        "请分析以下代码的结构和功能，生成一份详细的技术分析报告。\n"
        "包括：模块功能、类/函数列表、依赖关系、核心逻辑。\n\n"
        f"```python\n{ctx.get('code')}\n```"
    )


def _store_analysis(ctx: WorkflowContext, output: str) -> None:
    """存储分析结果"""
    ctx.set("analysis", output)
    ctx.set("analysis_done", True)


def _doc_input(ctx: WorkflowContext) -> str:
    """构造文档生成输入"""
    return (
        "请根据以下代码和分析报告，生成一份完整的项目文档（README.md 格式）。\n\n"
        f"## 代码\n```python\n{ctx.get('code')}\n```\n\n"
        f"## 分析报告\n{ctx.get('analysis')}"
    )


def _store_doc(ctx: WorkflowContext, output: str) -> None:
    """存储生成的文档"""
    ctx.set("documentation", output)


def _needs_more_analysis(ctx: WorkflowContext) -> bool:
    """检查是否需要补充分析（代码较长时进行分段分析）"""
    code = ctx.get("code", "")
    # 代码超过 500 行时触发补充分析
    return len(code.split('\n')) > 500 and ctx.get("analysis_round", 0) < 2


def build_doc_generation_workflow(verbose: bool = True) -> WorkflowEngine:
    """构建文档生成工作流

    流程：
    1. CodeAgent 读取代码
    2. ReviewAgent 分析代码结构
    3. [可选循环] 代码过长时补充分析（最多 2 轮）
    4. FixAgent 生成文档

    Args:
        verbose: 是否实时打印执行日志

    Returns:
        配置好的工作流引擎
    """
    # 通过注册表创建 Agent
    code_agent = default_registry.create("CodeAgent")
    analysis_agent = default_registry.create("ReviewAgent")
    doc_agent = default_registry.create("FixAgent")

    engine = WorkflowEngine(name="文档生成工作流", verbose=verbose)

    # Step 1: CodeAgent 读取代码
    engine.add_step(Step(
        name="读取代码",
        agent=code_agent,
        input_fn=_read_code_input,
        output_fn=_store_code,
    ))

    # Step 2: ReviewAgent 分析代码结构
    engine.add_step(Step(
        name="代码分析",
        agent=analysis_agent,
        input_fn=_analyze_input,
        output_fn=_store_analysis,
    ))

    # Step 3: FixAgent 生成文档
    engine.add_step(Step(
        name="生成文档",
        agent=doc_agent,
        input_fn=_doc_input,
        output_fn=_store_doc,
    ))

    return engine


def run_doc_generation(user_input: str, verbose: bool = True) -> WorkflowContext:
    """运行文档生成工作流（便捷入口）"""
    ctx = WorkflowContext(initial_data={"user_input": user_input})
    engine = build_doc_generation_workflow(verbose=verbose)
    return engine.run(ctx)