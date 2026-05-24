"""斜杠命令注册表。

目前只包含内置命令（如 /exit），未来 custom skill 也通过此入口聚合。

设计目标：
- UI 只与 list_commands() 交互，不关心命令来源（内置/自定义）。
- 命令本身的执行暂不在此处理，先只做元数据展示和补全。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    """斜杠命令元数据。

    name: 不带前导斜杠的命令名，如 "exit"。
    summary: 一行简介，用于补全菜单的右侧说明。
    aliases: 别名列表（不含前导斜杠），可为空。
    source: "builtin" | "skill"，用于未来区分来源。
    """

    name: str
    summary: str
    aliases: tuple[str, ...] = ()
    source: str = "builtin"

    @property
    def display(self) -> str:
        """补全菜单中显示的命令文本（带斜杠）。"""
        return f"/{self.name}"


BUILTIN_COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand(name="exit", summary="退出 mincc", aliases=("quit",)),
    SlashCommand(name="help", summary="显示可用命令"),
    SlashCommand(name="clear", summary="清空当前会话历史"),
)


def list_commands() -> list[SlashCommand]:
    """返回当前可用的所有斜杠命令。

    后续接入 skill 时，在此处合并扫描结果。
    """
    return list(BUILTIN_COMMANDS)


def match_commands(text: str) -> list[SlashCommand]:
    """根据当前输入行返回应展示的命令列表。

    规则：
    - 不以 `/` 开头：返回空。
    - 行内含空格：说明已经在写参数，不再做命令名补全，返回空。
    - 否则按命令名/别名前缀匹配（大小写不敏感），保留 list_commands() 顺序。
      若一个命令的多个名字都命中，仅保留一份（以主名为准）。
    """
    if not text.startswith("/"):
        return []
    if " " in text:
        return []
    prefix = text[1:].lower()
    out: list[SlashCommand] = []
    for cmd in list_commands():
        names = (cmd.name, *cmd.aliases)
        if any(n.lower().startswith(prefix) for n in names):
            out.append(cmd)
    return out


def matched_name(cmd: SlashCommand, text: str) -> str:
    """在 `text` 这个输入下，命令实际命中的名字（可能是主名或别名）。

    用于补全后写回输入框：用户输入 `/qu` 命中 `quit` 别名，应补成 `/quit `。
    若没有任何名字命中（理论上不会发生，因为已经 match 过了），退化到主名。
    """
    prefix = text[1:].lower() if text.startswith("/") else text.lower()
    for n in (cmd.name, *cmd.aliases):
        if n.lower().startswith(prefix):
            return n
    return cmd.name
