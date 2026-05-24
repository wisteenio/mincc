"""mincc 命令行入口：单一交互模式。

`uv run mincc` 直接进入 REPL，输入 /exit 退出。
"""

from __future__ import annotations

from pathlib import Path

import typer
from langchain_core.messages import AIMessage, HumanMessage
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from mincc import __version__
from mincc.agent import build_agent
from mincc.config import load_config
from mincc.llm import build_chat_model

app = typer.Typer(
    name="mincc",
    help="mini claude code —— 基于 LangChain / LangGraph 的命令行 AI Agent",
    add_completion=False,
)
console = Console()


def _print_ai(text: str) -> None:
    console.print(Panel(Markdown(text), title="mincc", border_style="cyan"))


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"mincc {__version__}")
        raise typer.Exit(0)


@app.command()
def chat(
    env_file: Path | None = typer.Option(
        None, "--env-file", help="自定义 .env 文件路径"
    ),
    _version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="显示版本号并退出",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """交互式 REPL：输入 /exit 退出。"""
    config = load_config(env_file)
    model = build_chat_model(config)
    agent = build_agent(model)

    console.print(
        Panel.fit(
            "进入 mincc 交互模式，输入 [bold]/exit[/bold] 退出",
            border_style="green",
        )
    )

    history: list = []
    while True:
        try:
            user_input = console.input("[bold green]你 ›[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n再见。")
            return

        if not user_input:
            continue
        if user_input in {"/exit", "/quit"}:
            console.print("再见。")
            return

        history.append(HumanMessage(content=user_input))
        result = agent.invoke({"messages": history})
        history = result["messages"]
        final = history[-1]
        if isinstance(final, AIMessage):
            _print_ai(str(final.content))


if __name__ == "__main__":
    app()
