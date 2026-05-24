"""执行本地命令的工具。"""

from __future__ import annotations

import os
import shlex
import subprocess

from langchain_core.tools import tool

from mincc.permissions import is_cancelled, request_command_permission
from mincc.storage import MinccStorage

MAX_TIMEOUT_SECONDS = 120


@tool
def run_command(command: str, confirmed: bool = False, timeout_seconds: int = 30) -> str:
    """在当前项目内执行本地命令。

    运行命令属于高风险操作。agent 应先评估命令风险；除非用户已经明确授权，
    否则不要设置 confirmed=true。未授权命令会触发 CLI 权限选择。
    本工具不通过 shell 执行命令，因此不支持管道、重定向或命令拼接。

    Args:
        command: 要执行的命令，例如 "uv run pytest -q"。
        confirmed: 兼容参数；CLI 授权面板仍会决定是否执行命令。
        timeout_seconds: 超时时间，上限 120 秒。

    Returns:
        命令退出码、stdout 与 stderr；失败时返回以 "ERROR: " 开头的错误说明。
    """
    try:
        parts = tuple(shlex.split(command, posix=os.name != "nt"))
    except ValueError as exc:
        return f"ERROR: 命令解析失败：{exc}"
    normalized_command = " ".join(parts)
    storage = MinccStorage.create()
    if is_cancelled():
        return "已取消当前操作。"
    needs_permission = (
        not storage.read_allow_all_operations()
        and normalized_command not in storage.read_allowed_commands()
    )
    if needs_permission:
        decision = request_command_permission(normalized_command)
        if decision == "deny":
            return f"已取消执行命令：{normalized_command}"
        if decision == "always":
            storage.allow_command(normalized_command)
        if decision == "always_all":
            storage.allow_all_operations()
    if is_cancelled():
        return "已取消当前操作。"

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
