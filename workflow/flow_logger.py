"""
工作流执行日志
记录每步执行详情，支持实时打印和事后查询
"""

import logging
import time
from typing import List, Optional

from workflow.context import StepResult

logger = logging.getLogger(__name__)


class FlowLogger:
    """工作流执行日志

    功能：
    - 实时打印每步执行状态（带颜色标识）
    - 记录完整执行历史
    - 生成执行摘要报告
    """

    # 状态图标
    ICONS = {
        "running": "⏳",
        "success": "✅",
        "failed": "❌",
        "skipped": "⏭️",
        "loop": "🔄",
    }

    def __init__(self, verbose: bool = True):
        """初始化

        Args:
            verbose: 是否实时打印到控制台
        """
        self.verbose = verbose
        self._records: List[dict] = []
        self._workflow_start = time.time()

    def on_workflow_start(self, workflow_name: str) -> None:
        """工作流开始"""
        self._workflow_start = time.time()
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"🚀 工作流开始: {workflow_name}")
            print(f"{'='*60}")
        logger.info(f"工作流开始: {workflow_name}")

    def on_step_start(self, step_name: str, agent_name: str) -> None:
        """步骤开始"""
        if self.verbose:
            print(f"\n  {self.ICONS['running']} [{step_name}] Agent: {agent_name} ...")
        logger.info(f"步骤开始: {step_name} (Agent: {agent_name})")

    def on_step_end(self, result: StepResult) -> None:
        """步骤结束"""
        icon = self.ICONS.get(result.status, "❓")
        if self.verbose:
            print(f"  {icon} [{result.step_name}] 完成 ({result.duration:.1f}s)")
            # 打印输出摘要（截取前 200 字符）
            preview = result.output[:200].replace('\n', ' ')
            if len(result.output) > 200:
                preview += "..."
            print(f"     输出: {preview}")
        logger.info(f"步骤完成: {result.step_name} ({result.duration:.1f}s, {result.status})")

        self._records.append({
            "step": result.step_name,
            "agent": result.agent_name,
            "status": result.status,
            "duration": result.duration,
            "output_length": len(result.output),
            "metadata": result.metadata,
        })

    def on_loop_start(self, round_num: int, max_rounds: int) -> None:
        """循环开始"""
        if self.verbose:
            print(f"\n  {self.ICONS['loop']} 审查-修复循环 第 {round_num}/{max_rounds} 轮")
        logger.info(f"循环开始: 第 {round_num}/{max_rounds} 轮")

    def on_loop_end(self, round_num: int, passed: bool) -> None:
        """循环结束"""
        if self.verbose:
            status = "审查通过 ✅" if passed else "仍有问题，继续修复"
            print(f"  {self.ICONS['loop']} 第 {round_num} 轮结果: {status}")

    def on_workflow_end(self, status: str) -> None:
        """工作流结束"""
        total_time = time.time() - self._workflow_start
        if self.verbose:
            print(f"\n{'='*60}")
            icon = "✅" if status == "completed" else "❌"
            print(f"{icon} 工作流结束: {status} (总耗时: {total_time:.1f}s)")
            print(f"{'='*60}")
        logger.info(f"工作流结束: {status} ({total_time:.1f}s)")

    def get_summary(self) -> str:
        """生成执行摘要报告"""
        total_time = time.time() - self._workflow_start
        lines = [
            "📊 工作流执行摘要",
            "─" * 40,
            f"总耗时: {total_time:.1f}s",
            f"步骤数: {len(self._records)}",
            "",
            "步骤详情:",
        ]
        for i, rec in enumerate(self._records, 1):
            icon = self.ICONS.get(rec["status"], "❓")
            lines.append(
                f"  {i}. {icon} {rec['step']} ({rec['agent']}) "
                f"- {rec['duration']:.1f}s"
            )

        success = sum(1 for r in self._records if r["status"] == "success")
        failed = sum(1 for r in self._records if r["status"] == "failed")
        lines.append("")
        lines.append(f"成功: {success}  失败: {failed}")

        return "\n".join(lines)

    @property
    def records(self) -> List[dict]:
        """获取所有记录"""
        return list(self._records)