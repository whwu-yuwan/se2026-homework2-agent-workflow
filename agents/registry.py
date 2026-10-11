"""
Agent 注册表
提供 Agent 的注册与发现机制，支持通过名称动态创建 Agent 实例
新增 Agent 只需注册即可在工作流中使用，无需修改引擎代码
"""

from typing import Dict, Optional, Type

from agents.base import BaseAgent
from agents.code_agent import CodeAgent
from agents.review_agent import ReviewAgent
from agents.fix_agent import FixAgent


class AgentRegistry:
    """Agent 注册表

    使用示例：
        registry = AgentRegistry()
        agent = registry.create("CodeAgent")
        agent = registry.create("ReviewAgent", system_prompt="自定义提示词")
    """

    def __init__(self):
        self._registry: Dict[str, Type[BaseAgent]] = {}

    def register(self, agent_cls: Type[BaseAgent]) -> None:
        """注册一个 Agent 类"""
        self._registry[agent_cls.name] = agent_cls

    def create(self, name: str, **kwargs) -> BaseAgent:
        """通过名称创建 Agent 实例

        Args:
            name: Agent 名称（如 "CodeAgent"）
            **kwargs: 传递给 Agent 构造函数的参数（如 system_prompt、tools）

        Returns:
            Agent 实例

        Raises:
            KeyError: 未注册的 Agent 名称
        """
        if name not in self._registry:
            available = ", ".join(self._registry.keys())
            raise KeyError(f"未注册的 Agent: '{name}'，可用: {available}")
        return self._registry[name](**kwargs)

    def list_agents(self) -> list:
        """列出所有已注册的 Agent 名称"""
        return list(self._registry.keys())

    def has(self, name: str) -> bool:
        """检查 Agent 是否已注册"""
        return name in self._registry


# 全局默认注册表（预注册所有内置 Agent）
default_registry = AgentRegistry()
default_registry.register(CodeAgent)
default_registry.register(ReviewAgent)
default_registry.register(FixAgent)