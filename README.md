# mincc

> mini claude code —— 一个跑在终端里的 Python AI Agent，基于 LangChain / LangGraph 构建。

## 特性

- Python 3.12，使用 [uv](https://docs.astral.sh/uv/) 做依赖管理
- 基于 [LangGraph](https://langchain-ai.github.io/langgraph/) 的 ReAct agent
- 模型 provider 支持：Claude（Anthropic）、OpenAI、DeepSeek
- 工具系统采用注册表模式，新增工具只需放入 `src/mincc/tools/` 并加入注册表
- 命令行用 [typer](https://typer.tiangolo.com/) + [rich](https://rich.readthedocs.io/) 渲染
- 支持 PyInstaller 打包成单文件可执行程序

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 用编辑器填入 LLM_API_KEY 等
```

主要环境变量：

| 变量 | 说明 |
|---|---|
| `LLM_PROVIDER` | `claude`、`openai` 或 `deepseek` |
| `LLM_MODEL` | 模型名，例：`claude-sonnet-4-5`、`gpt-4o-mini`、`deepseek-chat` |
| `LLM_API_KEY` | API Key |
| `LLM_BASE_URL` | 可选；OpenAI 自部署端点；DeepSeek 留空走默认 `https://api.deepseek.com/v1` |
| `LLM_TEMPERATURE` | 采样温度（默认 `0`） |

### 3. 运行

```bash
uv run mincc
```

输入 `/exit` 或 `/quit` 退出。查看帮助：

```bash
uv run mincc --help
```

## 项目结构

```
mincc/
├── __main__.py     # python -m mincc 入口
├── cli.py          # 命令行（typer）
├── config.py       # .env 加载与配置数据类
├── llm.py          # 模型 provider 抽象
├── agent.py        # LangGraph agent 装配
├── prompts.py      # 系统提示词
└── tools/          # 工具系统
    ├── __init__.py # 注册表 ALL_TOOLS
    └── read_file.py # 示例工具
```

## 新增工具

1. 在 `mincc/tools/` 下新建模块，使用 `@tool` 装饰器：

   ```python
   from langchain_core.tools import tool

   @tool
   def my_tool(arg: str) -> str:
       """工具说明，LLM 会读 docstring 决定是否调用。"""
       ...
   ```

2. 在 `mincc/tools/__init__.py` 中 import 并加入 `ALL_TOOLS`。

## 测试

```bash
uv run pytest -q
```

## 打包成可执行文件

```bash
uv run pyinstaller build.spec
```

产物位于 `dist/mincc`（Windows 为 `dist/mincc.exe`）。运行需将 `.env` 与可执行文件放在同目录，或导出环境变量。

## 开发与编辑器

- 项目根目录的 `.editorconfig` 让 PyCharm / VS Code 共用同一套缩进与换行规则。
- 推荐用 `uv run ruff check` 做格式与静态检查（已在 `pyproject.toml` 中配置）。

## 许可证

MIT
