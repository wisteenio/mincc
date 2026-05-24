"""工具层共享安全校验。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

DEFAULT_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "build",
    "dist",
    "__pycache__",
    "node_modules",
}
SENSITIVE_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".netrc",
}
SENSITIVE_SUFFIXES = {
    ".key",
    ".pem",
    ".p12",
    ".pfx",
}


def project_root() -> Path:
    """返回当前工具调用允许访问的项目根目录。"""
    return Path.cwd().resolve()


def resolve_project_path(path: str, *, must_exist: bool = False) -> tuple[Path | None, str | None]:
    """把用户路径解析到项目内；失败时返回错误文案。"""
    root = project_root()
    raw = Path(path).expanduser()
    candidate = raw if raw.is_absolute() else root / raw

    try:
        resolved = candidate.resolve(strict=must_exist)
    except FileNotFoundError:
        return None, f"ERROR: 路径不存在：{candidate}"
    except OSError as exc:
        return None, f"ERROR: 无法解析路径：{candidate}：{exc}"

    try:
        resolved.relative_to(root)
    except ValueError:
        return None, f"ERROR: 路径不在当前项目目录内：{resolved}"

    return resolved, None


def is_sensitive_path(path: Path) -> bool:
    """判断路径是否像凭据或密钥文件。"""
    name = path.name.lower()
    return name in SENSITIVE_FILENAMES or any(
        name.endswith(suffix) for suffix in SENSITIVE_SUFFIXES
    )


def is_ignored(path: Path, ignored_dirs: Iterable[str] = DEFAULT_IGNORED_DIRS) -> bool:
    """判断路径是否位于常见忽略目录中。"""
    ignored = set(ignored_dirs)
    return any(part in ignored for part in path.parts)
