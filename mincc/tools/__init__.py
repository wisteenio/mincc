"""工具注册表。

新增工具步骤：
1. 在 tools/ 下新建模块，使用 langchain_core.tools 的 @tool 装饰器导出工具
2. 在本文件 import 该工具并加入 ALL_TOOLS
"""

from langchain_core.tools import BaseTool

from mincc.tools.edit_file import edit_file
from mincc.tools.grep import grep
from mincc.tools.list_files import list_files
from mincc.tools.read_file import read_file
from mincc.tools.run_command import run_command
from mincc.tools.write_file import write_file

ALL_TOOLS: list[BaseTool] = [list_files, grep, read_file, write_file, edit_file, run_command]

__all__ = ["ALL_TOOLS"]
