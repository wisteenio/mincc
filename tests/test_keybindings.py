"""按键绑定回归测试。

历史教训：换行绑定改了三次都"以为修好了"但没真正验证。这个测试用
prompt_toolkit 自身的 API（Vt100Parser / KeyBindings.get_bindings_for_keys）
直接断言"原始字节 -> KeyPress 序列 -> 命中的 handler"链路，不依赖真
实终端，能在 CI 里跑。
"""

from __future__ import annotations

from prompt_toolkit.input.vt100_parser import Vt100Parser
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPress
from prompt_toolkit.keys import Keys

from mincc.ui import (
    TERMINAL_KEY_REPORTING_DISABLE,
    TERMINAL_KEY_REPORTING_ENABLE,
    XTERM_MODIFIED_SHIFT_ENTER,
    _previous_key_was_escape,
    _write_terminal_sequence,
)


def _bytes_to_keys(data: str) -> tuple[Keys | str, ...]:
    """把原始终端字节流喂给 vt100 parser，返回得到的 KeyPress.key 序列。

    feed_and_flush 模拟"终端把这串字节一口气送过来后空闲了"，与真实
    Alt+Enter 的输入到达模式一致。
    """
    presses: list[KeyPress] = []
    parser = Vt100Parser(presses.append)
    parser.feed_and_flush(data)
    return tuple(p.key for p in presses)


def _build_ui_bindings() -> tuple[KeyBindings, dict[str, list[str]]]:
    """复刻 ui.py 中输入相关的绑定，返回 KeyBindings 和命中记录字典。

    只复刻"Enter / 换行"相关的绑定，不引入 TextArea / Application，
    保持测试独立、可在 CI 跑。
    """
    kb = KeyBindings()
    hits: dict[str, list[str]] = {"newline": [], "submit": []}

    @kb.add("escape", "enter")
    @kb.add("escape", "c-j")
    @kb.add("escape", "[", "1", "3", ";", "2", "u")
    @kb.add("escape", "[", "1", "3", ";", "3", "u")
    @kb.add("escape", "[", "1", "3", ";", "4", "u")
    @kb.add("escape", "[", "2", "7", ";", "3", ";", "1", "3", "~")
    @kb.add("escape", "[", "2", "7", ";", "4", ";", "1", "3", "~")
    @kb.add("c-j")
    def _newline(event):  # noqa: ARG001
        hits["newline"].append("hit")

    @kb.add("enter")
    def _submit(event):  # noqa: ARG001
        hits["submit"].append("hit")

    return kb, hits


def test_vt100_parser_alt_enter_cr() -> None:
    """Alt+Enter (ESC+CR) 应被解析成 (Escape, ControlM)。"""
    assert _bytes_to_keys("\x1b\r") == (Keys.Escape, Keys.ControlM)


def test_vt100_parser_alt_enter_lf() -> None:
    """Alt+Enter (ESC+LF) 应被解析成 (Escape, ControlJ)。"""
    assert _bytes_to_keys("\x1b\n") == (Keys.Escape, Keys.ControlJ)


def test_vt100_parser_plain_enter() -> None:
    """单 Enter 应是 ControlM。"""
    assert _bytes_to_keys("\r") == (Keys.ControlM,)


def test_vt100_parser_bare_lf() -> None:
    """裸 LF（部分终端的 Shift+Enter / Ctrl+J）应是 ControlJ。"""
    assert _bytes_to_keys("\n") == (Keys.ControlJ,)


def test_vt100_parser_csi_u_modified_enter() -> None:
    """CSI u 的 Shift/Alt+Enter 目前会被 prompt_toolkit 拆成普通字符序列。"""
    assert _bytes_to_keys("\x1b[13;2u") == (
        Keys.Escape,
        "[",
        "1",
        "3",
        ";",
        "2",
        "u",
    )
    assert _bytes_to_keys("\x1b[13;3u") == (
        Keys.Escape,
        "[",
        "1",
        "3",
        ";",
        "3",
        "u",
    )


def test_vt100_parser_xterm_modified_shift_enter() -> None:
    """xterm modifyOtherKeys 的 Shift+Enter 会保留在 KeyPress.data 中。"""
    presses: list[KeyPress] = []
    parser = Vt100Parser(presses.append)
    parser.feed_and_flush(XTERM_MODIFIED_SHIFT_ENTER)

    assert tuple(p.key for p in presses) == (Keys.ControlM,)
    assert presses[0].data == XTERM_MODIFIED_SHIFT_ENTER


def test_binding_alt_enter_cr_hits_newline() -> None:
    """Alt+Enter (ESC+CR) -> _newline，绝不能命中 _submit。"""
    kb, _ = _build_ui_bindings()
    matches = kb.get_bindings_for_keys((Keys.Escape, Keys.ControlM))
    assert len(matches) == 1
    assert matches[0].handler.__name__ == "_newline"


def test_binding_alt_enter_lf_hits_newline() -> None:
    """Alt+Enter (ESC+LF) -> _newline。"""
    kb, _ = _build_ui_bindings()
    matches = kb.get_bindings_for_keys((Keys.Escape, Keys.ControlJ))
    assert len(matches) == 1
    assert matches[0].handler.__name__ == "_newline"


def test_binding_plain_enter_hits_submit() -> None:
    """单 Enter -> _submit，绝不能误命中 _newline。"""
    kb, _ = _build_ui_bindings()
    matches = kb.get_bindings_for_keys((Keys.ControlM,))
    assert len(matches) == 1
    assert matches[0].handler.__name__ == "_submit"


def test_binding_bare_lf_hits_newline() -> None:
    """裸 LF -> _newline，方便支持 Shift+Enter 发 LF 的终端。"""
    kb, _ = _build_ui_bindings()
    matches = kb.get_bindings_for_keys((Keys.ControlJ,))
    assert len(matches) == 1
    assert matches[0].handler.__name__ == "_newline"


def test_binding_csi_u_shift_enter_hits_newline() -> None:
    """CSI u Shift+Enter -> _newline。"""
    kb, _ = _build_ui_bindings()
    matches = kb.get_bindings_for_keys((Keys.Escape, "[", "1", "3", ";", "2", "u"))
    assert len(matches) == 1
    assert matches[0].handler.__name__ == "_newline"


def test_binding_csi_u_alt_enter_hits_newline() -> None:
    """CSI u Alt/Option+Enter -> _newline。"""
    kb, _ = _build_ui_bindings()
    matches = kb.get_bindings_for_keys((Keys.Escape, "[", "1", "3", ";", "3", "u"))
    assert len(matches) == 1
    assert matches[0].handler.__name__ == "_newline"


def test_binding_xterm_alt_enter_hits_newline() -> None:
    """xterm modifyOtherKeys Alt/Option+Enter -> _newline。"""
    kb, _ = _build_ui_bindings()
    matches = kb.get_bindings_for_keys(
        (Keys.Escape, "[", "2", "7", ";", "3", ";", "1", "3", "~")
    )
    assert len(matches) == 1
    assert matches[0].handler.__name__ == "_newline"


def test_terminal_key_reporting_requests_alt_modified_keys_only() -> None:
    """启动 TUI 时用 modifyOtherKeys level 1，避免改写 Ctrl 编辑键。"""
    assert "\x1b[?1036;1039s" in TERMINAL_KEY_REPORTING_ENABLE
    assert "\x1b[?1036;1039h" in TERMINAL_KEY_REPORTING_ENABLE
    assert "\x1b[>4;1m" in TERMINAL_KEY_REPORTING_ENABLE
    assert "\x1b[>4;2m" not in TERMINAL_KEY_REPORTING_ENABLE
    assert "\x1b[>4m" in TERMINAL_KEY_REPORTING_DISABLE
    assert "\x1b[?1036;1039r" in TERMINAL_KEY_REPORTING_DISABLE


def test_write_terminal_sequence_flushes_raw_output() -> None:
    """写终端控制序列时使用 write_raw 并 flush。"""
    from prompt_toolkit.output import DummyOutput

    class RecordingOutput(DummyOutput):
        def __init__(self) -> None:
            self.writes: list[str] = []
            self.flush_count = 0

        def write_raw(self, data: str) -> None:
            self.writes.append(data)

        def flush(self) -> None:
            self.flush_count += 1

    output = RecordingOutput()
    _write_terminal_sequence(output, "abc")

    assert output.writes == ["abc"]
    assert output.flush_count == 1


def test_binding_starts_with_escape_waits() -> None:
    """看到单个 ESC 时，KeyBindings 应能找到以 Escape 开头的更长序列，
    意味着 KeyProcessor 会等待下一个键，而不是立刻把 ESC 当独立键触发。"""
    kb, _ = _build_ui_bindings()
    starts = kb.get_bindings_starting_with_keys((Keys.Escape,))
    handler_names = {m.handler.__name__ for m in starts}
    assert "_newline" in handler_names


def test_real_ui_module_bindings_match() -> None:
    """直接 import ui.run_chat_ui 内部用到的相同绑定声明，确保未来
    有人改了 ui.py 也会被这个测试看见。

    做法：解析 ui.py 源码里 _newline 上方的 @kb.add(...) 装饰器，把
    解析出来的键序列拿来直接构造一遍绑定并查找。比 mock 整个 TUI 简单
    可靠。
    """
    import ast
    import pathlib

    ui_path = pathlib.Path(__file__).parent.parent / "mincc" / "ui.py"
    tree = ast.parse(ui_path.read_text(encoding="utf-8"))

    newline_decorators: list[tuple[str, ...]] = []
    submit_decorators: list[tuple[str, ...]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("_newline", "_submit"):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "add"
                ):
                    keys = tuple(
                        a.value for a in dec.args if isinstance(a, ast.Constant)
                    )
                    if not keys:
                        continue
                    if node.name == "_newline":
                        newline_decorators.append(keys)
                    else:
                        submit_decorators.append(keys)

    # 至少要覆盖 ESC+Enter / ESC+c-j / CSI u / modifyOtherKeys / 裸 c-j
    assert ("escape", "enter") in newline_decorators, newline_decorators
    assert ("escape", "c-j") in newline_decorators, newline_decorators
    assert ("escape", "[", "1", "3", ";", "2", "u") in newline_decorators, newline_decorators
    assert ("escape", "[", "1", "3", ";", "3", "u") in newline_decorators, newline_decorators
    assert (
        "escape",
        "[",
        "2",
        "7",
        ";",
        "3",
        ";",
        "1",
        "3",
        "~",
    ) in newline_decorators, newline_decorators
    assert ("c-j",) in newline_decorators, newline_decorators
    assert ("c-o",) not in newline_decorators, newline_decorators
    # _submit 必须绑定 enter
    assert ("enter",) in submit_decorators, submit_decorators


def test_end_to_end_pipe_input_newlines() -> None:
    """端到端：起一个真实 Application，把"原始终端字节"喂进去，
    断言最终 buffer 文本里换行符的数量。

    覆盖：Alt+Enter(ESC+CR) / Alt+Enter(ESC+LF) / 裸 LF / 普通 Enter。
    Application 用 DummyOutput + create_pipe_input，不依赖真实终端。
    """
    import asyncio

    from prompt_toolkit.application import Application
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.output import DummyOutput
    from prompt_toolkit.widgets import TextArea

    async def run() -> str:
        with create_pipe_input() as pipe_input:
            ta = TextArea(multiline=True)
            kb = KeyBindings()
            result: dict[str, str] = {}

            @kb.add("escape", "enter")
            @kb.add("escape", "c-j")
            @kb.add("escape", "[", "1", "3", ";", "2", "u")
            @kb.add("escape", "[", "1", "3", ";", "3", "u")
            @kb.add("escape", "[", "1", "3", ";", "4", "u")
            @kb.add("escape", "[", "2", "7", ";", "3", ";", "1", "3", "~")
            @kb.add("escape", "[", "2", "7", ";", "4", ";", "1", "3", "~")
            @kb.add("c-j")
            def _newline(event):  # noqa: ARG001
                event.current_buffer.insert_text("\n")

            @kb.add("enter")
            def _submit(event):
                if event.key_sequence and event.key_sequence[-1].data == XTERM_MODIFIED_SHIFT_ENTER:
                    event.current_buffer.insert_text("\n")
                    return
                result["text"] = event.current_buffer.text
                event.app.exit()

            app: Application = Application(
                layout=Layout(ta),
                key_bindings=kb,
                input=pipe_input,
                output=DummyOutput(),
                full_screen=False,
            )

            # A + Alt+Enter(CR) + B + Alt+Enter(LF) + C + bare-LF
            # + D + CSI u Shift+Enter + E + CSI u Alt+Enter
            # + F + xterm Shift+Enter + G + xterm Alt+Enter + H + Enter
            pipe_input.send_text(
                "A\x1b\rB\x1b\nC\nD\x1b[13;2uE\x1b[13;3u"
                f"F{XTERM_MODIFIED_SHIFT_ENTER}G\x1b[27;3;13~H\r"
            )
            await app.run_async()
            return result["text"]

    text = asyncio.run(run())
    assert text == "A\nB\nC\nD\nE\nF\nG\nH", repr(text)


def test_end_to_end_split_escape_enter_newline() -> None:
    """Alt/Option+Enter 被拆成裸 ESC + Enter 时仍应换行。"""
    import asyncio

    from prompt_toolkit.application import Application
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.output import DummyOutput
    from prompt_toolkit.widgets import TextArea

    async def run() -> str:
        with create_pipe_input() as pipe_input:
            ta = TextArea(multiline=True)
            kb = KeyBindings()
            result: dict[str, str] = {}

            @kb.add("escape", "enter")
            def _newline(event):  # noqa: ARG001
                event.current_buffer.insert_text("\n")

            @kb.add("enter")
            def _submit(event):
                if _previous_key_was_escape(event):
                    event.current_buffer.insert_text("\n")
                    return
                result["text"] = event.current_buffer.text
                event.app.exit()

            app: Application = Application(
                layout=Layout(ta),
                key_bindings=kb,
                input=pipe_input,
                output=DummyOutput(),
                full_screen=False,
            )

            async def feed() -> None:
                pipe_input.send_text("A\x1b")
                await asyncio.sleep(app.ttimeoutlen + 0.1)
                pipe_input.send_text("\rB\r")

            asyncio.create_task(feed())
            await app.run_async()
            return result["text"]

    text = asyncio.run(run())
    assert text == "A\nB", repr(text)


def test_end_to_end_common_cli_editing_shortcuts() -> None:
    """常见 readline/CLI 编辑键应继续由 TextArea 默认绑定处理。

    这个测试覆盖我们曾经因为开启 modifyOtherKeys level 2 而破坏的键：
    Ctrl-A/E/F/B/K/U/W。
    """
    import asyncio

    from prompt_toolkit.application import Application
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.output import DummyOutput
    from prompt_toolkit.widgets import TextArea

    async def run(seq: str) -> str:
        with create_pipe_input() as pipe_input:
            ta = TextArea(multiline=True)
            kb = KeyBindings()
            result: dict[str, str] = {}

            @kb.add("enter")
            def _submit(event):
                result["text"] = event.current_buffer.text
                event.app.exit()

            app: Application = Application(
                layout=Layout(ta),
                key_bindings=kb,
                input=pipe_input,
                output=DummyOutput(),
                full_screen=False,
            )
            pipe_input.send_text(seq)
            await app.run_async()
            return result["text"]

    cases = {
        # Ctrl-A moves to line start; Ctrl-E moves to line end.
        "ctrl_a_e": ("abc\x01X\x05Y\r", "XabcY"),
        # Ctrl-B moves back; Ctrl-F moves forward.
        "ctrl_b_f": ("abc\x02X\x06Y\r", "abXcY"),
        # Ctrl-K kills to end of line.
        "ctrl_k": ("abc\x01X\x0b\r", "X"),
        # Ctrl-U kills backward to start of line.
        "ctrl_u": ("abc\x15X\r", "X"),
        # Ctrl-W deletes the previous word.
        "ctrl_w": ("abc def\x17X\r", "abc X"),
    }
    for name, (seq, expected) in cases.items():
        text = asyncio.run(run(seq))
        assert text == expected, f"{name}: {text!r}"


def test_end_to_end_more_cli_editing_shortcuts() -> None:
    """补充覆盖更多常见 CLI 编辑键及其与换行绑定的共存。"""
    import asyncio

    from prompt_toolkit.application import Application
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.output import DummyOutput
    from prompt_toolkit.widgets import TextArea

    async def run(seq: str) -> str:
        with create_pipe_input() as pipe_input:
            ta = TextArea(multiline=True)
            kb = KeyBindings()
            result: dict[str, str] = {}

            @kb.add("escape", "enter")
            @kb.add("escape", "c-j")
            @kb.add("c-j")
            def _newline(event):  # noqa: ARG001
                event.current_buffer.insert_text("\n")

            @kb.add("enter")
            def _submit(event):
                result["text"] = event.current_buffer.text
                event.app.exit()

            app: Application = Application(
                layout=Layout(ta),
                key_bindings=kb,
                input=pipe_input,
                output=DummyOutput(),
                full_screen=False,
            )
            pipe_input.send_text(seq)
            await app.run_async()
            return result["text"]

    cases = {
        # Ctrl-T transposes the two characters before/around the cursor.
        "ctrl_t": ("ab\x14\r", "ba"),
        # Ctrl-K/Y and Ctrl-U/Y keep the kill/yank buffer behavior.
        "ctrl_k_y": ("abc\x01\x0b\x19\r", "abc"),
        "ctrl_u_y": ("abc\x15\x19\r", "abc"),
        # Ctrl-L redraws/clears screen without changing input.
        "ctrl_l": ("abc\x0cX\r", "abcX"),
        # Ctrl-H and DEL/backspace delete the previous character.
        "ctrl_h": ("abc\x08X\r", "abX"),
        "backspace": ("abc\x7fX\r", "abX"),
        # Alt+Enter newline should coexist with line-local Ctrl-A/E editing.
        "newline_plus_edit": ("abc\x1b\rdef\x01X\x05Y\r", "abc\nXdefY"),
    }
    for name, (seq, expected) in cases.items():
        text = asyncio.run(run(seq))
        assert text == expected, f"{name}: {text!r}"


def test_end_to_end_ctrl_c_and_ctrl_d_exit() -> None:
    """Ctrl-C / Ctrl-D 仍然执行 mincc 的退出绑定。"""
    import asyncio

    from prompt_toolkit.application import Application
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.output import DummyOutput
    from prompt_toolkit.widgets import TextArea

    async def run(seq: str) -> str:
        with create_pipe_input() as pipe_input:
            ta = TextArea(multiline=True)
            kb = KeyBindings()
            result: dict[str, str] = {"exit": ""}

            @kb.add("c-c")
            @kb.add("c-d")
            def _exit(event):
                result["exit"] = event.key_sequence[-1].key.value
                event.app.exit()

            @kb.add("enter")
            def _submit(event):
                result["exit"] = "submitted"
                event.app.exit()

            app: Application = Application(
                layout=Layout(ta),
                key_bindings=kb,
                input=pipe_input,
                output=DummyOutput(),
                full_screen=False,
            )
            pipe_input.send_text(seq)
            await app.run_async()
            return result["exit"]

    assert asyncio.run(run("abc\x03")) == "c-c"
    assert asyncio.run(run("abc\x04")) == "c-d"
