"""搜索项目文本内容的工具。"""

from __future__ import annotations

import re

from langchain_core.tools import tool

from mincc.tools.safety import is_ignored, is_sensitive_path, project_root, resolve_project_path

MAX_FILE_BYTES = 1024 * 1024
MAX_MATCHES = 200


@tool
def grep(pattern: str, path: str = ".", use_regex: bool = False, max_matches: int = 50) -> str:
    """在当前项目内搜索文本内容。

    Args:
        pattern: 要搜索的文本或正则表达式。
        path: 搜索范围，必须位于当前项目内；可为文件或目录。
        use_regex: 为 true 时按正则表达式搜索，否则按普通文本搜索。
        max_matches: 最多返回多少条匹配，上限为 200。

    Returns:
        "文件:行号:内容" 格式的匹配列表；失败时返回以 "ERROR: " 开头的错误说明。
    """
    if not pattern:
        return "ERROR: pattern 不能为空"
    target, error = resolve_project_path(path, must_exist=True)
    if error is not None or target is None:
        return error or "ERROR: 无法解析路径"

    try:
        regex = re.compile(pattern) if use_regex else None
    except re.error as exc:
        return f"ERROR: 正则表达式无效：{exc}"

    root = project_root()
    limit = max(1, min(max_matches, MAX_MATCHES))
    if target.is_file():
        candidates = [target]
    else:
        candidates = sorted(p for p in target.rglob("*") if p.is_file())
    matches: list[str] = []

    for file_path in candidates:
        rel_path = file_path.relative_to(root)
        if is_ignored(rel_path) or is_sensitive_path(file_path):
            continue
        try:
            if file_path.stat().st_size > MAX_FILE_BYTES:
                continue
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for lineno, line in enumerate(lines, start=1):
            found = bool(regex.search(line)) if regex is not None else pattern in line
            if found:
                matches.append(f"{rel_path.as_posix()}:{lineno}:{line.strip()}")
                if len(matches) >= limit:
                    return "\n".join(matches) + "\n...（结果过多，已截断）"

    return "\n".join(matches) if matches else "(no matches)"
