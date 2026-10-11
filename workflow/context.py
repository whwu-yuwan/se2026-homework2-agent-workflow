"""
工作流上下文（共享状态）
在各 Agent 之间传递数据，记录工作流执行过程中的所有中间结果
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StepResult:
    """单步执行结果"""
    step_name: str
    agent_name: str
    status: str                    # "success" | "failed" | "skipped"
    output: str                    # Agent 输出文本
    duration: float                # 执行耗时（秒）
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorkflowContext:
    """工作流上下文

    在各 Agent 之间共享状态，支持：
    - 存取任意键值对数据
    - 记录每步执行结果
    - 追踪工作流状态
    """

    def __init__(self, initial_data: Optional[Dict[str, Any]] = None):
        """初始化上下文

        Args:
            initial_data: 初始数据（如用户输入的代码、文件路径等）
        """
        self._data: Dict[str, Any] = initial_data or {}
        self._step_results: List[StepResult] = []
        self._start_time = time.time()
        self._status = "pending"     # pending | running | completed | failed

    # ─── 数据存取 ──────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """获取上下文数据"""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置上下文数据"""
        self._data[key] = value

    def update(self, data: Dict[str, Any]) -> None:
        """批量更新上下文数据"""
        self._data.update(data)

    def has(self, key: str) -> bool:
        """检查键是否存在"""
        return key in self._data

    @property
    def data(self) -> Dict[str, Any]:
        """获取所有数据（只读副本）"""
        return dict(self._data)

    # ─── 步骤结果记录 ──────────────────────────────────────────

    def add_step_result(self, result: StepResult) -> None:
        """记录一步的执行结果"""
        self._step_results.append(result)

    @property
    def step_results(self) -> List[StepResult]:
        """获取所有步骤结果"""
        return list(self._step_results)

    @property
    def last_step(self) -> Optional[StepResult]:
        """获取最后一步结果"""
        return self._step_results[-1] if self._step_results else None

    # ─── 状态管理 ──────────────────────────────────────────────

    @property
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        self._status = value

    @property
    def elapsed(self) -> float:
        """工作流已运行时间（秒）"""
        return time.time() - self._start_time

    # ─── 便捷属性（代码审查工作流专用）─────────────────────────

    @property
    def code(self) -> Optional[str]:
        """获取当前代码"""
        return self.get("code")

    @code.setter
    def code(self, value: str) -> None:
        self.set("code", value)

    @property
    def review_result(self) -> Optional[str]:
        """获取审查结果"""
        return self.get("review_result")

    @review_result.setter
    def review_result(self, value: str) -> None:
        self.set("review_result", value)

    @property
    def review_round(self) -> int:
        """当前审查轮次"""
        return self.get("review_round", 0)

    @review_round.setter
    def review_round(self, value: int) -> None:
        self.set("review_round", value)

    @property
    def has_critical_issues(self) -> bool:
        """审查是否发现严重问题"""
        return self.get("has_critical_issues", False)

    @has_critical_issues.setter
    def has_critical_issues(self, value: bool) -> None:
        self.set("has_critical_issues", value)

    def __repr__(self) -> str:
        return (
            f"WorkflowContext(status={self._status}, "
            f"steps={len(self._step_results)}, "
            f"keys={list(self._data.keys())}, "
            f"elapsed={self.elapsed:.1f}s)"
        )