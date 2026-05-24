"""mincc 命令行入口。

子命令：
- chat：交互式 REPL（默认）
- run "<prompt>"：单次执行模式，便于脚本调用
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
    no_args_is_help=False,
)
console = Console()


def _build_runtime(env_file: Path | None):
    """统一加载配置并构建 agent。"""
    config = load_config(env_file)
    model = build_chat_model(config)
    return build_agent(model)


def _print_ai(text: str) -> None:
    console.print(Panel(Markdown(text), title="mincc", border_style="cyan"))


@app.callback(invoke_without_command=True)
def _default(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="显示版本号并退出"),
) -> None:
    if version:
        console.print(f"mincc {__version__}")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        # 不带子命令时默认进入 chat
        ctx.invoke(chat)


@app.command()
def run(
    prompt: str = typer.Argument(..., help="一次性提示词，模型回复后退出"),
    env_file: Path | None = typer.Option(
        None, "--env-file", help="自定义 .env 文件路径"
    ),
) -> None:
    """单次执行模式：发送一条消息，输出模型回复后退出。"""
    agent = _build_runtime(env_file)
    result = agent.invoke({"messages": [HumanMessage(content=prompt)]})
    final = result["messages"][-1]
    if isinstance(final, AIMessage):
        _print_ai(str(final.content))
    else:
        console.print(final)


@app.command()
def chat(
    env_file: Path | None = typer.Option(
        None, "--env-file", help="自定义 .env 文件路径"
    ),
) -> None:
    """交互式 REPL：输入 /exit 退出。"""
    agent = _build_runtime(env_file)
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
