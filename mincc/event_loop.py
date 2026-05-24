"""mincc 事件主循环。

本模块负责把配置、模型、agent、UI 串起来，并维护一次交互会话的消息历史。
CLI 只负责解析命令行参数，不直接承载事件循环和会话状态。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from mincc.agent import build_agent
from mincc.commands import list_commands
from mincc.config import load_config
from mincc.llm import build_chat_model
from mincc.storage import MinccStorage
from mincc.tools import ALL_TOOLS
from mincc.ui import run_chat_ui

ProgressCallback = Callable[[str], None]
SubmitHandler = Callable[[str, ProgressCallback], str]
ChatUIRunner = Callable[[SubmitHandler, list[str]], None]


class _ProgressCallbackHandler(BaseCallbackHandler):
    """把 LangChain 执行阶段转成 UI 可展示的状态文案。"""

    def __init__(self, update_status: ProgressCallback) -> None:
        self.update_status = update_status

    def on_chat_model_start(self, serialized: dict[str, Any], messages: list, **kwargs) -> None:
        self.update_status("调用模型...")

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs) -> None:
        self.update_status("调用模型...")

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs) -> None:
        self.update_status("执行工具...")

    def on_tool_end(self, output: Any, **kwargs) -> None:
        self.update_status("处理工具结果...")


class EventLoop:
    """一次 mincc 交互会话的主循环。

    当前 UI 层仍以同步回调方式提交用户输入；事件循环封装这层回调背后的
    消息历史更新与 agent 调用，避免把这些流程散落在 CLI 中。
    """

    def __init__(
        self,
        agent: Any,
        ui_runner: ChatUIRunner = run_chat_ui,
        storage: MinccStorage | None = None,
    ) -> None:
        self.agent = agent
        self.ui_runner = ui_runner
        self.storage = storage or MinccStorage.create()
        self.history: list[BaseMessage] = []
        self.input_history = self.storage.read_inputs()

    def submit(self, text: str, update_status: ProgressCallback | None = None) -> str:
        """处理一条用户输入，返回最终 assistant 文本。"""
        update_status = update_status or (lambda _status: None)
        command_reply = self._handle_slash_command(text)
        if command_reply is not None:
            return command_reply

        update_status("准备调用模型...")
        self.storage.append_input(text)
        self.input_history.append(text)
        self.history.append(HumanMessage(content=text))
        result = self.agent.invoke(
            {"messages": self.history},
            config={"callbacks": [_ProgressCallbackHandler(update_status)]},
        )
        self.history[:] = list(result["messages"])

        final = self.history[-1]
        if isinstance(final, AIMessage):
            return str(final.content)
        return str(final)

    def _handle_slash_command(self, text: str) -> str | None:
        """处理不需要进入 LLM 的内置斜杠命令。"""
        stripped = text.strip()
        command = stripped.lower()
        if command == "/clear":
            self.history.clear()
            return "已清空当前会话历史。"
        if command == "/pwd":
            return str(Path.cwd())
        if command.startswith("/cd"):
            return self._change_workdir(stripped)
        if command == "/help":
            commands = "\n".join(f"- /{cmd.name}: {cmd.summary}" for cmd in list_commands())
            tools = "\n".join(
                f"- {tool.name}: {tool.description.splitlines()[0]}" for tool in ALL_TOOLS
            )
            return f"可用命令：\n{commands}\n\n可用工具：\n{tools}"
        return None

    def _change_workdir(self, command: str) -> str:
        """切换当前进程工作目录，并让项目级输入历史跟随新目录。"""
        parts = command.split(maxsplit=1)
        if len(parts) == 1:
            return "ERROR: 用法：/cd <path>"

        target = Path(parts[1]).expanduser()
        if not target.is_absolute():
            target = Path.cwd() / target
        try:
            resolved = target.resolve(strict=True)
        except FileNotFoundError:
            return f"ERROR: 目录不存在：{target}"
        except OSError as exc:
            return f"ERROR: 无法解析目录：{target}：{exc}"
        if not resolved.is_dir():
            return f"ERROR: 路径不是目录：{resolved}"

        os.chdir(resolved)
        self.storage = MinccStorage.create(root=self.storage.root, project_path=resolved)
        self.input_history = self.storage.read_inputs()
        self.history.clear()
        return f"已切换当前工作目录：{resolved}\n当前会话历史已清空。"

    def run(self) -> None:
        """启动 UI，并将用户输入交给事件循环处理。"""
        self.ui_runner(self.submit, self.input_history)


def build_event_loop(env_file: Path | None = None, workdir: Path | None = None) -> EventLoop:
    """根据运行配置创建事件主循环。"""
    config = load_config(env_file)
    if workdir is not None:
        os.chdir(workdir.expanduser().resolve(strict=True))
    model = build_chat_model(config)
    agent = build_agent(model)
    return EventLoop(agent)


def run_event_loop(env_file: Path | None = None, workdir: Path | None = None) -> None:
    """创建并运行事件主循环。"""
    build_event_loop(env_file, workdir).run()
