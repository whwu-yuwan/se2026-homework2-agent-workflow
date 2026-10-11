"""
日志配置模块
提供统一的日志初始化，支持文件日志和控制台日志
"""

import logging
from pathlib import Path


def setup_logging(
    log_file: str = "logs/workflow.log",
    console_level: int = logging.WARNING,
    file_level: int = logging.DEBUG
) -> None:
    """配置全局日志

    Args:
        log_file: 日志文件路径
        console_level: 控制台日志级别
        file_level: 文件日志级别
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 清除已有的 handler（防止重复添加）
    root_logger.handlers.clear()

    # 日志格式
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件 handler
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)