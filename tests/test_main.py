"""
CLI 测试
测试 main.py 中的命令处理、API Key 检查等功能
"""

import pytest
from unittest.mock import patch, MagicMock

import config
from main import check_api_key, handle_command, WORKFLOWS
from exceptions import ConfigError


class TestCheckApiKey:
    """测试 API Key 检查"""

    def test_api_key_set(self):
        with patch.object(config, "API_KEY", "sk-test-key"):
            check_api_key()

    def test_api_key_empty_raises_error(self):
        with patch.object(config, "API_KEY", ""):
            with pytest.raises(ConfigError, match="未设置"):
                check_api_key()


def _make_state(**overrides):
    """创建默认 state 字典"""
    state = {"verbose": True, "workflow": "1"}
    state.update(overrides)
    return state


class TestHandleCommand:
    """测试斜杠命令处理"""

    def test_quit_command(self):
        assert handle_command("/quit", _make_state()) is True
        assert handle_command("/exit", _make_state()) is True

    def test_help_command(self, capsys):
        result = handle_command("/help", _make_state())
        assert result is False
        assert "帮助" in capsys.readouterr().out

    def test_verbose_toggle_on(self, capsys):
        state = _make_state(verbose=False)
        handle_command("/verbose", state)
        assert state["verbose"] is True
        assert "开启" in capsys.readouterr().out

    def test_verbose_toggle_off(self, capsys):
        state = _make_state(verbose=True)
        handle_command("/verbose", state)
        assert state["verbose"] is False
        assert "关闭" in capsys.readouterr().out

    def test_unknown_command(self, capsys):
        result = handle_command("/unknown", _make_state())
        assert result is False
        assert "未知命令" in capsys.readouterr().out

    def test_command_case_insensitive(self, capsys):
        result = handle_command("/HELP", _make_state())
        assert result is False
        assert "帮助" in capsys.readouterr().out

    def test_command_with_whitespace(self, capsys):
        result = handle_command("  /help  ", _make_state())
        assert result is False

    def test_agents_command(self, capsys):
        result = handle_command("/agents", _make_state())
        assert result is False
        out = capsys.readouterr().out
        assert "CodeAgent" in out
        assert "ReviewAgent" in out
        assert "FixAgent" in out

    def test_verbose_toggle_in_state(self):
        state = _make_state(verbose=False)
        handle_command("/verbose", state)
        assert state["verbose"] is True
        handle_command("/verbose", state)
        assert state["verbose"] is False


class TestWorkflowsConfig:
    """测试工作流配置"""

    def test_workflows_has_two_entries(self):
        assert len(WORKFLOWS) == 2
        assert "1" in WORKFLOWS
        assert "2" in WORKFLOWS

    def test_workflow_names(self):
        assert WORKFLOWS["1"][0] == "代码审查"
        assert WORKFLOWS["2"][0] == "文档生成"