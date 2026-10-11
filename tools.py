"""
自定义工具模块
复用 task1 的核心工具，供各 Agent 使用
"""

import os
import re
import sys
import subprocess
from pathlib import Path

from langchain_core.tools import tool

import config
from exceptions import ToolError


def _validate_path(file_path: str) -> Path:
    """校验路径是否在允许的目录范围内"""
    path = Path(file_path).resolve()
    if config.ALLOWED_PATH_PREFIX == "/":
        return path
    allowed_prefix = config.ALLOWED_PATH_PREFIX if config.ALLOWED_PATH_PREFIX is not None else os.getcwd()
    allowed = Path(allowed_prefix).resolve()
    path_str = str(path).lower()
    allowed_str = str(allowed).lower()
    if not (path_str == allowed_str or path_str.startswith(allowed_str + os.sep)):
        raise ToolError(f"路径超出允许范围: {file_path}")
    return path


@tool
def read_file(file_path: str) -> str:
    """读取本地代码文件的内容。
    当你需要查看代码文件、配置文件或任何文本文件时使用此工具。

    Args:
        file_path: 要读取的文件路径（相对路径或绝对路径）
    """
    path = _validate_path(file_path)
    if not path.exists():
        raise ToolError(f"文件不存在: {file_path}")
    if not path.is_file():
        raise ToolError(f"路径不是文件: {file_path}")
    file_size = path.stat().st_size
    if file_size > config.MAX_FILE_READ_BYTES:
        raise ToolError(f"文件过大 ({file_size / 1024:.1f}KB)，超过限制")
    try:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = path.read_text(encoding="gbk")
            except (UnicodeDecodeError, LookupError):
                content = path.read_text(encoding="latin-1")
    except PermissionError:
        raise ToolError(f"没有权限读取文件: {file_path}")
    except OSError as e:
        raise ToolError(f"读取文件失败: {e}")
    return content


@tool
def list_directory(dir_path: str) -> str:
    """列出目录中的文件和子目录。
    当你需要了解项目结构或查找文件时使用此工具。

    Args:
        dir_path: 要列出的目录路径（相对路径或绝对路径）
    """
    path = _validate_path(dir_path)
    if not path.exists():
        raise ToolError(f"目录不存在: {dir_path}")
    if not path.is_dir():
        raise ToolError(f"路径不是目录: {dir_path}")
    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        raise ToolError(f"没有权限访问目录: {dir_path}")
    if not entries:
        return "(空目录)"
    lines = []
    for entry in entries:
        if entry.is_dir():
            lines.append(f"[目录] {entry.name}/")
        else:
            size = entry.stat().st_size
            size_str = f"{size / 1024:.1f}KB" if size >= 1024 else f"{size}B"
            lines.append(f"[文件] {entry.name}  ({size_str})")
    return "\n".join(lines)


@tool
def execute_python(code: str) -> str:
    """执行 Python 代码并返回输出。
    当你需要运行代码片段、验证逻辑或测试代码时使用此工具。

    Args:
        code: 要执行的 Python 代码
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=config.CODE_EXECUTION_TIMEOUT,
            cwd=os.getcwd()
        )
    except subprocess.TimeoutExpired:
        raise ToolError(f"代码执行超时（超过 {config.CODE_EXECUTION_TIMEOUT} 秒）")
    except Exception as e:
        raise ToolError(f"执行失败: {e}")
    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        if output:
            output += "\n--- stderr ---\n"
        output += result.stderr
    return output if output else "(无输出)"


@tool
def search_code(keyword: str, dir_path: str = ".", file_pattern: str = "**/*.py") -> str:
    """在代码文件中搜索关键词或正则表达式（递归搜索子目录）。
    当你需要查找某个函数、变量或代码片段的位置时使用此工具。

    Args:
        keyword: 要搜索的关键词或正则表达式
        dir_path: 搜索的目录路径（默认当前目录）
        file_pattern: 文件匹配模式（默认 **/*.py）
    """
    path = _validate_path(dir_path)
    if not path.exists():
        raise ToolError(f"目录不存在: {dir_path}")
    if not path.is_dir():
        raise ToolError(f"路径不是目录: {dir_path}")
    try:
        pattern = re.compile(keyword)
    except re.error:
        pattern = re.compile(re.escape(keyword))
    if ".." in file_pattern:
        raise ToolError(f"文件模式不允许包含 '..'")
    results = []
    match_count = 0
    try:
        for file_path in path.glob(file_pattern):
            if not file_path.is_file():
                continue
            try:
                _validate_path(str(file_path))
            except ToolError:
                continue
            if file_path.stat().st_size > config.MAX_FILE_READ_BYTES:
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            for line_num, line in enumerate(content.splitlines(), 1):
                if pattern.search(line):
                    match_count += 1
                    try:
                        rel_path = file_path.relative_to(Path.cwd())
                    except ValueError:
                        rel_path = file_path
                    results.append(f"{rel_path}:{line_num}: {line.strip()}")
                    if match_count >= config.MAX_SEARCH_RESULTS:
                        return f"共找到 {match_count}+ 处匹配（已截断）:\n" + "\n".join(results)
    except Exception as e:
        raise ToolError(f"搜索失败: {e}")
    if not results:
        return f"未找到匹配 '{keyword}' 的结果"
    return f"共找到 {match_count} 处匹配:\n" + "\n".join(results)


# 工具列表
CODE_TOOLS = [read_file, list_directory, execute_python, search_code]
READ_TOOLS = [read_file, list_directory, search_code]