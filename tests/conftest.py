"""
测试配置
提供通用的测试 fixtures
"""

import pytest
from unittest.mock import MagicMock

# 设置允许所有路径（测试环境）
import config
config.ALLOWED_PATH_PREFIX = "/"
config.API_KEY = "test-key"


@pytest.fixture
def mock_llm_response():
    """创建一个模拟的 LLM 响应"""
    def _make_response(content="test response", tool_calls=None):
        response = MagicMock()
        response.content = content
        response.tool_calls = tool_calls or []
        response.usage_metadata = {"total_tokens": 100}
        return response
    return _make_response