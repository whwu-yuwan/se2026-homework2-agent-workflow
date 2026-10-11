"""
CLI 测试
测试 main.py 中的命令处理、API Key 检查等功能
"""

import pytest
from unittest.mock import patch, MagicMock

import config
from main import check_api_key, handle_command
from exceptions import ConfigError


class TestCheckApiKey:
    """测试 API Key 检查"""

    def test_api_key_set(self):
        """测试 API Key 已设置时不抛异常"""
        with patch.object(config, "API_KEY", "sk-test-key"):
            check_api_key()  # 不应抛异常

    def test_api_key_empty_raises_error(self):
        """测试 API Key 为空时抛出 ConfigError"""
        with patch.object(config, "API_KEY", ""):
            with pytest.raises(ConfigError, match="未设置"):
                check_api_key()


class TestHandleCommand:
    """测试斜杠命令处理"""

    def test_quit_command(self):
        """测试 /quit 命令"""
        assert handle_command("/quit", [True]) is True
        assert handle_command("/exit", [True]) is True

    def test_help_command(self, capsys):
        """测试 /help 命令"""
        result = handle_command("/help", [True])
        assert result is False
        captured = capsys.readouterr()
        assert "帮助" in captured.out

    def test_verbose_toggle_on(self, capsys):
        """测试 /verbose 切换开启"""
        verbose = [False]
        handle_command("/verbose", verbose)
        assert verbose[0] is True
        captured = capsys.readouterr()
        assert "开启" in captured.out

    def test_verbose_toggle_off(self, capsys):
        """测试 /verbose 切换关闭"""
        verbose = [True]
        handle_command("/verbose", verbose)
        assert verbose[0] is False
        captured = capsys.readouterr()
        assert "关闭" in captured.out

    def test_unknown_command(self, capsys):
        """测试未知命令"""
        result = handle_command("/unknown", [True])
        assert result is False
        captured = capsys.readouterr()
        assert "未知命令" in captured.out

    def test_command_case_insensitive(self, capsys):
        """测试命令大小写不敏感"""
        result = handle_command("/HELP", [True])
        assert result is False
        captured = capsys.readouterr()
        assert "帮助" in captured.out

    def test_command_with_whitespace(self, capsys):
        """测试命令带前后空格"""
        result = handle_command("  /help  ", [True])
        assert result is False