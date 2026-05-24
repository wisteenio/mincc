"""mincc 命令行入口：单一交互模式。

`uv run mincc` 直接进入全屏 TUI，输入 /exit 或 Ctrl-C 退出。
"""

from __future__ import annotations

from pathlib import Path

import typer
from langchain_core.messages import AIMessage, HumanMessage

from mincc import __version__
from mincc.agent import build_agent
from mincc.config import load_config
from mincc.llm import build_chat_model
from mincc.ui import run_chat_ui

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
    config = load_config(env_file)
    model = build_chat_model(config)
    agent = build_agent(model)

    history: list = []

    def on_submit(text: str) -> str:
        history.append(HumanMessage(content=text))
        result = agent.invoke({"messages": history})
        history[:] = result["messages"]
        final = history[-1]
        if isinstance(final, AIMessage):
            return str(final.content)
        return str(final)

    run_chat_ui(on_submit)


if __name__ == "__main__":
    app()
