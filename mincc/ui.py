"""全屏 TUI 交互界面。

布局：
- 顶部历史区：用户消息带浅色背景块；AI 回复纯文本无装饰；进行中显示 spinner。
- 中部输入框：上下各有一条分隔线；Enter 提交，Shift+Enter / Alt+Enter / Option+Enter 换行。
- 底部信息面板：当前用于显示斜杠命令列表（输入以 `/` 开头时），将来可承载其他信息。
- Ctrl-C / Ctrl-D 退出。

LLM 调用通过 on_submit 回调传入，由本模块在后台线程跑，UI 主循环不阻塞。
on_submit 可通过 update_status 回调更新当前执行阶段。
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass

from prompt_toolkit.application import Application
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition, to_filter
from prompt_toolkit.formatted_text import ANSI, FormattedText, to_formatted_text
from prompt_toolkit.formatted_text.base import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import ConditionalContainer, HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.output import Output
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.widgets import TextArea
from rich.console import Console
from rich.markdown import Markdown

from mincc.commands import match_commands, matched_name

SPINNER_FRAMES = ("✢", "✳", "✶", "✻", "✽")
SPINNER_INTERVAL = 0.12
USER_MESSAGE_CONTENT_START = 2

# 终端无法真的放大字号，标题用块状字符拼成"伪大字"以获得视觉重量。
# 每个字母/词组占一块，整体居中显示。手写而非引入 pyfiglet，避免新增依赖。
WELCOME_TITLE_LINES: tuple[str, ...] = (
    "███╗   ███╗██╗███╗   ██╗██╗     ██████╗ ██████╗",
    "████╗ ████║██║████╗  ██║██║    ██╔════╝██╔════╝",
    "██╔████╔██║██║██╔██╗ ██║██║    ██║     ██║     ",
    "██║╚██╔╝██║██║██║╚██╗██║██║    ██║     ██║     ",
    "██║ ╚═╝ ██║██║██║ ╚████║██║    ╚██████╗╚██████╗",
    "╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝     ╚═════╝ ╚═════╝",
)
WELCOME_TITLE_FALLBACK = "✦ Mini Claude Code"
WELCOME_SUBTITLE = "基于 LangChain / LangGraph 的最小版本 Claude Code"
WELCOME_HINTS: tuple[tuple[str, str], ...] = (
    ("⏎", "提交"),
    ("⇧⏎", "换行"),
    ("/", "查看可用命令"),
    ("⌃C or /exit", "退出"),
)

XTERM_MODIFIED_SHIFT_ENTER = "\x1b[27;2;13~"
XTERM_SAVE_ALT_MODES = "\x1b[?1036;1039s"
XTERM_ENABLE_ALT_SENDS_ESCAPE = "\x1b[?1036;1039h"
XTERM_ENABLE_MODIFY_OTHER_KEYS_ALT_ONLY = "\x1b[>4;1m"
XTERM_RESET_MODIFY_OTHER_KEYS = "\x1b[>4m"
XTERM_RESTORE_ALT_MODES = "\x1b[?1036;1039r"
TERMINAL_KEY_REPORTING_ENABLE = (
    XTERM_SAVE_ALT_MODES + XTERM_ENABLE_ALT_SENDS_ESCAPE + XTERM_ENABLE_MODIFY_OTHER_KEYS_ALT_ONLY
)
TERMINAL_KEY_REPORTING_DISABLE = XTERM_RESET_MODIFY_OTHER_KEYS + XTERM_RESTORE_ALT_MODES
XTERM_LIKE_TERMS = (
    "xterm",
    "screen",
    "tmux",
    "rxvt",
    "kitty",
    "wezterm",
    "ghostty",
    "alacritty",
    "foot",
    "contour",
)
VT_CAPABLE_WINDOWS_ENV_VARS = (
    "WT_SESSION",
    "TERM_PROGRAM",
    "VSCODE_INJECTION",
    "ConEmuANSI",
    "MSYSTEM",
)


@dataclass
class _Entry:
    role: str  # "welcome" | "user" | "assistant" | "spinner"
    text: str


def _slash_command_token_bounds(line: str, start_at: int = 0) -> tuple[int, int] | None:
    """返回一行中斜杠命令 token 的起止位置，允许 token 前有缩进空格。"""
    start = start_at
    while start < len(line) and line[start] == " ":
        start += 1
    if start >= len(line) or line[start] != "/":
        return None

    end = len(line)
    for i in range(start, len(line)):
        if line[i].isspace():
            end = i
            break
    if end == start:
        return None
    return start, end


class _SlashCommandLexer(Lexer):
    """高亮输入区首行的斜杠命令 token。"""

    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        lines = document.lines

        def get_line(lineno: int) -> StyleAndTextTuples:
            line = lines[lineno]
            if lineno != 0:
                return [("", line)]

            bounds = _slash_command_token_bounds(line)
            if bounds is None:
                return [("", line)]
            start, end = bounds
            return [
                fragment
                for fragment in [
                    ("", line[:start]),
                    ("class:input.slash-cmd", line[start:end]),
                    ("", line[end:]),
                ]
                if fragment[1]
            ]

        return get_line


_STYLE = Style.from_dict(
    {
        "welcome": "#888888",
        "welcome.title": "#ff8c42 bold",
        "welcome.subtitle": "#cccccc",
        "welcome.hint-key": "#ffd166 bold",
        "welcome.hint-desc": "#888888",
        "welcome.rule": "#444444",
        "user-prompt": "bg:#2a2a2a #888888",
        "user-msg": "bg:#2a2a2a #ffffff",
        "user-msg.slash-cmd": "bg:#2a2a2a #d9a066",
        "assistant-msg": "",
        "spinner": "#ff8c42",
        "sep": "#444444",
        "input-area": "",
        "suggestion": "#888888",
        "suggestion.name": "#cccccc",
        "suggestion.summary": "#666666",
        "suggestion.current": "bg:#3a3a3a #ffffff bold",
        "suggestion.current.name": "bg:#3a3a3a #ffffff bold",
        "suggestion.current.summary": "bg:#3a3a3a #dddddd",
        "input.slash-cmd": "#ff8c42 bold",
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


def _user_line_fragments(line: str) -> list[tuple[str, str]]:
    """用户历史行的样式切分：保留背景，同时高亮斜杠命令 token。"""
    # _user_lines 会在第一行加 "› "，后续行加两个空格缩进；命令从其后开始判定。
    bounds = _slash_command_token_bounds(line, start_at=USER_MESSAGE_CONTENT_START)
    if bounds is None:
        return [("class:user-msg", line)]
    start, end = bounds
    return [
        fragment
        for fragment in [
            ("class:user-msg", line[:start]),
            ("class:user-msg.slash-cmd", line[start:end]),
            ("class:user-msg", line[end:]),
        ]
        if fragment[1]
    ]


def _render_markdown_ansi(text: str, width: int) -> str:
    """用 rich 把 Markdown 渲染成带 ANSI 转义码的字符串。

    width 用于换行；这里限制最大列宽，避免把长终端撑得读不过来。
    """
    eff_width = max(20, min(width, 120))
    buf = io.StringIO()
    console = Console(
        file=buf,
        width=eff_width,
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
        soft_wrap=False,
        record=False,
    )
    console.print(Markdown(text, code_theme="monokai"))
    rendered = buf.getvalue()
    # rich 总会在末尾追加一个换行；这里去掉，避免与条目间距叠加成两空行。
    if rendered.endswith("\n"):
        rendered = rendered[:-1]
    return rendered


def _welcome_fragments(width: int) -> list[tuple[str, str]]:
    """欢迎信息：标题 / 副标题 / 横线 / 快捷键提示，整体水平居中。

    标题用 WELCOME_TITLE_LINES 这套块状字符拼成"伪大字"。窄终端放不下时，
    退化到 WELCOME_TITLE_FALLBACK 单行小标题。
    """
    title_lines = list(WELCOME_TITLE_LINES)
    title_w = max((get_cwidth(line) for line in title_lines), default=0)
    if title_w + 4 > width:
        title_lines = [WELCOME_TITLE_FALLBACK]
        title_w = get_cwidth(WELCOME_TITLE_FALLBACK)

    subtitle = WELCOME_SUBTITLE
    hints = WELCOME_HINTS
    rule_w = min(max(title_w, get_cwidth(subtitle), 32), max(20, width - 4))
    rule = "─" * rule_w

    def _center(line_width: int) -> str:
        return " " * max(0, (width - line_width) // 2)

    fragments: list[tuple[str, str]] = []
    for i, line in enumerate(title_lines):
        if i > 0:
            fragments.append(("", "\n"))
        fragments.append(("", _center(get_cwidth(line))))
        fragments.append(("class:welcome.title", line))
    fragments.append(("", "\n\n"))
    fragments.append(("", _center(get_cwidth(subtitle))))
    fragments.append(("class:welcome.subtitle", subtitle))
    fragments.append(("", "\n"))
    fragments.append(("", _center(rule_w)))
    fragments.append(("class:welcome.rule", rule))
    fragments.append(("", "\n"))

    # 把所有 hint 拼成一行用 ' · ' 分隔；超长时降级为多行（每行一个 hint）。
    sep = "  ·  "
    one_line_w = sum(get_cwidth(f"{k} {d}") for k, d in hints) + get_cwidth(sep) * (len(hints) - 1)
    if one_line_w <= width - 2:
        fragments.append(("", _center(one_line_w)))
        for i, (k, d) in enumerate(hints):
            if i > 0:
                fragments.append(("class:welcome", sep))
            fragments.append(("class:welcome.hint-key", k))
            fragments.append(("class:welcome", " "))
            fragments.append(("class:welcome.hint-desc", d))
    else:
        for i, (k, d) in enumerate(hints):
            if i > 0:
                fragments.append(("", "\n"))
            line_w = get_cwidth(f"{k} {d}")
            fragments.append(("", _center(line_w)))
            fragments.append(("class:welcome.hint-key", k))
            fragments.append(("class:welcome", " "))
            fragments.append(("class:welcome.hint-desc", d))
    return fragments


def _render(entries: list[_Entry]) -> FormattedText:
    """把历史条目拼成 FormattedText。条目之间留一个空行。"""
    fragments: list[tuple[str, str]] = []
    width = _term_width()
    for i, entry in enumerate(entries):
        if i > 0:
            fragments.append(("", "\n\n"))
        if entry.role == "welcome":
            fragments.extend(_welcome_fragments(width))
        elif entry.role == "user":
            lines = _user_lines(entry.text, width)
            for j, line in enumerate(lines):
                if j > 0:
                    fragments.append(("class:user-msg", "\n"))
                fragments.extend(_user_line_fragments(line))
        elif entry.role == "assistant":
            ansi = _render_markdown_ansi(entry.text, width)
            fragments.extend(list(to_formatted_text(ANSI(ansi))))
        elif entry.role == "spinner":
            fragments.append(("class:spinner", entry.text))
    return FormattedText(fragments)


def _write_terminal_sequence(output: Output, sequence: str) -> None:
    """向终端写入原始控制序列；不支持时静默跳过。"""
    try:
        output.write_raw(sequence)
        output.flush()
    except Exception:  # noqa: BLE001
        return


def _supports_terminal_key_reporting(output: Output) -> bool:
    """判断当前输出后端是否适合写 xterm 私有按键上报序列。"""
    output_name = type(output).__name__.lower()
    if "dummy" in output_name:
        return False

    term = os.environ.get("TERM", "").lower()
    if term == "dumb":
        return False

    if os.name == "nt":
        return any(os.environ.get(name) for name in VT_CAPABLE_WINDOWS_ENV_VARS) or any(
            marker in term for marker in XTERM_LIKE_TERMS
        )

    return any(marker in term for marker in XTERM_LIKE_TERMS)


def _previous_key_was_escape(event) -> bool:
    """上一段已处理按键是裸 ESC，常见于 Alt/Option+Enter 被拆包。"""
    return (
        len(event.previous_key_sequence) == 1 and event.previous_key_sequence[-1].key == Keys.Escape
    )


def run_chat_ui(
    on_submit: Callable[[str, Callable[[str], None]], str],
    input_history: list[str] | None = None,
) -> None:
    """启动全屏 TUI 聊天界面。

    on_submit: 接收用户输入字符串与状态更新回调，返回 AI 最终回复字符串（同步阻塞调用）。
    """
    entries: list[_Entry] = [_Entry(role="welcome", text="")]
    spinner_idx: int | None = None
    spinner_frame = 0
    spinner_label = "准备中"
    busy = False
    history_items = input_history if input_history is not None else []
    history_cursor: int | None = None
    history_draft = ""

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
        height=Dimension(min=1),
        style="class:input-area",
        focus_on_click=True,
        lexer=_SlashCommandLexer(),
    )
    # TextArea 内部 Window 默认会被 HSplit 撑高，需要显式禁止，
    # 这样输入区高度只跟随内容行数，而不是占满剩余空间。
    input_area.window.dont_extend_height = to_filter(True)

    sep_top = Window(height=1, char="─", style="class:sep")
    sep_bottom = Window(height=1, char="─", style="class:sep")
    # 底部弹性占位：当内容很少时把 history+input 压在屏幕顶部
    filler = Window(height=Dimension(weight=1))

    # 斜杠命令面板状态：当前匹配命令列表与选中下标。
    # 列表随 input_area 文本变化重算；选中下标在重算时尽量保持原命令。
    # dismissed_for 记录"用户用 ESC 关闭面板时的输入文本"：
    # 文本未改前不再弹回；任何编辑都会清掉这个记号。
    # app 在 Application 创建后回填，用于动态调整 ttimeoutlen。
    panel_state: dict = {
        "matches": [],
        "selected": 0,
        "dismissed_for": None,
        "app": None,
    }

    def _sync_ttimeout() -> None:
        """面板展开时把 vt100 解析超时调短，让单击 ESC 立即关面板。

        平时保持默认 0.5s，避免 Option+Enter / Alt+Enter 这类
        ESC+CR 两字节序列因解析窗口太短而被拆成 ESC + Enter（提交）。
        """
        a = panel_state.get("app")
        if a is not None:
            a.ttimeoutlen = 0.05 if panel_state["matches"] else 0.5

    def _refresh_matches() -> None:
        """根据当前输入刷新候选列表，并修正选中下标。"""
        text = input_area.text
        # ESC 关闭后，只要文本没变就一直保持隐藏
        if panel_state["dismissed_for"] == text:
            panel_state["matches"] = []
            panel_state["selected"] = 0
            _sync_ttimeout()
            return
        panel_state["dismissed_for"] = None
        new_matches = match_commands(text)
        prev_matches = panel_state["matches"]
        prev_selected = panel_state["selected"]
        prev_name = (
            prev_matches[prev_selected].name
            if prev_matches and 0 <= prev_selected < len(prev_matches)
            else None
        )
        new_selected = 0
        if prev_name is not None:
            for i, c in enumerate(new_matches):
                if c.name == prev_name:
                    new_selected = i
                    break
        panel_state["matches"] = new_matches
        panel_state["selected"] = new_selected
        _sync_ttimeout()

    # 文本变更时刷新候选
    input_area.buffer.on_text_changed += lambda _buf: _refresh_matches()

    has_suggestions = Condition(lambda: bool(panel_state["matches"]))

    def _suggestion_text() -> FormattedText:
        """渲染底部命令面板：每行 '/<name>   <summary>'，选中行高亮。"""
        matches = panel_state["matches"]
        selected = panel_state["selected"]
        if not matches:
            return FormattedText([])
        # 命令列宽度对齐，便于阅读
        name_col = max(get_cwidth(f"/{c.name}") for c in matches) + 2
        width = _term_width()
        fragments: list[tuple[str, str]] = []
        for i, cmd in enumerate(matches):
            is_cur = i == selected
            base = "class:suggestion.current" if is_cur else "class:suggestion"
            name_cls = f"{base}.name" if not is_cur else "class:suggestion.current.name"
            summary_cls = (
                "class:suggestion.current.summary" if is_cur else "class:suggestion.summary"
            )
            name_text = f" /{cmd.name}"
            pad_after_name = " " * max(1, name_col - get_cwidth(name_text) + 1)
            summary = cmd.summary
            used = get_cwidth(name_text) + get_cwidth(pad_after_name) + get_cwidth(summary)
            tail_pad = " " * max(0, width - used)
            fragments.append((name_cls, name_text))
            fragments.append((base, pad_after_name))
            fragments.append((summary_cls, summary))
            fragments.append((base, tail_pad))
            if i != len(matches) - 1:
                fragments.append(("", "\n"))
        return FormattedText(fragments)

    suggestion_window = Window(
        content=FormattedTextControl(text=_suggestion_text, focusable=False),
        height=Dimension(min=0),
        dont_extend_height=True,
        wrap_lines=False,
    )
    suggestion_panel = ConditionalContainer(
        content=suggestion_window,
        filter=has_suggestions,
    )

    root_container = HSplit(
        [history_window, sep_top, input_area, sep_bottom, suggestion_panel, filler]
    )

    kb = KeyBindings()

    @kb.add("c-c")
    @kb.add("c-d")
    def _exit(event) -> None:
        event.app.exit()

    @kb.add("escape", "enter")
    @kb.add("escape", "c-j")
    @kb.add("escape", "[", "1", "3", ";", "2", "u")
    @kb.add("escape", "[", "1", "3", ";", "3", "u")
    @kb.add("escape", "[", "1", "3", ";", "4", "u")
    @kb.add("escape", "[", "2", "7", ";", "3", ";", "1", "3", "~")
    @kb.add("escape", "[", "2", "7", ";", "4", ";", "1", "3", "~")
    @kb.add("c-j")
    def _newline(event) -> None:
        # 换行覆盖几种常见字节序列：
        # - escape, enter == ESC+CR：多数终端发给 Alt/Option+Enter
        # - escape, c-j   == ESC+LF：少数终端发给 Alt/Option+Enter
        # - c-j           == LF：部分终端把 Shift+Enter 发成裸 LF，绑这个能让 Shift+Enter 换行；
        #                       不会误伤普通 Enter，因为 Enter 是 c-m（CR）。
        # - CSI u / modifyOtherKeys 序列：Kitty、Ghostty、WezTerm、iTerm2 等现代终端
        #   可能用这些形式上报 Shift+Enter / Alt+Enter / Option+Enter。启动时只请求
        #   modifyOtherKeys level 1，以保留 Ctrl-A/F/E 等默认编辑键。
        event.current_buffer.insert_text("\n")

    def _apply_selected() -> None:
        """把当前选中的命令写回输入框（替换整行），并清空候选。"""
        matches = panel_state["matches"]
        if not matches:
            return
        cmd = matches[panel_state["selected"]]
        name = matched_name(cmd, input_area.text)
        leading_spaces = input_area.text[: len(input_area.text) - len(input_area.text.lstrip(" "))]
        replacement = f"{leading_spaces}/{name} "
        input_area.buffer.document = Document(
            text=replacement,
            cursor_position=len(replacement),
        )
        # 写回时 on_text_changed 会刷新一次；写完后通常已经包含空格，应自动隐藏

    @kb.add("up", filter=has_suggestions)
    def _up(event) -> None:
        n = len(panel_state["matches"])
        if n:
            panel_state["selected"] = (panel_state["selected"] - 1) % n
            event.app.invalidate()

    @kb.add("down", filter=has_suggestions)
    def _down(event) -> None:
        n = len(panel_state["matches"])
        if n:
            panel_state["selected"] = (panel_state["selected"] + 1) % n
            event.app.invalidate()

    @kb.add("up", filter=~has_suggestions)
    def _history_previous(event) -> None:
        nonlocal history_cursor, history_draft
        if busy or not history_items:
            return
        if history_cursor is None:
            history_draft = input_area.text
            history_cursor = len(history_items) - 1
        else:
            history_cursor = max(0, history_cursor - 1)
        text = history_items[history_cursor]
        input_area.buffer.document = Document(text=text, cursor_position=len(text))

    @kb.add("down", filter=~has_suggestions)
    def _history_next(event) -> None:
        nonlocal history_cursor
        if busy or history_cursor is None:
            return
        if history_cursor >= len(history_items) - 1:
            text = history_draft
            history_cursor = None
        else:
            history_cursor += 1
            text = history_items[history_cursor]
        input_area.buffer.document = Document(text=text, cursor_position=len(text))

    @kb.add("escape", filter=has_suggestions)
    def _dismiss(event) -> None:
        """ESC：关闭候选面板，记下当前文本以避免立刻重新弹出。

        vt100 解析层 ttimeoutlen 在面板展开时已被调到 50ms（见
        _sync_ttimeout），此时单击 ESC 仍会很快触发；不设 eager 是为了
        让 Option/Alt+Enter 等以 ESC 开头的长序列仍然能被识别为换行。
        """
        panel_state["matches"] = []
        panel_state["selected"] = 0
        panel_state["dismissed_for"] = input_area.text
        _sync_ttimeout()
        event.app.invalidate()

    @kb.add("tab")
    def _tab(event) -> None:
        """Tab：候选面板展开时应用选中命令；否则空操作。"""
        if panel_state["matches"]:
            _apply_selected()
            event.app.invalidate()

    @kb.add("enter")
    def _submit(event) -> None:
        nonlocal busy, spinner_idx, spinner_frame, history_cursor, history_draft
        if (event.key_sequence and event.key_sequence[-1].data == XTERM_MODIFIED_SHIFT_ENTER) or (
            _previous_key_was_escape(event) and panel_state["dismissed_for"] != input_area.text
        ):
            event.current_buffer.insert_text("\n")
            return
        # 候选面板展开 → 应用选中项，不提交
        if panel_state["matches"]:
            _apply_selected()
            event.app.invalidate()
            return
        if busy:
            return
        text = input_area.text.rstrip()
        if not text.strip():
            return
        if text.lstrip(" ") in {"/exit", "/quit"}:
            event.app.exit()
            return
        history_cursor = None
        history_draft = ""
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

        def _update_status(label: str) -> None:
            def _apply_status() -> None:
                nonlocal spinner_label
                spinner_label = label
                if spinner_idx is not None:
                    entries[spinner_idx] = _Entry(
                        role="spinner",
                        text=f"{SPINNER_FRAMES[spinner_frame]} {spinner_label}",
                    )
                event.app.invalidate()

            loop.call_soon_threadsafe(_apply_status)

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
                reply = await loop.run_in_executor(None, on_submit, text, _update_status)
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

    key_reporting_enabled = False

    def _enable_key_reporting_after_render(a: Application) -> None:
        nonlocal key_reporting_enabled
        if key_reporting_enabled:
            return
        if not _supports_terminal_key_reporting(a.output):
            return
        key_reporting_enabled = True
        _write_terminal_sequence(a.output, TERMINAL_KEY_REPORTING_ENABLE)

    app: Application = Application(
        layout=layout,
        key_bindings=kb,
        style=_STYLE,
        full_screen=True,
        mouse_support=False,
        after_render=_enable_key_reporting_after_render,
    )
    panel_state["app"] = app
    try:
        app.run()
    finally:
        if key_reporting_enabled:
            _write_terminal_sequence(app.output, TERMINAL_KEY_REPORTING_DISABLE)
