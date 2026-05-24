"""写入项目文件的工具。"""

from __future__ import annotations

from langchain_core.tools import tool

from mincc.tools.safety import is_sensitive_path, resolve_project_path


@tool
def write_file(path: str, content: str, confirmed: bool = False) -> str:
    """在当前项目内写入文本文件。

    覆盖已有文件或写入敏感文件前，agent 必须先向用户说明影响并取得确认，
    再把 confirmed 设为 true 调用本工具。

    Args:
        path: 要写入的文件路径，必须位于当前项目内。
        content: 要写入的 UTF-8 文本内容。
        confirmed: 用户已确认覆盖已有文件或敏感文件时设为 true。

    Returns:
        写入结果；失败时返回以 "ERROR: " 开头的错误说明。
    """
    target, error = resolve_project_path(path, must_exist=False)
    if error is not None or target is None:
        return error or "ERROR: 无法解析路径"
    existed = target.exists()
    if existed and target.is_dir():
        return f"ERROR: 路径是目录，不能写入文件：{target}"
    if (existed or is_sensitive_path(target)) and not confirmed:
        return "ERROR: 写入会覆盖已有文件或触及敏感文件，必须先取得用户确认并设置 confirmed=true"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"ERROR: 写入失败：{exc}"

    action = "updated" if existed else "written"
    return f"OK: {action} {target}"
