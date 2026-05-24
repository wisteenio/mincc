"""示例工具：读取本地文本文件。

作为后续 write / edit / bash / grep / glob 等工具的模板，重点演示：
- 用 @tool 装饰器声明
- 用 docstring 描述工具用途和参数（LLM 会读取 docstring 决定是否调用）
- 入参类型注解，langchain 会据此生成 JSON Schema
- 基本的安全校验（路径存在、大小上限、文本编码）
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

MAX_BYTES = 1024 * 1024  # 1 MiB，避免读到超大文件把上下文塞满


@tool
def read_file(path: str) -> str:
    """读取本地文本文件并返回内容。

    Args:
        path: 文件路径，可为相对路径（基于当前工作目录）或绝对路径。

    Returns:
        文件文本内容；若读取失败则返回以 "ERROR: " 开头的错误说明。
    """
    file_path = Path(path).expanduser()

    if not file_path.exists():
        return f"ERROR: 文件不存在：{file_path}"
    if not file_path.is_file():
        return f"ERROR: 路径不是文件：{file_path}"

    size = file_path.stat().st_size
    if size > MAX_BYTES:
        return f"ERROR: 文件过大（{size} 字节，上限 {MAX_BYTES} 字节）：{file_path}"

    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"ERROR: 文件不是 UTF-8 文本：{file_path}"
