"""全屏 TUI 交互界面。

布局：
- 顶部历史区：用户消息带浅色背景块；AI 回复纯文本无装饰；进行中显示 spinner。
- 底部输入框：固定在终端底部；Enter 提交，Alt+Enter 换行；Ctrl-C / Ctrl-D 退出。

LLM 调用通过 on_submit 回调传入，由本模块在后台线程跑，UI 主循环不阻塞。
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
from collections.abc import Callable
from dataclasses import dataclass

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.widgets import TextArea

SPINNER_FRAMES = ("✢", "✳", "✶", "✻", "✽")
SPINNER_INTERVAL = 0.12

WELCOME_TEXT = (
    "mincc\n"
    "基于 LangChain/LangGraph 实现的最小版本的 Claude Code\n"
    "Enter 提交，Alt+Enter 换行，Ctrl-C 或 /exit 退出。"
)


@dataclass
class _Entry:
    role: str  # "welcome" | "user" | "assistant" | "spinner"
    text: str


_STYLE = Style.from_dict(
    {
        "welcome": "#888888 italic",
        "user-prompt": "bg:#2a2a2a #888888",
        "user-msg": "bg:#2a2a2a #ffffff",
        "assistant-msg": "",
        "spinner": "#888888",
        "sep": "#444444",
        "input-area": "",
    }
)


def _term_width() -> int:
    """终端宽度，失败时退化到 80。"""
    try:
        return shutil.get_terminal_size((80, 24)).columns
    except OSError:
        return 80


def _user_lines(text: str, width: int) -> list[str]:
    """把用户消息按终端宽度切成若干行，每行右侧用空格补到整行宽度。

    第一行带 '› ' 前缀，后续行用等宽空格缩进对齐。
    """
    prefix = "› "
    indent = "  "
    prefix_w = get_cwidth(prefix)
    inner_width = max(1, width - prefix_w)
    lines: list[str] = []
    for raw in text.split("\n"):
        if not raw:
            lines.append("")
            continue
        cur = ""
        cur_w = 0
        for ch in raw:
            cw = get_cwidth(ch)
            if cur_w + cw > inner_width:
                lines.append(cur)
                cur = ch
                cur_w = cw
            else:
                cur += ch
                cur_w += cw
        lines.append(cur)

    out: list[str] = []
    for i, line in enumerate(lines):
        head = prefix if i == 0 else indent
        body = line
        used = get_cwidth(head) + get_cwidth(body)
        pad = max(0, width - used)
        out.append(head + body + " " * pad)
    return out


def _render(entries: list[_Entry]) -> FormattedText:
    """把历史条目拼成 FormattedText。条目之间留一个空行。"""
    fragments: list[tuple[str, str]] = []
    width = _term_width()
    for i, entry in enumerate(entries):
        if i > 0:
            fragments.append(("", "\n\n"))
        if entry.role == "welcome":
            fragments.append(("class:welcome", entry.text))
        elif entry.role == "user":
            lines = _user_lines(entry.text, width)
            for j, line in enumerate(lines):
                if j > 0:
                    fragments.append(("class:user-msg", "\n"))
                fragments.append(("class:user-msg", line))
        elif entry.role == "assistant":
            fragments.append(("class:assistant-msg", entry.text))
        elif entry.role == "spinner":
            fragments.append(("class:spinner", entry.text))
    return FormattedText(fragments)


def run_chat_ui(on_submit: Callable[[str], str]) -> None:
    """启动全屏 TUI 聊天界面。

    on_submit: 接收用户输入字符串，返回 AI 最终回复字符串（同步阻塞调用）。
    """
    entries: list[_Entry] = [_Entry(role="welcome", text=WELCOME_TEXT)]
    spinner_idx: int | None = None
    spinner_frame = 0
    spinner_label = "Gallivanting…"
    busy = False

    def get_history_text() -> FormattedText:
        return _render(entries)

    history_control = FormattedTextControl(text=get_history_text, focusable=False)
    history_window = Window(
        content=history_control,
        wrap_lines=True,
        dont_extend_height=True,
        height=Dimension(min=0),
    )

    input_area = TextArea(
        prompt="› ",
        multiline=True,
        wrap_lines=True,
        height=Dimension(min=1, max=6, preferred=1),
        style="class:input-area",
        focus_on_click=True,
    )

    sep = Window(height=1, char="─", style="class:sep")
    # 底部弹性占位：当内容很少时把 history+input 压在屏幕顶部
    filler = Window(height=Dimension(weight=1))

    root_container = HSplit([history_window, sep, input_area, filler])

    kb = KeyBindings()

    @kb.add("c-c")
    @kb.add("c-d")
    def _exit(event) -> None:
        event.app.exit()

    @kb.add("escape", "enter")
    def _newline(event) -> None:
        # Alt+Enter / Esc-Enter 插入换行
        event.current_buffer.insert_text("\n")

    @kb.add("enter")
    def _submit(event) -> None:
        nonlocal busy, spinner_idx, spinner_frame
        if busy:
            return
        text = input_area.text.strip()
        if not text:
            return
        if text in {"/exit", "/quit"}:
            event.app.exit()
            return
        input_area.buffer.reset()
        entries.append(_Entry(role="user", text=text))
        # 占位 spinner 行
        spinner_frame = 0
        entries.append(
            _Entry(
                role="spinner",
                text=f"{SPINNER_FRAMES[0]} {spinner_label}",
            )
        )
        spinner_idx = len(entries) - 1
        busy = True
        event.app.invalidate()

        loop = asyncio.get_event_loop()

        async def _animate() -> None:
            nonlocal spinner_frame
            while busy and spinner_idx is not None:
                await asyncio.sleep(SPINNER_INTERVAL)
                if not busy or spinner_idx is None:
                    break
                spinner_frame = (spinner_frame + 1) % len(SPINNER_FRAMES)
                entries[spinner_idx] = _Entry(
                    role="spinner",
                    text=f"{SPINNER_FRAMES[spinner_frame]} {spinner_label}",
                )
                event.app.invalidate()

        async def _run() -> None:
            nonlocal busy, spinner_idx
            anim = asyncio.create_task(_animate())
            try:
                reply = await loop.run_in_executor(None, on_submit, text)
            except Exception as exc:  # noqa: BLE001
                reply = f"[error] {exc}"
            anim.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await anim
            if spinner_idx is not None:
                entries[spinner_idx] = _Entry(role="assistant", text=reply)
            spinner_idx = None
            busy = False
            event.app.invalidate()

        asyncio.create_task(_run())

    layout = Layout(root_container, focused_element=input_area)

    app: Application = Application(
        layout=layout,
        key_bindings=kb,
        style=_STYLE,
        full_screen=True,
        mouse_support=False,
    )
    app.run()

