"""冒烟测试：能 import、工具注册表非空。

不调用真实 API，避免网络与密钥依赖。create_react_agent 内部会 bind_tools，
而 FakeListChatModel 不一定支持，所以这里只做静态层面的冒烟验证。
"""

from langchain_core.tools import BaseTool

import mincc
from mincc.tools import ALL_TOOLS


def test_import_package() -> None:
    assert mincc.__version__


def test_tools_registered() -> None:
    assert len(ALL_TOOLS) >= 1
    assert all(isinstance(t, BaseTool) for t in ALL_TOOLS)


def test_read_file_tool_smoke(tmp_path) -> None:
    from mincc.tools.read_file import read_file

    target = tmp_path / "hello.txt"
    target.write_text("你好 mincc", encoding="utf-8")
    result = read_file.invoke({"path": str(target)})
    assert "你好 mincc" in result


def test_ui_module_importable() -> None:
    """mincc.ui 在 import 阶段不能启动 TUI。"""
    from mincc.ui import run_chat_ui

    assert callable(run_chat_ui)
