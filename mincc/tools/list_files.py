"""列出项目文件的工具。"""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from mincc.tools.safety import DEFAULT_IGNORED_DIRS, is_ignored, project_root, resolve_project_path

MAX_RESULTS = 500


@tool
def list_files(path: str = ".", max_results: int = 200) -> str:
    """列出当前项目内的文件。

    Args:
        path: 要列出的目录路径，必须位于当前项目内。
        max_results: 最多返回多少个文件路径，上限为 500。

    Returns:
        相对项目根目录的文件路径列表；失败时返回以 "ERROR: " 开头的错误说明。
    """
    target, error = resolve_project_path(path, must_exist=True)
    if error is not None or target is None:
        return error or "ERROR: 无法解析路径"
    if not target.is_dir():
        return f"ERROR: 路径不是目录：{target}"

    root = project_root()
    limit = max(1, min(max_results, MAX_RESULTS))
    files: list[str] = []
    for item in sorted(target.rglob("*")):
        if is_ignored(item.relative_to(root), DEFAULT_IGNORED_DIRS):
            continue
        if item.is_file():
            files.append(Path(item).relative_to(root).as_posix())
            if len(files) >= limit:
                break

    if not files:
        return "(no files)"
    suffix = "\n...（结果过多，已截断）" if len(files) >= limit else ""
    return "\n".join(files) + suffix
