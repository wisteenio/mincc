"""工具注册表。

新增工具步骤：
1. 在 tools/ 下新建模块，使用 langchain_core.tools 的 @tool 装饰器导出工具
2. 在本文件 import 该工具并加入 ALL_TOOLS
"""

from langchain_core.tools import BaseTool

from mincc.tools.read_file import read_file

ALL_TOOLS: list[BaseTool] = [read_file]

__all__ = ["ALL_TOOLS"]
