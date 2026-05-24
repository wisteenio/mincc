"""mincc 事件主循环。

本模块负责把配置、模型、agent、UI 串起来，并维护一次交互会话的消息历史。
CLI 只负责解析命令行参数，不直接承载事件循环和会话状态。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from mincc.agent import build_agent
from mincc.config import load_config
from mincc.llm import build_chat_model
from mincc.ui import run_chat_ui

ChatUIRunner = Callable[[Callable[[str], str]], None]


class EventLoop:
    """一次 mincc 交互会话的主循环。

    当前 UI 层仍以同步回调方式提交用户输入；事件循环封装这层回调背后的
    消息历史更新与 agent 调用，避免把这些流程散落在 CLI 中。
    """

    def __init__(self, agent: Any, ui_runner: ChatUIRunner = run_chat_ui) -> None:
        self.agent = agent
        self.ui_runner = ui_runner
        self.history: list[BaseMessage] = []

    def submit(self, text: str) -> str:
        """处理一条用户输入，返回最终 assistant 文本。"""
        self.history.append(HumanMessage(content=text))
        result = self.agent.invoke({"messages": self.history})
        self.history[:] = list(result["messages"])

        final = self.history[-1]
        if isinstance(final, AIMessage):
            return str(final.content)
        return str(final)

    def run(self) -> None:
        """启动 UI，并将用户输入交给事件循环处理。"""
        self.ui_runner(self.submit)


def build_event_loop(env_file: Path | None = None) -> EventLoop:
    """根据运行配置创建事件主循环。"""
    config = load_config(env_file)
    model = build_chat_model(config)
    agent = build_agent(model)
    return EventLoop(agent)


def run_event_loop(env_file: Path | None = None) -> None:
    """创建并运行事件主循环。"""
    build_event_loop(env_file).run()
