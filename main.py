"""
CLI 交互界面
支持多工作流选择：代码审查 / 文档生成
"""

import sys
import logging

import config
from logger import setup_logging
from exceptions import ConfigError, WorkflowError
from workflow.context import WorkflowContext
from workflows.code_review import build_code_review_workflow
from workflows.doc_generation import build_doc_generation_workflow
from agents.registry import default_registry

logger = logging.getLogger(__name__)

# 可用工作流映射
WORKFLOWS = {
    "1": ("代码审查", build_code_review_workflow),
    "2": ("文档生成", build_doc_generation_workflow),
}

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║           🔍 多 Agent 协同工作流系统                           ║
║                                                              ║
║  三个 Agent 协同工作：                                        ║
║    CodeAgent   → 读取和分析代码                               ║
║    ReviewAgent → 审查代码质量 / 分析代码结构                   ║
║    FixAgent    → 修复代码 / 生成文档                          ║
║                                                              ║
║  可用工作流：                                                 ║
║    1. 代码审查  代码 → 审查 → 修复（循环直到通过）             ║
║    2. 文档生成  代码 → 分析 → 生成文档                        ║
║                                                              ║
║  命令：                                                      ║
║    /help      - 显示帮助信息                                 ║
║    /workflow  - 切换工作流                                   ║
║    /agents    - 查看已注册的 Agent                            ║
║    /verbose   - 切换详细模式                                 ║
║    /quit      - 退出程序                                     ║
╚══════════════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
📖 帮助信息
───────────────────────────────────
命令：
  /help      - 显示此帮助信息
  /workflow  - 切换工作流（代码审查/文档生成）
  /agents    - 查看已注册的 Agent 列表
  /verbose   - 切换详细模式（显示每步执行详情）
  /quit      - 退出程序

使用方式：
  1. 输入文件路径 → Agent 自动读取并处理
     示例: main.py
     示例: D:\\project\\app.py

  2. 直接粘贴代码 → Agent 分析处理
     示例: def foo():
              return 1/0
───────────────────────────────────
"""


def check_api_key() -> None:
    """检查 API Key 是否已设置"""
    if not config.API_KEY:
        raise ConfigError(
            "未设置 DEEPSEEK_API_KEY 环境变量\n"
            "请按以下步骤设置：\n"
            "  Windows:  set DEEPSEEK_API_KEY=your-api-key-here\n"
            "  Linux/Mac: export DEEPSEEK_API_KEY=your-api-key-here"
        )


def handle_command(command: str, state: dict) -> bool:
    """处理斜杠命令

    Args:
        command: 用户输入的命令
        state: 应用状态字典

    Returns:
        True 表示应该退出程序
    """
    command = command.strip().lower()

    if command in ("/quit", "/exit"):
        print("\n👋 再见！")
        return True

    elif command == "/help":
        print(HELP_TEXT)

    elif command == "/verbose":
        state["verbose"] = not state["verbose"]
        mode = "开启" if state["verbose"] else "关闭"
        print(f"✅ 详细模式已{mode}")

    elif command == "/workflow":
        print("\n可用工作流：")
        for key, (name, _) in WORKFLOWS.items():
            marker = " ← 当前" if key == state["workflow"] else ""
            print(f"  {key}. {name}{marker}")
        choice = input("选择工作流编号: ").strip()
        if choice in WORKFLOWS:
            state["workflow"] = choice
            print(f"✅ 已切换到: {WORKFLOWS[choice][0]}")
        else:
            print("❌ 无效选择")

    elif command == "/agents":
        agents = default_registry.list_agents()
        print(f"\n已注册的 Agent ({len(agents)} 个):")
        for name in agents:
            print(f"  - {name}")

    else:
        print(f"❌ 未知命令: {command}")
        print("输入 /help 查看可用命令")

    return False


def run_workflow(user_input: str, state: dict) -> None:
    """执行选定的工作流"""
    workflow_key = state["workflow"]
    workflow_name, build_fn = WORKFLOWS[workflow_key]

    try:
        ctx = WorkflowContext(initial_data={"user_input": user_input})
        engine = build_fn(verbose=state["verbose"])
        ctx = engine.run(ctx)

        # 输出最终结果
        print(f"\n{'='*60}")
        print(f"📋 最终结果 - {workflow_name}")
        print(f"{'='*60}")

        # 通用结果输出
        for key in ["review_result", "analysis", "documentation"]:
            if ctx.has(key):
                label = {"review_result": "审查报告", "analysis": "分析报告", "documentation": "生成文档"}
                print(f"\n📝 {label.get(key, key)}:")
                print(ctx.get(key))

        if ctx.has("code"):
            print(f"\n💻 代码:")
            print(ctx.get("code"))

        # 执行摘要
        print(f"\n{engine.flow_logger.get_summary()}")
        round_key = f"审查-修复循环_round"
        if ctx.has(round_key):
            print(f"循环轮次: {ctx.get(round_key)}")

    except WorkflowError as e:
        print(f"\n❌ 工作流错误: {e}")
        logger.error(f"工作流错误: {e}")
    except Exception as e:
        print(f"\n❌ 未知错误: {e}")
        logger.error(f"未知错误: {e}", exc_info=True)


def main():
    """主函数"""
    setup_logging(
        log_file=config.LOG_FILE,
        console_level=config.LOG_CONSOLE_LEVEL,
        file_level=config.LOG_FILE_LEVEL
    )

    print(BANNER)

    try:
        check_api_key()
    except ConfigError as e:
        print(f"❌ 配置错误: {e}")
        sys.exit(1)

    print("✅ 准备就绪！输入文件路径或代码开始。")
    print("─" * 50)

    state = {"verbose": True, "workflow": "1"}

    while True:
        try:
            user_input = input("\n🧑 You > ").strip()

            if not user_input:
                continue

            if user_input.startswith("/"):
                if handle_command(user_input, state):
                    break
                continue

            run_workflow(user_input, state)

        except KeyboardInterrupt:
            print("\n\n👋 再见！（Ctrl+C）")
            break
        except EOFError:
            print("\n\n👋 再见！（EOF）")
            break


if __name__ == "__main__":
    main()