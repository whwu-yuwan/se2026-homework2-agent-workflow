"""
测试配置
提供通用的测试 fixtures，处理 langchain 兼容性问题
"""

import sys
import types
import pytest
from unittest.mock import MagicMock

# ─── langchain 兼容性修复 ─────────────────────────────────────
# langchain-core 的 globals.py 会访问 langchain.verbose / langchain.debug
# 但新版 langchain 包可能没有这些属性，需要提前补上
if "langchain" in sys.modules:
    _lc = sys.modules["langchain"]
    if not hasattr(_lc, "verbose"):
        _lc.verbose = False
    if not hasattr(_lc, "debug"):
        _lc.debug = False
else:
    # 如果 langchain 还没被 import，创建一个假模块占位
    _fake_lc = types.ModuleType("langchain")
    _fake_lc.verbose = False
    _fake_lc.debug = False
    sys.modules["langchain"] = _fake_lc

# ─── 测试环境配置 ─────────────────────────────────────────────
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