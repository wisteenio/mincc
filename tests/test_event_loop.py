"""事件主循环测试：不调用真实模型或 TUI。"""

from langchain_core.messages import AIMessage, HumanMessage

from mincc.event_loop import EventLoop


class FakeAgent:
    def __init__(self) -> None:
        self.calls: list[list] = []

    def invoke(self, state: dict) -> dict:
        messages = list(state["messages"])
        self.calls.append(messages)
        return {"messages": [*messages, AIMessage(content=f"echo: {messages[-1].content}")]}


def test_event_loop_submit_updates_history_and_returns_ai_content() -> None:
    agent = FakeAgent()
    loop = EventLoop(agent)

    reply = loop.submit("你好")

    assert reply == "echo: 你好"
    assert len(agent.calls) == 1
    assert isinstance(agent.calls[0][0], HumanMessage)
    assert agent.calls[0][0].content == "你好"
    assert [m.content for m in loop.history] == ["你好", "echo: 你好"]


def test_event_loop_run_delegates_to_ui_runner() -> None:
    seen: list[str] = []

    def ui_runner(on_submit) -> None:
        seen.append(on_submit("ping"))

    loop = EventLoop(FakeAgent(), ui_runner=ui_runner)

    loop.run()

    assert seen == ["echo: ping"]
