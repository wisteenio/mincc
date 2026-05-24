"""本地工具的最小安全与行为测试。"""

from __future__ import annotations

from mincc.tools.edit_file import edit_file
from mincc.tools.grep import grep
from mincc.tools.list_files import list_files
from mincc.tools.read_file import read_file
from mincc.tools.run_command import run_command
from mincc.tools.write_file import write_file


def test_list_files_ignores_common_dirs(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mincc").mkdir()
    (tmp_path / "mincc" / "agent.py").write_text("agent", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("secret", encoding="utf-8")

    result = list_files.invoke({"path": "."})

    assert "mincc/agent.py" in result
    assert ".git/config" not in result


def test_grep_finds_text_with_line_numbers(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "hello.py").write_text("print('hello')\nprint('mincc')\n", encoding="utf-8")

    result = grep.invoke({"pattern": "mincc", "path": "."})

    assert "hello.py:2:print('mincc')" in result


def test_grep_rejects_invalid_regex(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "hello.py").write_text("hello", encoding="utf-8")

    result = grep.invoke({"pattern": "[", "path": ".", "use_regex": True})

    assert result.startswith("ERROR: 正则表达式无效")


def test_read_file_rejects_paths_outside_project(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    monkeypatch.chdir(project)

    result = read_file.invoke({"path": str(outside)})

    assert result.startswith("ERROR: 路径不在当前项目目录内")


def test_read_file_rejects_sensitive_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("LLM_API_KEY=secret", encoding="utf-8")

    result = read_file.invoke({"path": ".env"})

    assert result.startswith("ERROR: 拒绝读取敏感文件")


def test_write_file_creates_new_file_without_confirmation(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = write_file.invoke({"path": "notes/todo.txt", "content": "hello"})

    assert result.startswith("OK: written")
    assert (tmp_path / "notes" / "todo.txt").read_text(encoding="utf-8") == "hello"


def test_write_file_requires_confirmation_for_overwrite(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "todo.txt"
    target.write_text("old", encoding="utf-8")

    result = write_file.invoke({"path": "todo.txt", "content": "new"})

    assert result.startswith("ERROR: 写入会覆盖已有文件")
    assert target.read_text(encoding="utf-8") == "old"


def test_edit_file_replaces_unique_text_when_confirmed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "app.py"
    target.write_text("name = 'old'\n", encoding="utf-8")

    result = edit_file.invoke(
        {
            "path": "app.py",
            "old_text": "name = 'old'",
            "new_text": "name = 'new'",
            "confirmed": True,
        }
    )

    assert result.startswith("OK: edited")
    assert target.read_text(encoding="utf-8") == "name = 'new'\n"


def test_edit_file_requires_confirmation(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("old", encoding="utf-8")

    result = edit_file.invoke({"path": "app.py", "old_text": "old", "new_text": "new"})

    assert result.startswith("ERROR: 编辑文件前必须先取得用户确认")


def test_edit_file_rejects_ambiguous_replacement(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("old\nold\n", encoding="utf-8")

    result = edit_file.invoke(
        {"path": "app.py", "old_text": "old", "new_text": "new", "confirmed": True}
    )

    assert result.startswith("ERROR: old_text 出现 2 次")


def test_run_command_requires_confirmation() -> None:
    result = run_command.invoke({"command": "uv run pytest -q"})

    assert result.startswith("ERROR: 执行命令前必须先取得用户确认")


def test_run_command_rejects_non_whitelisted_command() -> None:
    result = run_command.invoke({"command": "python --version", "confirmed": True})

    assert result.startswith("ERROR: 命令不在白名单内")
