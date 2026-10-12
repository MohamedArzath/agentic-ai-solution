# Agentic Trial

A small, readable AI agent harness built from scratch on the OpenAI-compatible Chat Completions API. It contains two agents:

| Script | What it is |
| --- | --- |
| [`main.py`](main.py) | **Simple agent.** One local model (Ollama), a tool-calling loop and three file tools scoped to `src/workspace/`. |
| [`agentic_ai.py`](agentic_ai.py) | **Full agent.** Several models you can switch at runtime (local and cloud), MCP server tools, long-term memory and slash commands. |

Both agents use the same plain loop: send the conversation to the model, run any tools it asks for, append the results and repeat until the model gives a final answer.

---

## Features

### `main.py`: simple local agent
- Talks to a local Ollama model (`gemma4:12b` by default) through its OpenAI-compatible endpoint
- File tools: `list_files`, `get_file_content`, `create_file`
- All file access stays inside `src/workspace/`
- Each prompt starts a new conversation, with no state kept between turns

### `agentic_ai.py`: multi-model agent
- **Model registry.** Local Ollama models (Gemma, Qwen, Phi) plus OpenAI and Anthropic, all through one client. Switch with `/model <name>`.
- **MCP tools.** Starts every server listed in [`mcp_servers.json`](mcp_servers.json) (time and fetch by default) and adds their tools to the model's toolset.
- **Long-term memory.** The model can call `save_memory` to append facts to `memory.md`. That file is loaded into the system prompt when the agent starts.
- **File tools.** `list_files`, `read_file`, `write_file` (creates parent folders), scoped to `src/workspace/`
- **Shared conversation.** History is kept across turns and across model switches.

---

## Project structure

```
agentic_trial/
├── main.py              # simple local-model file agent
├── agentic_ai.py        # multi-model agent with MCP + memory
├── mcp_servers.json     # MCP servers started by agentic_ai.py
├── memory.md            # long-term memory (appended to at runtime)
├── pyproject.toml
├── uv.lock
└── src/
    ├── assets/          # static assets (contents git-ignored)
    └── workspace/       # the agent's sandboxed file area (contents git-ignored)
```

---

## Requirements

- Python **3.12+**
- [uv](https://docs.astral.sh/uv/) package manager
- [Ollama](https://ollama.com/) for the local models
- *(Optional)* API keys for OpenAI and Anthropic to use the cloud models

---

## Installation (uv)

**1. Install uv** (skip this if you already have it)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**2. Clone the repository**

```bash
git clone git@github.com:<your-org>/<your-repo>.git
cd <your-repo>/agentic_trial
```

**3. Create the virtual environment and install dependencies**

```bash
uv sync
```

`uv sync` reads `pyproject.toml` and `uv.lock`, installs Python 3.12 if needed, creates `.venv/` and installs the pinned dependencies.

**4. Pull the local models with Ollama**

```bash
ollama pull gemma4:12b
```

Pull any other models you plan to use from the registry in `agentic_ai.py`, for example `qwen2.5-coder:7b` or `phi4-mini`.

---

## Configuration

### Ollama endpoint
Both scripts point to an Ollama server on the local network (`http://192.168.0.32:11434/v1`). If Ollama runs on your own machine, change this to `http://localhost:11434/v1`:

- `main.py`: the `base_url` passed to `OpenAI(...)`
- `agentic_ai.py`: the `base_url` of each `local-*` entry in `MODELS`

### Cloud API keys (optional, `agentic_ai.py`)

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

Never commit keys. `.env` files are git-ignored.

### MCP servers
Add or remove servers in `mcp_servers.json`. Each one is launched over stdio:

```json
{
  "mcpServers": {
    "time":  { "command": "uvx", "args": ["mcp-server-time"] },
    "fetch": { "command": "uvx", "args": ["mcp-server-fetch"] }
  }
}
```

---

## Usage

### Simple agent

```bash
uv run main.py
```

```
You: list my files
Tool call: list_files with arguments: {}
Assistant: Your workspace contains data.txt and hello.py.
```

Type `exit` or `quit` to leave.

### Multi-model agent

```bash
uv run agentic_ai.py
```

| Command | Description |
| --- | --- |
| `/models` | List the configured models (the active one is marked `*`) |
| `/model <name>` | Switch model, e.g. `/model local-qwen` or `/model claude` |
| `/tools` | List the loaded tools and whether each is local or MCP |
| `/memory` | Show the saved long-term memory |
| `/quit` | Exit |

Anything that does not start with `/` goes to the agent:

```
you: remember that I prefer TypeScript
  [tool] save_memory({'fact': 'The user prefers TypeScript'})
assistant: Got it, I'll remember that.
```

---

## How it works

```
user input ──► messages ──► model ──► tool_calls? ──no──► answer
                  ▲                       │yes
                  └──── tool results ◄────┘
```

1. The user message is added to `messages`.
2. The model gets the conversation plus the JSON tool schemas.
3. If it returns `tool_calls`, each tool runs (a local Python function or an MCP session) and its result is added as a `tool` message.
4. The loop repeats until the model replies without any tool calls.

---

## Security notes

- `write_file` and `create_file` overwrite existing files without asking.
- MCP servers run as local processes with your user's permissions. Only add servers you trust.

---

## Dependencies

| Package | License |
| --- | --- |
| [openai](https://github.com/openai/openai-python) | Apache-2.0 |
| [mcp](https://github.com/modelcontextprotocol/python-sdk) | MIT |
| [pydantic](https://github.com/pydantic/pydantic) | MIT |

---

## Author

**Mohamed Arzath**
