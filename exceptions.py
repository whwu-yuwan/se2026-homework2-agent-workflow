"""
异常类层次结构
为工作流引擎和各 Agent 提供分类异常处理
"""


class WorkflowError(Exception):
    """工作流基础异常"""
    pass


class AgentError(WorkflowError):
    """Agent 基础异常"""
    pass


class ToolError(AgentError):
    """工具执行失败"""
    pass


class APIError(AgentError):
    """LLM 调用失败"""
    pass


class ContextError(AgentError):
    """输入过长或上下文错误"""
    pass


class ConfigError(WorkflowError):
    """配置错误"""
    pass


class EngineError(WorkflowError):
    """工作流引擎错误"""
    pass


class StepError(WorkflowError):
    """工作流步骤执行失败"""

    def __init__(self, step_name: str, message: str, original_error: Exception = None):
        self.step_name = step_name
        self.original_error = original_error
        super().__init__(f"[{step_name}] {message}")