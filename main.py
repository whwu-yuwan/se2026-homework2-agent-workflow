"""
CLI 交互界面
代码审查工作流的命令行入口
"""

import sys
import logging
from pathlib import Path

import config
from logger import setup_logging
from exceptions import ConfigError, WorkflowError
from workflow.context import WorkflowContext
from workflows.code_review import build_code_review_workflow

logger = logging.getLogger(__name__)

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║           🔍 代码审查工作流 (Code Review Workflow)             ║
║                                                              ║
║  三个 Agent 协同工作：                                        ║
║    CodeAgent   → 读取和分析代码                               ║
║    ReviewAgent → 审查代码质量，发现问题                       ║
║    FixAgent    → 根据审查报告修复代码                         ║
║                                                              ║
║  流程：代码 → 审查 → 修复 → 再审查（循环直到通过）             ║
║                                                              ║
║  命令：                                                      ║
║    /help      - 显示帮助信息                                 ║
║    /verbose   - 切换详细模式                                 ║
║    /quit      - 退出程序                                     ║
║                                                              ║
║  使用：输入文件路径或直接粘贴代码开始审查                       ║
╚══════════════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
📖 帮助信息
───────────────────────────────────
命令：
  /help      - 显示此帮助信息
  /verbose   - 切换详细模式（显示每步执行详情）
  /quit      - 退出程序

使用方式：
  1. 输入文件路径 → Agent 自动读取并审查
     示例: main.py
     示例: D:\\project\\app.py

  2. 直接粘贴代码 → Agent 审查并修复
     示例: def foo():
              return 1/0

工作流程：
  CodeAgent 读取代码 → ReviewAgent 审查 → FixAgent 修复
  如果审查发现问题，会自动循环修复（最多 3 轮）
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


def handle_command(command: str, verbose: list) -> bool:
    """处理斜杠命令

    Args:
        command: 用户输入的命令
        verbose: [is_verbose] 可变列表，用于修改 verbose 状态

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
        verbose[0] = not verbose[0]
        mode = "开启" if verbose[0] else "关闭"
        print(f"✅ 详细模式已{mode}")

    else:
        print(f"❌ 未知命令: {command}")
        print("输入 /help 查看可用命令")

    return False


def run_workflow(user_input: str, is_verbose: bool) -> None:
    """执行代码审查工作流"""
    try:
        ctx = WorkflowContext(initial_data={"user_input": user_input})
        engine = build_code_review_workflow(verbose=is_verbose)
        ctx = engine.run(ctx)

        # 输出最终结果
        print(f"\n{'='*60}")
        print("📋 最终结果")
        print(f"{'='*60}")

        if ctx.has("review_result"):
            print("\n📝 审查报告:")
            print(ctx.review_result)

        if ctx.has("code"):
            print(f"\n💻 {'修复后代码' if ctx.review_round > 1 else '代码'}:")
            print(ctx.code)

        # 执行摘要
        print(f"\n{engine.flow_logger.get_summary()}")
        print(f"审查轮次: {ctx.review_round}")

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

    # 检查 API Key
    try:
        check_api_key()
    except ConfigError as e:
        print(f"❌ 配置错误: {e}")
        sys.exit(1)

    print("✅ 准备就绪！输入文件路径或代码开始审查。")
    print("─" * 50)

    is_verbose = [True]  # 用列表包装以便在嵌套函数中修改

    while True:
        try:
            user_input = input("\n🧑 You > ").strip()

            if not user_input:
                continue

            if user_input.startswith("/"):
                if handle_command(user_input, is_verbose):
                    break
                continue

            run_workflow(user_input, is_verbose[0])

        except KeyboardInterrupt:
            print("\n\n👋 再见！（Ctrl+C）")
            break
        except EOFError:
            print("\n\n👋 再见！（EOF）")
            break


if __name__ == "__main__":
    main()