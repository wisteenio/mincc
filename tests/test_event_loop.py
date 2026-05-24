"""事件主循环测试：不调用真实模型或 TUI。"""

from pathlib import Path
from threading import Event

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mincc.event_loop import EventLoop
from mincc.storage import MinccStorage


class FakeAgent:
    def __init__(self) -> None:
        self.calls: list[list] = []
        self.configs: list[dict | None] = []

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        messages = list(state["messages"])
        self.calls.append(messages)
        self.configs.append(config)
        return {"messages": [*messages, AIMessage(content=f"echo: {messages[-1].content}")]}


class ToolCallbackAgent:
    def invoke(self, state: dict, config: dict | None = None) -> dict:
        messages = list(state["messages"])
        callbacks = config["callbacks"]
        for callback in callbacks:
            callback.on_chat_model_start({}, [messages])
            callback.on_tool_start(
                {"name": "write_file"},
                '{"path": "notes/todo.txt", "content": "hello"}',
            )
            callback.on_tool_end("OK: written notes/todo.txt")
        return {"messages": [*messages, AIMessage(content="done")]}


class ToolStreamAgent:
    def stream(self, state: dict, config: dict | None = None, stream_mode: str | None = None):
        assert stream_mode == "updates"
        yield {
            "model": {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "write_file",
                                "args": {"path": "notes/todo.txt", "content": "hello"},
                                "id": "call_1",
                            }
                        ],
                    )
                ]
            }
        }
        yield {
            "tools": {
                "messages": [
                    ToolMessage(content="OK: written notes/todo.txt", tool_call_id="call_1")
                ]
            }
        }
        yield {"model": {"messages": [AIMessage(content="done")]}}

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        raise AssertionError("stream should be used")


class CancelledCommandStreamAgent:
    def __init__(self) -> None:
        self.reached_second_model = False

    def stream(self, state: dict, config: dict | None = None, stream_mode: str | None = None):
        assert stream_mode == "updates"
        yield {
            "model": {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "run_command",
                                "args": {"command": "mvn spring-boot:run"},
                                "id": "call_1",
                            }
                        ],
                    )
                ]
            }
        }
        yield {
            "tools": {
                "messages": [
                    ToolMessage(
                        content="已取消执行命令：mvn spring-boot:run",
                        tool_call_id="call_1",
                    )
                ]
            }
        }
        self.reached_second_model = True
        yield {"model": {"messages": [AIMessage(content="不应该生成这条回复")]}}

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        raise AssertionError("stream should be used")


def test_event_loop_submit_updates_history_and_returns_ai_content(tmp_path) -> None:
    agent = FakeAgent()
    storage = MinccStorage.create(root=tmp_path, project_id="test-project")
    loop = EventLoop(agent, storage=storage)

    reply = loop.submit("你好")

    assert reply == "echo: 你好"
    assert len(agent.calls) == 1
    assert isinstance(agent.calls[0][0], HumanMessage)
    assert agent.calls[0][0].content == "你好"
    assert [m.content for m in loop.history] == ["你好", "echo: 你好"]
    assert loop.input_history == ["你好"]
    assert storage.read_inputs() == ["你好"]
    assert agent.configs[0] is not None
    assert agent.configs[0]["callbacks"]


def test_event_loop_submit_reports_initial_status(tmp_path) -> None:
    statuses: list[str] = []
    loop = EventLoop(
        FakeAgent(),
        storage=MinccStorage.create(root=tmp_path, project_id="test-project"),
    )

    loop.submit("你好", statuses.append)

    assert statuses[0] == "准备调用模型..."


def test_event_loop_submit_reports_tool_progress(tmp_path) -> None:
    statuses: list[str] = []
    loop = EventLoop(
        ToolCallbackAgent(),
        storage=MinccStorage.create(root=tmp_path, project_id="test-project"),
    )

    loop.submit("写一个文件", statuses.append)

    assert statuses == [
        "准备调用模型...",
        "调用模型...",
        "调用工具：写入文件 notes/todo.txt...",
        "工具完成：写入文件 notes/todo.txt，处理结果...",
    ]


def test_event_loop_stream_reports_tool_progress_and_preserves_history(tmp_path) -> None:
    statuses: list[str] = []
    loop = EventLoop(
        ToolStreamAgent(),
        storage=MinccStorage.create(root=tmp_path, project_id="test-project"),
    )

    reply = loop.submit("写一个文件", statuses.append)

    assert reply == "done"
    assert statuses == [
        "准备调用模型...",
        "调用工具：写入文件 notes/todo.txt...",
        "工具完成：写入文件 notes/todo.txt，处理结果...",
        "调用模型...",
    ]
    assert [message.content for message in loop.history] == [
        "写一个文件",
        "",
        "OK: written notes/todo.txt",
        "done",
    ]


def test_event_loop_stops_after_command_permission_denied(tmp_path) -> None:
    agent = CancelledCommandStreamAgent()
    statuses: list[str] = []
    loop = EventLoop(
        agent,
        storage=MinccStorage.create(root=tmp_path, project_id="test-project"),
    )

    reply = loop.submit("运行服务", statuses.append)

    assert reply == "已取消执行命令：mvn spring-boot:run"
    assert not agent.reached_second_model
    assert [message.content for message in loop.history] == [
        "运行服务",
        "已取消执行命令：mvn spring-boot:run",
    ]
    assert statuses == [
        "准备调用模型...",
        "调用工具：执行命令 mvn spring-boot:run...",
        "工具完成：执行命令 mvn spring-boot:run，处理结果...",
    ]


def test_event_loop_returns_cancelled_when_cancel_event_is_set(tmp_path) -> None:
    cancel_event = Event()
    cancel_event.set()
    agent = FakeAgent()
    loop = EventLoop(
        agent,
        storage=MinccStorage.create(root=tmp_path, project_id="test-project"),
    )

    reply = loop.submit("你好", cancel_event=cancel_event)

    assert reply == "已取消当前操作。"
    assert agent.calls == []
    assert [message.content for message in loop.history] == ["你好", "已取消当前操作。"]


def test_event_loop_help_command_does_not_call_agent_or_store_input(tmp_path) -> None:
    agent = FakeAgent()
    storage = MinccStorage.create(root=tmp_path, project_id="test-project")
    loop = EventLoop(agent, storage=storage)

    reply = loop.submit("/help")

    assert "可用命令" in reply
    assert "/clear" in reply
    assert "可用工具" not in reply
    assert agent.calls == []
    assert loop.history == []
    assert storage.read_inputs() == []


def test_event_loop_clear_command_clears_in_memory_history(tmp_path) -> None:
    storage = MinccStorage.create(root=tmp_path, project_id="test-project")
    loop = EventLoop(FakeAgent(), storage=storage)
    loop.submit("你好")

    reply = loop.submit("/clear")

    assert reply == "已清空当前会话历史。"
    assert loop.history == []
    assert storage.read_inputs() == ["你好"]


def test_event_loop_pwd_command_returns_current_workdir(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    loop = EventLoop(
        FakeAgent(),
        storage=MinccStorage.create(root=tmp_path / "store", project_id="test-project"),
    )

    assert loop.submit("/pwd") == str(tmp_path)


def test_event_loop_cd_command_changes_workdir_and_clears_history(tmp_path, monkeypatch) -> None:
    start = tmp_path / "start"
    target = tmp_path / "target"
    start.mkdir()
    target.mkdir()
    monkeypatch.chdir(start)
    storage = MinccStorage.create(root=tmp_path / "store", project_id="start-project")
    loop = EventLoop(FakeAgent(), storage=storage)
    loop.history.append(HumanMessage(content="previous"))

    reply = loop.submit(f"/cd {target}")

    assert "已切换当前工作目录" in reply
    assert Path.cwd() == target
    assert loop.history == []
    assert loop.storage.root == tmp_path / "store"
    assert loop.storage.project_id.endswith("target")


def test_event_loop_cd_command_rejects_missing_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    loop = EventLoop(
        FakeAgent(),
        storage=MinccStorage.create(root=tmp_path / "store", project_id="test-project"),
    )

    reply = loop.submit("/cd missing")

    assert reply.startswith("ERROR: 目录不存在")
    assert Path.cwd() == tmp_path


def test_event_loop_run_delegates_to_ui_runner(tmp_path) -> None:
    seen: list[str] = []
    seen_history: list[str] = []

    def ui_runner(on_submit, input_history) -> None:
        seen_history.extend(input_history)
        seen.append(on_submit("ping", lambda _status: None))

    storage = MinccStorage.create(root=tmp_path, project_id="test-project")
    storage.append_input("previous")
    loop = EventLoop(FakeAgent(), ui_runner=ui_runner, storage=storage)

    loop.run()

    assert seen_history == ["previous"]
    assert seen == ["echo: ping"]
