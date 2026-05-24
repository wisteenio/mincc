"""启动 mincc 并切换到临时测试项目目录。

用法：
    uv run python scripts/start_test_app.py

可选：
    uv run python scripts/start_test_app.py --workdir /path/to/sandbox
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


def _write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def prepare_sandbox(workdir: Path) -> Path:
    """创建一个可安全修改的最小 Python 项目。"""
    workdir.mkdir(parents=True, exist_ok=True)
    _write_if_missing(
        workdir / "README.md",
        "# mincc test sandbox\n\n这个目录用于手动测试 mincc 的读写和搜索能力。\n",
    )
    _write_if_missing(
        workdir / "hello.py",
        'def hello() -> str:\n    return "hello mincc"\n',
    )
    _write_if_missing(
        workdir / "test_hello.py",
        "from hello import hello\n"
        "\n"
        "\n"
        "def test_hello() -> None:\n"
        '    assert hello() == "hello mincc"\n',
    )
    return workdir.resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start mincc in a disposable test workdir.")
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "mincc-test-workdir",
        help="测试项目目录，默认位于系统临时目录",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="传给 mincc 的 .env 文件路径",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workdir = prepare_sandbox(args.workdir.expanduser())
    command = ["uv", "run", "mincc", "--workdir", str(workdir)]
    if args.env_file is not None:
        command.extend(["--env-file", str(args.env_file.expanduser())])
    print(f"Starting mincc in test workdir: {workdir}")
    return subprocess.call(command)  # noqa: S603


if __name__ == "__main__":
    raise SystemExit(main())
