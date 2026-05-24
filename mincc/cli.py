"""mincc 命令行入口：单一交互模式。

`uv run mincc` 直接进入全屏 TUI，输入 /exit 或 Ctrl-C 退出。
"""

from __future__ import annotations

from pathlib import Path

import typer

from mincc import __version__
from mincc.event_loop import run_event_loop

app = typer.Typer(
    name="mincc",
    help="基于 LangChain/LangGraph 实现的最小版本的 Claude Code",
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"mincc {__version__}")
        raise typer.Exit(0)


@app.command()
def chat(
    env_file: Path | None = typer.Option(  # noqa: B008
        None, "--env-file", help="自定义 .env 文件路径"
    ),
    _version: bool = typer.Option(  # noqa: B008
        False,
        "--version",
        "-V",
        help="显示版本号并退出",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """全屏交互模式：底部输入，上方滚动历史。"""
    run_event_loop(env_file)


if __name__ == "__main__":
    app()
