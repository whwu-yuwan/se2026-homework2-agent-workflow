"""
文档生成工作流定义
CodeAgent 发现文件 → MapParallelStep 动态并行分析 → FixAgent 合并生成文档
展示 MapParallelStep 动态扇出能力
"""

from typing import Optional

from workflow.engine import WorkflowEngine, Step, MapParallelStep
from workflow.context import WorkflowContext
from agents.registry import AgentRegistry, default_registry


# ─── Step 1: CodeAgent 发现文件 ──────────────────────────────

def _discover_files_input(ctx: WorkflowContext) -> str:
    return (
        "请分析以下路径，列出所有 Python 代码文件。\n"
        "如果是文件路径，直接返回该文件路径。\n"
        "如果是目录路径，列出目录下所有 .py 文件。\n"
        "每个文件路径占一行，只输出路径，不要其他内容。\n\n"
        f"路径: {ctx.get('user_input', '')}"
    )


def _store_file_list(ctx: WorkflowContext, output: str) -> None:
    files = [f.strip() for f in output.strip().split('\n')
             if f.strip() and not f.strip().startswith('#')]
    files = list(dict.fromkeys(files))[:4]  # 去重 + 限制 4 个
    ctx.set("file_list", files)


# ─── MapParallelStep: 动态并行分析 ──────────────────────────

def _make_analysis_input(file_path: str, ctx: WorkflowContext) -> str:
    return (
        f"请详细分析以下代码文件的结构和功能。\n"
        f"包括：模块功能、主要类/函数、依赖关系、核心逻辑。\n\n"
        f"文件路径: {file_path}"
    )


def _make_analysis_output(file_path: str, ctx: WorkflowContext, output: str) -> None:
    analyses = ctx.get("file_analyses", {})
    analyses[file_path] = output
    ctx.set("file_analyses", analyses)


# ─── Step 3: FixAgent 合并生成文档 ──────────────────────────

def _merge_doc_input(ctx: WorkflowContext) -> str:
    analyses = ctx.get("file_analyses", {})
    files = ctx.get("file_list", [])

    parts = []
    for f in files:
        if f in analyses:
            parts.append(f"### {f}\n\n{analyses[f]}")
    combined = "\n\n---\n\n".join(parts)

    return (
        "请根据以下多个文件的分析报告，合并生成一份完整的项目文档（README.md 格式）。\n"
        "文档应包含：项目概述、模块说明、文件结构、核心功能、使用说明。\n\n"
        f"## 分析报告\n\n{combined}"
    )


def _store_doc(ctx: WorkflowContext, output: str) -> None:
    ctx.set("documentation", output)


# ─── 工作流构建 ─────────────────────────────────────────────

def build_doc_generation_workflow(
    verbose: bool = True,
    registry: Optional[AgentRegistry] = None,
) -> WorkflowEngine:
    """构建文档生成工作流

    流程：
    1. CodeAgent 发现/列出代码文件
    2. MapParallelStep: 运行时根据文件列表动态生成并行分析任务
    3. FixAgent 合并所有分析报告，生成最终文档

    使用 MapParallelStep 而非 ParallelGroup，因为文件数量运行时才知道。

    Args:
        verbose: 是否实时打印执行日志
        registry: Agent 注册表（支持注入）

    Returns:
        配置好的工作流引擎
    """
    reg = registry or default_registry
    code_agent = reg.create("CodeAgent")
    doc_agent = reg.create("FixAgent")
    analysis_agent = reg.create("ReviewAgent")

    engine = WorkflowEngine(name="文档生成工作流", verbose=verbose, fail_fast=True)

    # Step 1: CodeAgent 发现文件
    engine.add_step(Step(
        name="发现文件",
        agent=code_agent,
        input_fn=_discover_files_input,
        output_fn=_store_file_list,
    ))

    # Step 2: MapParallelStep 动态并行分析
    # 运行时从 ctx.get("file_list") 获取文件列表，为每个文件生成并行任务
    engine.add_map_parallel(MapParallelStep(
        name="并行分析文件",
        agent=analysis_agent,
        items_fn=lambda ctx: ctx.get("file_list", []),
        make_input_fn=_make_analysis_input,
        make_output_fn=_make_analysis_output,
        max_workers=4,
    ))

    # Step 3: FixAgent 合并生成文档
    engine.add_step(Step(
        name="生成文档",
        agent=doc_agent,
        input_fn=_merge_doc_input,
        output_fn=_store_doc,
    ))

    return engine


def run_doc_generation(user_input: str, verbose: bool = True) -> WorkflowContext:
    ctx = WorkflowContext(initial_data={"user_input": user_input})
    engine = build_doc_generation_workflow(verbose=verbose)
    return engine.run(ctx)