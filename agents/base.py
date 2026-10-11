"""
Agent 基类
封装 LLM 调用、消息管理、上下文裁剪、工具执行等通用逻辑
各具体 Agent 继承此类，只需关注 system prompt 和工具定义
"""

import logging
from typing import List, Tuple, Optional, Union

import tiktoken
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import BaseTool

import config
from exceptions import AgentError, ToolError, APIError, ContextError

logger = logging.getLogger(__name__)


class BaseAgent:
    """Agent 基类

    子类需实现:
    - name: Agent 名称
    - system_prompt: 系统提示词
    - tools: 工具列表（可为空）
    """

    name: str = "base"
    default_system_prompt: str = ""
    default_tools: List[BaseTool] = []

    def __init__(self, system_prompt: Optional[str] = None, tools: Optional[List[BaseTool]] = None):
        """初始化 Agent

        Args:
            system_prompt: 自定义系统提示词（None 则使用类默认值）
            tools: 自定义工具列表（None 则使用类默认值）
        """
        self.system_prompt = system_prompt if system_prompt is not None else self.default_system_prompt
        self.tools = tools if tools is not None else self.default_tools

        self.llm = ChatOpenAI(
            model=config.MODEL_NAME,
            openai_api_key=config.API_KEY,
            openai_api_base=config.API_BASE_URL,
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
            max_retries=2,
            timeout=30,
        )

        # 绑定工具到 LLM（如果有工具）
        if self.tools:
            self.llm_with_tools = self.llm.bind_tools(self.tools)
            self.tool_map = {tool.name: tool for tool in self.tools}
        else:
            self.llm_with_tools = self.llm
            self.tool_map = {}

        # 对话历史
        self.messages: List[Union[SystemMessage, HumanMessage, AIMessage, ToolMessage]] = [
            SystemMessage(content=self.system_prompt)
        ]

        # Token 统计
        self.total_tokens_used = 0

        # tiktoken 编码器
        self._encoding = tiktoken.get_encoding("cl100k_base")

        logger.info(f"[{self.name}] Agent 初始化完成")

    # ─── Token 管理 ────────────────────────────────────────────

    def _estimate_tokens(self) -> int:
        """估算当前对话历史的 token 数量"""
        total = 0
        for msg in self.messages:
            content = msg.content if msg.content else ""
            total += len(self._encoding.encode(content))
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    total += len(self._encoding.encode(str(tc)))
        return total

    def _estimate_msg_tokens(self, msg) -> int:
        """估算单条消息的 token 数量"""
        tokens = len(self._encoding.encode(msg.content or ""))
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tc in msg.tool_calls:
                tokens += len(self._encoding.encode(str(tc)))
        return tokens

    def _update_token_stats(self, response: AIMessage) -> None:
        """更新 token 使用统计"""
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            tokens = response.usage_metadata.get('total_tokens', 0)
            self.total_tokens_used += tokens

    def _truncate_tool_result(self, result: str) -> str:
        """截断过长的工具结果"""
        tokens = len(self._encoding.encode(result))
        if tokens <= config.MAX_TOOL_RESULT_TOKENS:
            return result

        keep_ratio = config.MAX_TOOL_RESULT_TOKENS / tokens
        keep_chars = int(len(result) * keep_ratio * 0.9)
        head_chars = int(keep_chars * config.TRUNCATE_HEAD_RATIO)
        tail_chars = keep_chars - head_chars

        notice = f"\n\n... [结果过长，已截断（原始约 {tokens} tokens）] ...\n\n"
        return result[:head_chars] + notice + result[-tail_chars:]

    # ─── 上下文裁剪 ────────────────────────────────────────────

    def _find_removable_group(self, protect_start: int = 0) -> Optional[Tuple[int, int]]:
        """找到第一个可安全删除的消息组"""
        idx = 1  # 跳过 system message
        while idx < len(self.messages):
            msg = self.messages[idx]
            if isinstance(msg, HumanMessage):
                start = idx
                end = idx + 1
                while end < len(self.messages) and not isinstance(self.messages[end], HumanMessage):
                    end += 1
                if start >= protect_start:
                    return None
                return (start, end)
            elif isinstance(msg, (ToolMessage, AIMessage)):
                start = idx
                end = idx + 1
                while end < len(self.messages) and isinstance(self.messages[end], (ToolMessage, AIMessage)):
                    end += 1
                if start >= protect_start:
                    return None
                return (start, end)
            else:
                idx += 1
        return None

    def _trim_context(self) -> None:
        """裁剪对话历史，确保不超过 token 限制"""
        current_tokens = self._estimate_tokens()
        if current_tokens <= config.TRIM_THRESHOLD_TOKENS:
            return

        logger.info(f"[{self.name}] 上下文裁剪: {current_tokens} tokens")

        while current_tokens > config.TRIM_THRESHOLD_TOKENS and len(self.messages) > config.MIN_MESSAGES_TO_KEEP:
            protect_start = 0
            for i in range(len(self.messages) - 1, 0, -1):
                if isinstance(self.messages[i], HumanMessage):
                    protect_start = i
                    break

            group = self._find_removable_group(protect_start=protect_start)
            if group is None:
                break
            start, end = group
            for i in range(end - 1, start - 1, -1):
                current_tokens -= self._estimate_msg_tokens(self.messages[i])
                self.messages.pop(i)

        logger.info(f"[{self.name}] 裁剪完成: 剩余 {len(self.messages)} 条消息")

    # ─── 工具执行 ──────────────────────────────────────────────

    def _execute_tool_calls(self, tool_calls: list, callbacks: list) -> None:
        """执行工具调用并将结果追加到 messages"""
        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            try:
                tool_func = self.tool_map.get(tool_name)
                if not tool_func:
                    raise ToolError(f"未知工具: {tool_name}")
                result = tool_func.invoke(
                    tool_args,
                    config={"callbacks": callbacks}
                )
            except ToolError as e:
                result = f"[工具错误] {e}"
            except Exception as e:
                logger.error(f"[{self.name}] 工具 '{tool_name}' 异常: {e}")
                result = f"[工具执行异常] {tool_name}: {e}"

            result_str = self._truncate_tool_result(str(result))
            self.messages.append(
                ToolMessage(content=result_str, tool_call_id=tool_id)
            )

        self._trim_context()

    # ─── 核心调用 ──────────────────────────────────────────────

    def _force_final_response(self, callbacks: list) -> str:
        """强制生成最终回复（不带 tools）"""
        response = self.llm.invoke(self.messages, config={"callbacks": callbacks})
        self._update_token_stats(response)
        if not response.content or not response.content.strip():
            fallback = "（Agent 未生成有效回复）"
            self.messages.append(AIMessage(content=fallback))
            return fallback
        self.messages.append(response)
        return response.content

    def run(self, user_input: str) -> str:
        """处理用户输入，执行 Agent 循环

        Args:
            user_input: 用户输入文本

        Returns:
            Agent 的回复文本

        Raises:
            ContextError: 输入过长
            APIError: LLM 调用失败
        """
        input_tokens = len(self._encoding.encode(user_input))
        if input_tokens > config.MAX_CONTEXT_TOKENS * config.MAX_INPUT_TOKEN_RATIO:
            raise ContextError(f"[{self.name}] 输入过长（约 {input_tokens} tokens）")

        pre_input_len = len(self.messages)
        pre_tokens = self.total_tokens_used

        self.messages.append(HumanMessage(content=user_input))
        self._trim_context()

        callbacks = []
        snapshot_len = len(self.messages)
        max_iters = config.MAX_TOOL_CALLS_PER_TURN

        for iteration in range(max_iters):
            try:
                response = self.llm_with_tools.invoke(
                    self.messages,
                    config={"callbacks": callbacks}
                )
                self._update_token_stats(response)

                if response.tool_calls:
                    self.messages.append(response)
                    self._execute_tool_calls(response.tool_calls, callbacks)

                    if iteration == max_iters - 1:
                        logger.warning(f"[{self.name}] 工具调用轮次耗尽")
                        break
                    continue
                else:
                    if not response.content or not response.content.strip():
                        fallback = "（Agent 未生成有效回复）"
                        self.messages.append(AIMessage(content=fallback))
                        return fallback
                    self.messages.append(response)
                    return response.content

            except AgentError:
                raise
            except Exception as e:
                del self.messages[pre_input_len:]
                self.total_tokens_used = pre_tokens
                logger.error(f"[{self.name}] 执行出错: {e}")
                raise APIError(f"[{self.name}] 执行失败: {e}")

        # 轮次耗尽：强制回复
        try:
            return self._force_final_response(callbacks)
        except Exception:
            del self.messages[snapshot_len:]
            fallback = "抱歉，处理过程过于复杂，请简化问题后重试。"
            self.messages.append(AIMessage(content=fallback))
            return fallback

    def reset(self) -> None:
        """重置对话历史"""
        self.messages = [SystemMessage(content=self.system_prompt)]
        self.total_tokens_used = 0
        logger.info(f"[{self.name}] 对话历史已重置")

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def get_summary(self) -> str:
        """获取对话摘要"""
        user_msgs = sum(1 for m in self.messages if isinstance(m, HumanMessage))
        ai_msgs = sum(1 for m in self.messages if isinstance(m, AIMessage))
        tool_calls = sum(1 for m in self.messages if isinstance(m, ToolMessage))
        return (
            f"[{self.name}] 消息: {len(self.messages)} "
            f"(用户:{user_msgs} AI:{ai_msgs} 工具:{tool_calls}) "
            f"Token: {self.total_tokens_used}"
        )