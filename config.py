"""
配置常量模块
包含 API 地址、模型名称、Agent 配置、工作流配置等
"""

import os

# DeepSeek API 配置
API_BASE_URL = "https://api.deepseek.com"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MODEL_NAME = "deepseek-chat"

# LLM 参数
TEMPERATURE = 0.3
MAX_TOKENS = 4096

# 上下文管理
MAX_CONTEXT_TOKENS = 64000
MAX_OUTPUT_TOKENS = 4096
TOOL_RESULT_RESERVE_TOKENS = 8000
TRIM_THRESHOLD_TOKENS = MAX_CONTEXT_TOKENS - MAX_OUTPUT_TOKENS - TOOL_RESULT_RESERVE_TOKENS

# Agent 配置
MAX_TOOL_CALLS_PER_TURN = 10
MAX_FILE_READ_BYTES = 200_000       # 200KB
MAX_TOOL_RESULT_TOKENS = 4000
MAX_SEARCH_RESULTS = 50
CODE_EXECUTION_TIMEOUT = 10         # 秒
MAX_INPUT_TOKEN_RATIO = 0.5
MIN_MESSAGES_TO_KEEP = 2

# 截断策略
TRUNCATE_HEAD_RATIO = 0.7
ARGS_PREVIEW_LENGTH = 200

# 安全：文件操作限制（None = 延迟求值到 os.getcwd()，"/" = 允许所有路径）
ALLOWED_PATH_PREFIX = None

# 工作流配置
MAX_REVIEW_ROUNDS = 3               # 审查-修复 最大循环轮次
REVIEW_PASS_THRESHOLD = "low"       # 审查通过阈值: 无 low/critical 问题即通过

# 日志配置
LOG_FILE = "logs/workflow.log"
LOG_CONSOLE_LEVEL = 30              # WARNING
LOG_FILE_LEVEL = 10                 # DEBUG