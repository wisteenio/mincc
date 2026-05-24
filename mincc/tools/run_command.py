"""执行受限本地命令的工具。"""

from __future__ import annotations

import os
import shlex
import subprocess

from langchain_core.tools import tool

ALLOWED_COMMANDS = {
    ("uv", "run", "pytest", "-q"),
    ("uv", "run", "ruff", "check"),
    ("uv", "run", "mincc", "--help"),
}
MAX_TIMEOUT_SECONDS = 120


@tool
def run_command(command: str, confirmed: bool = False, timeout_seconds: int = 30) -> str:
    """在当前项目内执行白名单中的非破坏性命令。

    agent 必须先向用户说明要执行的命令并取得确认，再把 confirmed 设为 true。
    第一版只允许固定白名单命令，不支持任意 shell 语法、管道、重定向或命令拼接。

    Args:
        command: 要执行的命令，例如 "uv run pytest -q"。
        confirmed: 用户已确认执行命令时设为 true。
        timeout_seconds: 超时时间，上限 120 秒。

    Returns:
        命令退出码、stdout 与 stderr；失败时返回以 "ERROR: " 开头的错误说明。
    """
    if not confirmed:
        return "ERROR: 执行命令前必须先取得用户确认并设置 confirmed=true"

    try:
        parts = tuple(shlex.split(command, posix=os.name != "nt"))
    except ValueError as exc:
        return f"ERROR: 命令解析失败：{exc}"
    if parts not in ALLOWED_COMMANDS:
        allowed = "\n".join(" ".join(item) for item in sorted(ALLOWED_COMMANDS))
        return f"ERROR: 命令不在白名单内。允许的命令：\n{allowed}"

    timeout = max(1, min(timeout_seconds, MAX_TIMEOUT_SECONDS))
    try:
        completed = subprocess.run(  # noqa: S603
            parts,
            cwd=os.getcwd(),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return f"ERROR: 命令不存在：{exc.filename}"
    except subprocess.TimeoutExpired:
        return f"ERROR: 命令超时（{timeout} 秒）：{command}"
    except OSError as exc:
        return f"ERROR: 命令执行失败：{exc}"

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    sections = [f"exit_code: {completed.returncode}"]
    if stdout:
        sections.append(f"stdout:\n{stdout}")
    if stderr:
        sections.append(f"stderr:\n{stderr}")
    return "\n\n".join(sections)
