"""精确替换编辑项目文件的工具。"""

from __future__ import annotations

from langchain_core.tools import tool

from mincc.tools.safety import is_sensitive_path, resolve_project_path


@tool
def edit_file(
    path: str,
    old_text: str,
    new_text: str,
    replace_all: bool = False,
    confirmed: bool = False,
) -> str:
    """在当前项目内用精确文本替换编辑文件。

    agent 必须先读取文件并确认 old_text 来自当前文件内容；修改前要向用户说明
    将改动的文件，取得确认后再把 confirmed 设为 true 调用本工具。

    Args:
        path: 要编辑的文件路径，必须位于当前项目内。
        old_text: 要替换的原始文本，必须精确匹配。
        new_text: 替换后的文本。
        replace_all: 为 true 时替换所有匹配，否则要求 old_text 只出现一次。
        confirmed: 用户已确认修改时设为 true。

    Returns:
        编辑结果；失败时返回以 "ERROR: " 开头的错误说明。
    """
    if not old_text:
        return "ERROR: old_text 不能为空"
    if not confirmed:
        return "ERROR: 编辑文件前必须先取得用户确认并设置 confirmed=true"

    target, error = resolve_project_path(path, must_exist=True)
    if error is not None or target is None:
        return error or "ERROR: 无法解析路径"
    if not target.is_file():
        return f"ERROR: 路径不是文件：{target}"
    if is_sensitive_path(target):
        return f"ERROR: 拒绝编辑敏感文件：{target}"

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"ERROR: 文件不是 UTF-8 文本：{target}"
    except OSError as exc:
        return f"ERROR: 读取失败：{exc}"

    count = content.count(old_text)
    if count == 0:
        return "ERROR: old_text 未在文件中找到"
    if count > 1 and not replace_all:
        return f"ERROR: old_text 出现 {count} 次；请提供更精确上下文或设置 replace_all=true"

    if replace_all:
        updated = content.replace(old_text, new_text)
    else:
        updated = content.replace(old_text, new_text, 1)
    try:
        target.write_text(updated, encoding="utf-8")
    except OSError as exc:
        return f"ERROR: 写入失败：{exc}"

    changed = count if replace_all else 1
    return f"OK: edited {target} ({changed} replacement{'s' if changed != 1 else ''})"
