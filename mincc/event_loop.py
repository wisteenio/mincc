"""mincc 事件主循环。

本模块负责把配置、模型、agent、UI 串起来，并维护一次交互会话的消息历史。
CLI 只负责解析命令行参数，不直接承载事件循环和会话状态。
"""

from __future__ import annotations

import ast
import json
import os
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from mincc.agent import build_agent
from mincc.commands import list_commands
from mincc.config import load_config
from mincc.llm import build_chat_model
from mincc.permissions import (
    CommandPermissionCallback,
    reset_cancel_event,
    reset_command_permission_callback,
    set_cancel_event,
    set_command_permission_callback,
)
from mincc.storage import MinccStorage
from mincc.tools import ALL_TOOLS
from mincc.ui import run_chat_ui

ProgressCallback = Callable[[str], None]
SubmitHandler = Callable[
    [str, ProgressCallback, CommandPermissionCallback | None, Event | None],
    str,
]
ChatUIRunner = Callable[[SubmitHandler, list[str]], None]
CANCELLED_CONTENT = "已取消当前操作。"


class _ProgressCallbackHandler(BaseCallbackHandler):
    """把 LangChain 执行阶段转成 UI 可展示的状态文案。"""

    def __init__(self, update_status: ProgressCallback) -> None:
        self.update_status = update_status
        self._tool_stack: list[str] = []

    def on_chat_model_start(self, serialized: dict[str, Any], messages: list, **kwargs) -> None:
        self.update_status("调用模型...")

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs) -> None:
        self.update_status("调用模型...")

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs) -> None:
        status = _format_tool_start_status(serialized, input_str, kwargs.get("inputs"))
        self._tool_stack.append(status.removeprefix("调用工具：").removesuffix("..."))
        self.update_status(status)

    def on_tool_end(self, output: Any, **kwargs) -> None:
        tool_label = self._tool_stack.pop() if self._tool_stack else "工具"
        self.update_status(f"工具完成：{tool_label}，处理结果...")

    def on_tool_error(self, error: BaseException, **kwargs) -> None:
        tool_label = self._tool_stack.pop() if self._tool_stack else "工具"
        self.update_status(f"工具失败：{tool_label}，处理错误...")


def _format_tool_start_status(
    serialized: dict[str, Any],
    input_str: str,
    inputs: Any = None,
) -> str:
    """生成包含工具名与关键参数的进度文案。"""
    tool_name = _tool_name(serialized)
    tool_input = _coerce_tool_input(inputs if inputs is not None else input_str)
    action = _tool_action(tool_name)
    target = _tool_target(tool_name, tool_input)
    if target:
        return f"调用工具：{action} {target}..."
    return f"调用工具：{action}..."


def _tool_name(serialized: dict[str, Any]) -> str:
    name = serialized.get("name")
    if isinstance(name, str) and name:
        return name
    identifier = serialized.get("id")
    if isinstance(identifier, list) and identifier:
        last = identifier[-1]
        if isinstance(last, str) and last:
            return last
    return "tool"


def _coerce_tool_input(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}

    stripped = value.strip()
    if not stripped:
        return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(stripped)
        except (SyntaxError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _tool_action(tool_name: str) -> str:
    actions = {
        "list_files": "列出文件",
        "grep": "搜索文本",
        "read_file": "读取文件",
        "write_file": "写入文件",
        "edit_file": "编辑文件",
        "run_command": "执行命令",
    }
    return actions.get(tool_name, tool_name)


def _tool_target(tool_name: str, tool_input: dict[str, Any]) -> str:
    if tool_name in {"read_file", "write_file", "edit_file", "list_files"}:
        return _short_value(tool_input.get("path"))
    if tool_name == "grep":
        pattern = _short_value(tool_input.get("pattern"))
        path = _short_value(tool_input.get("path"))
        if pattern and path:
            return f"{pattern} in {path}"
        return pattern or path
    if tool_name == "run_command":
        return _short_value(tool_input.get("command"))
    return ""


def _short_value(value: Any, max_length: int = 80) -> str:
    if not isinstance(value, str):
        return ""
    compact = " ".join(value.split())
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 1]}..."


def _iter_stream_updates(chunk: Any):
    if not isinstance(chunk, dict):
        return
    for node_name, node_update in chunk.items():
        if isinstance(node_name, str):
            yield node_name, node_update


def _messages_from_update(node_update: Any) -> list[BaseMessage]:
    if not isinstance(node_update, dict):
        return []
    messages = node_update.get("messages")
    if isinstance(messages, list) and all(isinstance(item, BaseMessage) for item in messages):
        return messages
    return []


def _merge_messages(
    existing: list[BaseMessage],
    update: list[BaseMessage],
) -> tuple[list[BaseMessage], list[BaseMessage]]:
    if _is_prefix(existing, update):
        return list(update), list(update[len(existing) :])
    return [*existing, *update], update


def _is_prefix(prefix: list[BaseMessage], messages: list[BaseMessage]) -> bool:
    if len(prefix) > len(messages):
        return False
    return all(left == right for left, right in zip(prefix, messages, strict=False))


def _report_model_update(
    messages: list[BaseMessage],
    tool_labels: dict[str, str],
    update_status: ProgressCallback,
) -> None:
    if not messages:
        return
    latest = messages[-1]
    if not isinstance(latest, AIMessage) or not latest.tool_calls:
        update_status("调用模型...")
        return

    for tool_call in latest.tool_calls:
        tool_name = tool_call.get("name", "tool")
        args = tool_call.get("args", {})
        status = _format_tool_start_status({"name": tool_name}, "", args)
        label = status.removeprefix("调用工具：").removesuffix("...")
        tool_call_id = tool_call.get("id")
        if isinstance(tool_call_id, str):
            tool_labels[tool_call_id] = label
        update_status(status)


def _report_tools_update(
    messages: list[BaseMessage],
    tool_labels: dict[str, str],
    update_status: ProgressCallback,
) -> None:
    for message in messages:
        tool_call_id = getattr(message, "tool_call_id", None)
        label = tool_labels.pop(tool_call_id, "工具") if isinstance(tool_call_id, str) else "工具"
        update_status(f"工具完成：{label}，处理结果...")


def _command_cancel_content(messages: list[BaseMessage]) -> str | None:
    for message in messages:
        content = message.content
        if isinstance(content, str) and (
            content.startswith("已取消执行命令：") or content == CANCELLED_CONTENT
        ):
            return content
    return None


def _is_cancelled(cancel_event: Event | None) -> bool:
    return bool(cancel_event and cancel_event.is_set())


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

    def submit(
        self,
        text: str,
        update_status: ProgressCallback | None = None,
        request_command_permission: CommandPermissionCallback | None = None,
        cancel_event: Event | None = None,
    ) -> str:
        """处理一条用户输入，返回最终 assistant 文本。"""
        update_status = update_status or (lambda _status: None)
        command_reply = self._handle_slash_command(text)
        if command_reply is not None:
            return command_reply

        update_status("准备调用模型...")
        self.storage.append_input(text)
        self.input_history.append(text)
        self.history.append(HumanMessage(content=text))
        command_permission_token = set_command_permission_callback(request_command_permission)
        cancel_token = set_cancel_event(cancel_event)
        try:
            result = self._invoke_agent(update_status, cancel_event)
        finally:
            reset_cancel_event(cancel_token)
            reset_command_permission_callback(command_permission_token)
        self.history[:] = list(result["messages"])

        final = self.history[-1]
        if isinstance(final, AIMessage):
            return str(final.content)
        return str(final)

    def _invoke_agent(
        self, update_status: ProgressCallback, cancel_event: Event | None = None
    ) -> dict:
        """执行 agent，并尽量从 LangGraph stream 中提取真实进度。"""
        state = {"messages": self.history}
        config = {"callbacks": [_ProgressCallbackHandler(update_status)]}
        if _is_cancelled(cancel_event):
            return {"messages": [*state["messages"], AIMessage(content=CANCELLED_CONTENT)]}
        stream = getattr(self.agent, "stream", None)
        if callable(stream):
            return self._stream_agent(state, config, update_status, cancel_event)
        result = self.agent.invoke(state, config=config)
        if _is_cancelled(cancel_event):
            return {"messages": [*state["messages"], AIMessage(content=CANCELLED_CONTENT)]}
        return result

    def _stream_agent(
        self,
        state: dict,
        config: dict,
        update_status: ProgressCallback,
        cancel_event: Event | None = None,
    ) -> dict:
        """消费 LangGraph updates stream，补齐工具调用进度。"""
        result_messages = list(state["messages"])
        tool_labels: dict[str, str] = {}
        for chunk in self.agent.stream(state, config=config, stream_mode="updates"):
            if _is_cancelled(cancel_event):
                return {"messages": [*state["messages"], AIMessage(content=CANCELLED_CONTENT)]}
            for node_name, node_update in _iter_stream_updates(chunk):
                if _is_cancelled(cancel_event):
                    return {"messages": [*state["messages"], AIMessage(content=CANCELLED_CONTENT)]}
                messages = _messages_from_update(node_update)
                if not messages:
                    continue
                result_messages, new_messages = _merge_messages(result_messages, messages)
                if node_name == "model":
                    _report_model_update(new_messages, tool_labels, update_status)
                elif node_name == "tools":
                    _report_tools_update(new_messages, tool_labels, update_status)
                    cancel_content = _command_cancel_content(new_messages)
                    if cancel_content is not None:
                        return {"messages": [*state["messages"], AIMessage(content=cancel_content)]}

        if len(result_messages) > len(state["messages"]):
            return {"messages": result_messages}
        return self.agent.invoke(state, config=config)

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
