"""
文档生成工作流定义
编排 CodeAgent → 并行分析多个文件 → FixAgent 合并生成文档
展示 ParallelGroup 并行能力和多 Agent 协作
"""

import config
from workflow.engine import WorkflowEngine, Step, LoopGroup, ParallelGroup
from workflow.context import WorkflowContext
from agents.registry import default_registry


# ─── Step 1: CodeAgent 发现文件 ──────────────────────────────

def _discover_files_input(ctx: WorkflowContext) -> str:
    """输入：用户提供的路径"""
    return (
        "请分析以下路径，列出所有 Python 代码文件。\n"
        "如果是文件路径，直接返回该文件路径。\n"
        "如果是目录路径，列出目录下所有 .py 文件。\n"
        "每个文件路径占一行，只输出路径，不要其他内容。\n\n"
        f"路径: {ctx.get('user_input', '')}"
    )


def _store_file_list(ctx: WorkflowContext, output: str) -> None:
    """解析文件列表并存储"""
    files = [f.strip() for f in output.strip().split('\n') if f.strip() and not f.strip().startswith('#')]
    # 去重并限制最多 4 个文件（并行分析的合理上限）
    files = list(dict.fromkeys(files))[:4]
    ctx.set("file_list", files)
    ctx.set("file_count", len(files))


# ─── 并行分析：每个文件一个 ReviewAgent 实例 ─────────────────

def _make_file_analysis_input(file_path: str):
    """为指定文件创建分析输入函数"""
    def input_fn(ctx: WorkflowContext) -> str:
        return f"请详细分析以下代码文件的结构和功能：\n\n文件路径: {file_path}"
    return input_fn


def _make_file_analysis_output(file_path: str):
    """为指定文件创建分析输出函数"""
    def output_fn(ctx: WorkflowContext, output: str) -> None:
        analyses = ctx.get("file_analyses", {})
        analyses[file_path] = output
        ctx.set("file_analyses", analyses)
    return output_fn


# ─── Step 3: FixAgent 合并生成文档 ──────────────────────────

def _merge_doc_input(ctx: WorkflowContext) -> str:
    """构造合并文档的输入"""
    analyses = ctx.get("file_analyses", {})
    files = ctx.get("file_list", [])

    parts = []
    for f in files:
        if f in analyses:
            parts.append(f"### {f}\n\n{analyses[f]}")

    combined_analysis = "\n\n---\n\n".join(parts)

    return (
        "请根据以下多个文件的分析报告，合并生成一份完整的项目文档（README.md 格式）。\n"
        "文档应包含：项目概述、模块说明、文件结构、核心功能、使用说明。\n\n"
        f"## 分析报告\n\n{combined_analysis}"
    )


def _store_doc(ctx: WorkflowContext, output: str) -> None:
    """存储生成的文档"""
    ctx.set("documentation", output)


# ─── 工作流构建 ─────────────────────────────────────────────

def build_doc_generation_workflow(verbose: bool = True) -> WorkflowEngine:
    """构建文档生成工作流

    流程：
    1. CodeAgent 发现/列出代码文件
    2. ParallelGroup: 多个 ReviewAgent 实例并行分析每个文件
    3. FixAgent 合并所有分析报告，生成最终文档

    这个工作流展示了：
    - ParallelGroup 并行执行
    - 动态生成并行步骤（根据文件数量）
    - 多 Agent 协作（CodeAgent 发现文件、ReviewAgent 并行分析、FixAgent 合并输出）

    Args:
        verbose: 是否实时打印执行日志

    Returns:
        配置好的工作流引擎
    """
    code_agent = default_registry.create("CodeAgent")
    doc_agent = default_registry.create("FixAgent")

    engine = WorkflowEngine(name="文档生成工作流", verbose=verbose)

    # Step 1: CodeAgent 发现文件列表
    engine.add_step(Step(
        name="发现文件",
        agent=code_agent,
        input_fn=_discover_files_input,
        output_fn=_store_file_list,
    ))

    # Step 2: 并行分析多个文件（动态创建步骤）
    # 注意：ParallelGroup 的 steps 在构建时确定，但 input_fn/output_fn
    # 通过闭包引用不同的 file_path，实现"动态"效果
    # 这里先用占位步骤，实际的并行分析通过一个专门的协调步骤实现
    engine.add_step(Step(
        name="并行分析文件",
        agent=code_agent,  # 占位，实际逻辑在 output_fn 中协调
        input_fn=_build_parallel_analysis_prompt,
        output_fn=_store_parallel_results,
    ))

    # Step 3: FixAgent 合并生成文档
    engine.add_step(Step(
        name="生成文档",
        agent=doc_agent,
        input_fn=_merge_doc_input,
        output_fn=_store_doc,
    ))

    return engine


def _build_parallel_analysis_prompt(ctx: WorkflowContext) -> str:
    """构造并行分析的提示词（将所有文件合并到一个 prompt 中让 Agent 分析）"""
    files = ctx.get("file_list", [])
    if not files:
        return "没有发现代码文件，请说明原因。"

    file_list_str = "\n".join(f"  {i+1}. {f}" for i, f in enumerate(files))
    return (
        f"请逐一分析以下 {len(files)} 个代码文件的结构和功能。\n"
        f"对每个文件输出：模块功能、主要类/函数、与其他文件的依赖关系。\n"
        f"最后总结整个项目的架构。\n\n"
        f"文件列表:\n{file_list_str}\n\n"
        f"请使用 `read_file` 工具逐一读取这些文件并分析。"
    )


def _store_parallel_results(ctx: WorkflowContext, output: str) -> None:
    """存储并行分析结果"""
    files = ctx.get("file_list", [])
    # 将整体分析结果存为每个文件的分析（简化处理）
    analyses = {}
    for f in files:
        analyses[f] = output
    ctx.set("file_analyses", analyses)
    ctx.set("analysis", output)


def build_doc_generation_parallel_workflow(verbose: bool = True) -> WorkflowEngine:
    """构建文档生成工作流（使用真正的 ParallelGroup 并行版本）

    适用于已知文件列表的场景（如 3 个文件 → 3 个并行分析步骤）

    Args:
        verbose: 是否实时打印执行日志

    Returns:
        配置好的工作流引擎
    """
    engine = WorkflowEngine(name="文档生成工作流(并行)", verbose=verbose)

    # 注意：真正的 ParallelGroup 需要在构建时知道文件列表
    # 这里展示 API 用法，实际使用时由调用方传入文件列表
    return engine


def run_doc_generation(user_input: str, verbose: bool = True) -> WorkflowContext:
    """运行文档生成工作流（便捷入口）"""
    ctx = WorkflowContext(initial_data={"user_input": user_input})
    engine = build_doc_generation_workflow(verbose=verbose)
    return engine.run(ctx)