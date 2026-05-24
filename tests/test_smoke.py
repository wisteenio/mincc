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


def test_read_file_tool_smoke(tmp_path, monkeypatch) -> None:
    from mincc.tools.read_file import read_file

    monkeypatch.chdir(tmp_path)
    target = tmp_path / "hello.txt"
    target.write_text("你好 mincc", encoding="utf-8")
    result = read_file.invoke({"path": "hello.txt"})
    assert "你好 mincc" in result


def test_ui_module_importable() -> None:
    """mincc.ui 在 import 阶段不能启动 TUI。"""
    from mincc.ui import run_chat_ui

    assert callable(run_chat_ui)


def test_spinner_text_shows_current_step() -> None:
    from mincc.ui import _spinner_text

    assert _spinner_text("✽", "调用工具：写入文件 a.txt...") == "✽ 调用工具：写入文件 a.txt..."
    assert _spinner_text("✽", "调用模型...", 3) == "✽ 调用模型... (3s · Esc 取消)"


def test_formatted_text_end_position_uses_last_rendered_line() -> None:
    from mincc.ui import _formatted_text_end_position

    position = _formatted_text_end_position([("", "first\n"), ("class:spinner", "second")])

    assert position.x == len("second")
    assert position.y == 1
