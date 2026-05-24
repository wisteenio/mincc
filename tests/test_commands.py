"""斜杠命令注册表与匹配逻辑的最小测试。"""

from mincc.commands import (
    BUILTIN_COMMANDS,
    list_commands,
    match_commands,
    matched_name,
)


def test_builtin_commands_nonempty() -> None:
    cmds = list_commands()
    assert cmds
    names = {c.name for c in cmds}
    assert {"exit", "help"}.issubset(names)


def test_exit_has_quit_alias() -> None:
    exit_cmd = next(c for c in BUILTIN_COMMANDS if c.name == "exit")
    assert "quit" in exit_cmd.aliases


def test_no_match_without_slash() -> None:
    assert match_commands("hello") == []
    assert match_commands("") == []


def test_slash_lists_all_builtins() -> None:
    out = match_commands("/")
    names = {c.name for c in out}
    assert "exit" in names
    assert "help" in names


def test_prefix_filters_candidates() -> None:
    out = match_commands("/ex")
    names = {c.name for c in out}
    assert names == {"exit"}


def test_prefix_filters_candidates_after_leading_spaces() -> None:
    out = match_commands("   /ex")
    names = {c.name for c in out}
    assert names == {"exit"}


def test_alias_matches() -> None:
    out = match_commands("/qu")
    names = {c.name for c in out}
    assert "exit" in names  # /qu 应命中 exit 的 quit 别名


def test_no_match_after_space() -> None:
    # 已经在写参数，不再补全命令名
    assert match_commands("/exit ") == []
    assert match_commands("   /exit ") == []


def test_matched_name_main_vs_alias() -> None:
    exit_cmd = next(c for c in BUILTIN_COMMANDS if c.name == "exit")
    assert matched_name(exit_cmd, "/ex") == "exit"
    assert matched_name(exit_cmd, "/qu") == "quit"
    assert matched_name(exit_cmd, "   /qu") == "quit"


def test_slash_command_lexer_highlights_first_token() -> None:
    from prompt_toolkit.document import Document

    from mincc.ui import _SlashCommandLexer

    get_line = _SlashCommandLexer().lex_document(Document("/exit now"))
    assert get_line(0) == [
        ("class:input.slash-cmd", "/exit"),
        ("", " now"),
    ]


def test_slash_command_lexer_preserves_leading_spaces() -> None:
    from prompt_toolkit.document import Document

    from mincc.ui import _SlashCommandLexer

    get_line = _SlashCommandLexer().lex_document(Document("   /exit now"))
    assert get_line(0) == [
        ("", "   "),
        ("class:input.slash-cmd", "/exit"),
        ("", " now"),
    ]


def test_slash_command_lexer_ignores_non_command_text() -> None:
    from prompt_toolkit.document import Document

    from mincc.ui import _SlashCommandLexer

    get_line = _SlashCommandLexer().lex_document(Document("hello /exit"))
    assert get_line(0) == [("", "hello /exit")]


def test_user_history_line_highlights_command_after_prompt_and_spaces() -> None:
    from mincc.ui import _user_line_fragments

    assert _user_line_fragments("›  /exit now     ") == [
        ("class:user-msg", "›  "),
        ("class:user-msg.slash-cmd", "/exit"),
        ("class:user-msg", " now     "),
    ]


def test_user_lines_add_padding_around_message() -> None:
    from mincc.ui import _user_lines

    assert _user_lines("/exit", width=12) == [
        "› /exit     ",
    ]
