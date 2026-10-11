"""
工作流上下文（共享状态）
通用键值存储 + 状态追踪。
业务属性（如 code、review_result）在各工作流中通过 get()/set() 存取，
此处不定义任何业务特定属性。
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StepResult:
    """单步执行结果"""
    step_name: str
    agent_name: str
    status: str
    output: str
    duration: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorkflowContext:
    """工作流上下文（通用键值存储 + 状态追踪）

    所有业务数据通过 get(key)/set(key, value) 存取。
    不定义业务特定属性，保持引擎和上下文的通用性。
    """

    def __init__(self, initial_data: Optional[Dict[str, Any]] = None):
        self._data: Dict[str, Any] = initial_data or {}
        self._step_results: List[StepResult] = []
        self._start_time = time.time()
        self._status = "pending"

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def update(self, data: Dict[str, Any]) -> None:
        self._data.update(data)

    def has(self, key: str) -> bool:
        return key in self._data

    @property
    def data(self) -> Dict[str, Any]:
        return dict(self._data)

    def add_step_result(self, result: StepResult) -> None:
        self._step_results.append(result)

    @property
    def step_results(self) -> List[StepResult]:
        return list(self._step_results)

    @property
    def last_step(self) -> Optional[StepResult]:
        return self._step_results[-1] if self._step_results else None

    @property
    def status(self) -> str:
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        self._status = value

    @property
    def elapsed(self) -> float:
        return time.time() - self._start_time

    def __repr__(self) -> str:
        return (
            f"WorkflowContext(status={self._status}, "
            f"steps={len(self._step_results)}, "
            f"keys={list(self._data.keys())}, "
            f"elapsed={self.elapsed:.1f}s)"
        )