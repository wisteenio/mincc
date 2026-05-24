# CLAUDE.md

本文件为 Claude Code（以及任何兼容的 AI 编程助手）协作此项目时的指令。

## 项目概览

mincc 是一个用 Python 3.12 实现的命令行 AI Agent，基于 LangChain / LangGraph，定位是"mini claude code"——一个可逐步演进、最终能本地化部署成可执行文件的轻量 agent。

## 技术栈

- **Python**：3.12（见 `.python-version`）
- **依赖管理**：[uv](https://docs.astral.sh/uv/)，所有命令以 `uv run ...` 形式调用
- **核心库**：langchain、langgraph、langchain-anthropic、langchain-openai、python-dotenv、typer、rich
- **打包**：PyInstaller（配置在 `build.spec`）
- **模型 Provider**：`src/mincc/llm.py` 中通过 `init_chat_model` 工厂支持 anthropic 与 openai；国内/自部署模型走 OpenAI 兼容接口（用 `LLM_BASE_URL` 配置）

## 常用命令

| 操作 | 命令 |
|---|---|
| 安装依赖 | `uv sync` |
| 运行交互模式 | `uv run mincc` |
| 单次执行 | `uv run mincc run "<prompt>"` |
| 跑测试 | `uv run pytest -q` |
| Lint | `uv run ruff check` |
| 格式化 | `uv run ruff format` |
| 打包可执行 | `uv run pyinstaller build.spec` |

## 代码风格

- 缩进 4 空格，UTF-8，LF 换行（`.editorconfig` 已配置）。
- 行宽 100，启用 ruff 的 E/F/I/W/UP/B/SIM 规则集。
- 公共函数使用类型注解。

## 新增工具的标准流程

1. 在 `src/mincc/tools/` 下新建一个模块，使用 `langchain_core.tools` 的 `@tool` 装饰器，docstring 写清楚用途与参数（LLM 据此选择是否调用）。
2. 在 `src/mincc/tools/__init__.py` 中 import 该工具并加入 `ALL_TOOLS`。
3. 在 `tests/` 下补一个对应的最小用例。
4. 涉及破坏性操作（写文件、执行 shell、网络请求等）时，必须在工具内部做安全校验或在 prompt 中明确要求 agent 先确认。

## 与用户协作时的语言

**全程使用中文**，包括工具调用前的说明与中间状态更新。代码本身保持英文，注释与文档使用中文。

## 不在范围内（已知未来工作）

- 多工具实现（write / edit / bash / grep / glob）
- LangGraph checkpointer 多轮对话持久化
- subagent 与任务编排
- MCP 客户端集成
- 流式输出渲染
- 权限系统（敏感操作前确认）

这些会在脚手架基础上增量加，注册表与目录结构已经为它们留好位置。
