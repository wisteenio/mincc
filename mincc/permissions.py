"""运行期权限请求通道。"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from threading import Event
from typing import Literal

CommandPermissionDecision = Literal["once", "always", "always_all", "deny"]
CommandPermissionCallback = Callable[[str], CommandPermissionDecision]
CancelCheck = Callable[[], bool]

_command_permission_callback: ContextVar[CommandPermissionCallback | None] = ContextVar(
    "command_permission_callback",
    default=None,
)
_cancel_event: ContextVar[Event | None] = ContextVar("cancel_event", default=None)


def set_command_permission_callback(callback: CommandPermissionCallback | None):
    """设置当前 agent 调用期间使用的命令授权回调。"""
    return _command_permission_callback.set(callback)


def reset_command_permission_callback(token) -> None:
    """恢复命令授权回调。"""
    _command_permission_callback.reset(token)


def request_command_permission(command: str) -> CommandPermissionDecision:
    """请求用户授权执行命令；没有交互回调时默认拒绝。"""
    callback = _command_permission_callback.get()
    if callback is None:
        return "deny"
    return callback(command)


def set_cancel_event(cancel_event: Event | None):
    """设置当前 agent 调用期间使用的取消事件。"""
    return _cancel_event.set(cancel_event)


def reset_cancel_event(token) -> None:
    """恢复取消事件。"""
    _cancel_event.reset(token)


def is_cancelled() -> bool:
    """当前 agent 调用是否已被用户取消。"""
    cancel_event = _cancel_event.get()
    return bool(cancel_event and cancel_event.is_set())
