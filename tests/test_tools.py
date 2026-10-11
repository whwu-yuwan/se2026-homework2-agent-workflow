"""
工具测试
测试 read_file, list_directory, execute_python, search_code 四个工具
以及 _validate_path 路径校验函数
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

import config
from tools import read_file, list_directory, execute_python, search_code, _validate_path
from exceptions import ToolError


# ─── _validate_path 路径校验 ─────────────────────────────────


class TestValidatePath:
    """测试路径校验函数"""

    def test_valid_path_in_cwd(self, tmp_path):
        """测试工作目录内的路径通过校验"""
        test_file = tmp_path / "test.py"
        test_file.write_text("hello")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = _validate_path(str(test_file))
            assert result.exists()

    def test_path_outside_allowed_raises_error(self, tmp_path):
        """测试超出允许范围的路径抛出 ToolError"""
        outside = Path("C:\\Windows\\System32\\notepad.exe")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            with pytest.raises(ToolError, match="路径超出允许范围"):
                _validate_path(str(outside))

    def test_allow_all_paths_with_slash(self):
        """测试 '/' 表示允许所有路径"""
        result = _validate_path("C:\\")
        assert result is not None

    def test_none_prefix_uses_cwd(self):
        """测试 None 前缀使用当前工作目录"""
        with patch("config.ALLOWED_PATH_PREFIX", None):
            # 当前目录下的文件应该通过
            result = _validate_path(".")
            assert result is not None


# ─── read_file 工具 ──────────────────────────────────────────


class TestReadFile:
    """测试文件读取工具"""

    def test_read_existing_file(self, tmp_path):
        """测试读取已存在的文件"""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')", encoding="utf-8")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = read_file.invoke({"file_path": str(test_file)})
        assert "print('hello')" in result

    def test_read_nonexistent_file_raises_error(self, tmp_path):
        """测试读取不存在的文件抛出 ToolError"""
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            with pytest.raises(ToolError, match="文件不存在"):
                read_file.invoke({"file_path": str(tmp_path / "nope.py")})

    def test_read_directory_raises_error(self, tmp_path):
        """测试读取目录（非文件）抛出 ToolError"""
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            with pytest.raises(ToolError, match="路径不是文件"):
                read_file.invoke({"file_path": str(tmp_path)})

    def test_read_large_file_raises_error(self, tmp_path):
        """测试读取超大文件抛出 ToolError"""
        big_file = tmp_path / "big.py"
        big_file.write_text("x" * (config.MAX_FILE_READ_BYTES + 1))
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            with pytest.raises(ToolError, match="文件过大"):
                read_file.invoke({"file_path": str(big_file)})

    def test_read_gbk_file(self, tmp_path):
        """测试读取 GBK 编码文件"""
        gbk_file = tmp_path / "gbk.py"
        gbk_file.write_text("中文内容", encoding="gbk")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = read_file.invoke({"file_path": str(gbk_file)})
        assert "中文内容" in result

    def test_read_empty_file(self, tmp_path):
        """测试读取空文件"""
        empty = tmp_path / "empty.py"
        empty.write_text("")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = read_file.invoke({"file_path": str(empty)})
        assert result == ""


# ─── list_directory 工具 ─────────────────────────────────────


class TestListDirectory:
    """测试目录列表工具"""

    def test_list_directory_with_files(self, tmp_path):
        """测试列出有文件的目录"""
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.py").write_text("b")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = list_directory.invoke({"dir_path": str(tmp_path)})
        assert "a.py" in result
        assert "b.py" in result

    def test_list_directory_with_subdirs(self, tmp_path):
        """测试列出包含子目录的目录"""
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.py").write_text("x")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = list_directory.invoke({"dir_path": str(tmp_path)})
        assert "[目录] subdir/" in result
        assert "[文件] file.py" in result

    def test_list_empty_directory(self, tmp_path):
        """测试列出空目录"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = list_directory.invoke({"dir_path": str(empty_dir)})
        assert "(空目录)" in result

    def test_list_nonexistent_raises_error(self, tmp_path):
        """测试列出不存在的目录抛出 ToolError"""
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            with pytest.raises(ToolError, match="目录不存在"):
                list_directory.invoke({"dir_path": str(tmp_path / "nope")})

    def test_list_file_raises_error(self, tmp_path):
        """测试对文件调用 list_directory 抛出 ToolError"""
        f = tmp_path / "file.py"
        f.write_text("x")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            with pytest.raises(ToolError, match="路径不是目录"):
                list_directory.invoke({"dir_path": str(f)})

    def test_file_size_display(self, tmp_path):
        """测试文件大小显示格式"""
        small = tmp_path / "small.txt"
        small.write_text("x" * 500)  # 500B
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = list_directory.invoke({"dir_path": str(tmp_path)})
        assert "500B" in result

    def test_file_size_kb_display(self, tmp_path):
        """测试 KB 级别文件大小显示"""
        medium = tmp_path / "medium.txt"
        medium.write_text("x" * 2048)  # 2KB
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = list_directory.invoke({"dir_path": str(tmp_path)})
        assert "2.0KB" in result


# ─── execute_python 工具 ─────────────────────────────────────


class TestExecutePython:
    """测试代码执行工具"""

    def test_execute_simple_code(self):
        """测试执行简单代码"""
        result = execute_python.invoke({"code": "print(1 + 2)"})
        assert "3" in result

    def test_execute_code_with_output(self):
        """测试代码输出"""
        result = execute_python.invoke({"code": "print('hello world')"})
        assert "hello world" in result

    def test_execute_code_no_output(self):
        """测试无输出代码"""
        result = execute_python.invoke({"code": "x = 1"})
        assert "(无输出)" in result

    def test_execute_code_with_stderr(self):
        """测试有 stderr 输出的代码"""
        result = execute_python.invoke({
            "code": "import sys; sys.stderr.write('warning\\n')"
        })
        assert "warning" in result

    def test_execute_code_syntax_error(self):
        """测试语法错误代码"""
        result = execute_python.invoke({"code": "def ("})
        # 应该有 stderr 输出（语法错误）
        assert len(result) > 0

    def test_execute_code_runtime_error(self):
        """测试运行时错误代码"""
        result = execute_python.invoke({"code": "1/0"})
        assert "ZeroDivisionError" in result or "division by zero" in result

    def test_execute_timeout(self):
        """测试代码执行超时"""
        # langchain invoke 会重新 raise ToolError，需要捕获
        with pytest.raises(ToolError, match="超时"):
            execute_python.invoke({
                "code": "import time; time.sleep(30)"
            })


# ─── search_code 工具 ────────────────────────────────────────


class TestSearchCode:
    """测试代码搜索工具"""

    def test_search_found(self, tmp_path):
        """测试搜索到匹配"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = search_code.invoke({
                "keyword": "hello",
                "dir_path": str(tmp_path),
                "file_pattern": "*.py"
            })
        assert "hello" in result
        assert "处匹配" in result

    def test_search_not_found(self, tmp_path):
        """测试搜索无匹配"""
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = search_code.invoke({
                "keyword": "nonexistent_xyz",
                "dir_path": str(tmp_path),
                "file_pattern": "*.py"
            })
        assert "未找到匹配" in result

    def test_search_regex(self, tmp_path):
        """测试正则搜索"""
        test_file = tmp_path / "test.py"
        test_file.write_text("foo123\nbar456\nfoo789\n")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = search_code.invoke({
                "keyword": r"foo\d+",
                "dir_path": str(tmp_path),
                "file_pattern": "*.py"
            })
        assert "foo123" in result
        assert "foo789" in result

    def test_search_invalid_regex_fallback(self, tmp_path):
        """测试无效正则回退到字面匹配"""
        test_file = tmp_path / "test.py"
        test_file.write_text("a.b.c\n")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = search_code.invoke({
                "keyword": "a.b.c",
                "dir_path": str(tmp_path),
                "file_pattern": "*.py"
            })
        assert "a.b.c" in result

    def test_search_nonexistent_dir_raises_error(self, tmp_path):
        """测试搜索不存在的目录抛出 ToolError"""
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            with pytest.raises(ToolError, match="目录不存在"):
                search_code.invoke({
                    "keyword": "test",
                    "dir_path": str(tmp_path / "nope"),
                })

    def test_search_file_dir_raises_error(self, tmp_path):
        """测试对文件调用搜索抛出 ToolError"""
        f = tmp_path / "file.py"
        f.write_text("x")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            with pytest.raises(ToolError, match="路径不是目录"):
                search_code.invoke({
                    "keyword": "x",
                    "dir_path": str(f),
                })

    def test_search_recursive(self, tmp_path):
        """测试递归搜索子目录"""
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("recursive_search_test\n")
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = search_code.invoke({
                "keyword": "recursive_search_test",
                "dir_path": str(tmp_path),
                "file_pattern": "**/*.py"
            })
        assert "recursive_search_test" in result

    def test_search_max_results(self, tmp_path):
        """测试搜索结果数量限制"""
        test_file = tmp_path / "test.py"
        # 写入超过 MAX_SEARCH_RESULTS 行匹配
        test_file.write_text("\n".join(["match_line"] * (config.MAX_SEARCH_RESULTS + 10)))
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            result = search_code.invoke({
                "keyword": "match_line",
                "dir_path": str(tmp_path),
                "file_pattern": "*.py"
            })
        assert "截断" in result

    def test_search_with_dotdot_pattern_raises_error(self, tmp_path):
        """测试包含 .. 的文件模式抛出 ToolError"""
        with patch("config.ALLOWED_PATH_PREFIX", str(tmp_path)):
            with pytest.raises(ToolError, match="不允许包含"):
                search_code.invoke({
                    "keyword": "test",
                    "dir_path": str(tmp_path),
                    "file_pattern": "../**/*.py",
                })