"""LangChain v1 Agent 装配。

当前用 langchain.agents.create_agent（LangChain v1 推荐入口）快速搭起来。未来需要：
- 接入 checkpointer 做多轮对话持久化
- 自定义 StateGraph 加入历史压缩、subagent、权限确认等
只需修改本文件，CLI 与工具系统不受影响。
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from mincc.prompts import SYSTEM_PROMPT
from mincc.tools import ALL_TOOLS


def build_agent(
    model: BaseChatModel,
    tools: list[BaseTool] | None = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> CompiledStateGraph:
    """根据传入的 chat model 与工具集构建一个 ReAct agent。"""
    return create_agent(
        model=model,
        tools=tools if tools is not None else ALL_TOOLS,
        system_prompt=system_prompt,
    )
