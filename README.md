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

**4. Set up Ollama and pull a model:** see [Ollama setup](#ollama-setup-local-models) below.

---

## Ollama setup (local models)

[Ollama](https://ollama.com/) runs open models on your own machine and serves them through an OpenAI-compatible API at `http://localhost:11434/v1`. Both agents connect to that address.

### 1. Install Ollama

**macOS** (Homebrew):

```bash
brew install ollama
```

You can also download the desktop app from [ollama.com/download](https://ollama.com/download). The app starts the server for you.

**Linux:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:** download and run the installer from [ollama.com/download](https://ollama.com/download).

Check the install:

```bash
ollama --version
```

### 2. Start the Ollama server

If you use the desktop app, the server is already running. Otherwise start it and leave the terminal open:

```bash
ollama serve
```

On macOS with Homebrew you can run it as a background service instead:

```bash
brew services start ollama
```

### 3. Pull the models

Each local entry in `agentic_ai.py` must match a model you have pulled. `main.py` uses `gemma4:12b`.

| Registry name (`/model`) | Ollama model | Pull command |
| --- | --- | --- |
| `local-gemma` *(default)* | `gemma4:12b` | `ollama pull gemma4:12b` |
| `local-smallgemma` | `gemma4:e2b` | `ollama pull gemma4:e2b` |
| `local-smallqwen` | `qwen3.5:2b` | `ollama pull qwen3.5:2b` |
| `local-phi4` | `phi4-mini:latest` | `ollama pull phi4-mini` |
| `local-qwen` | `qwen2.5-coder:7b` | `ollama pull qwen2.5-coder:7b` |

You only need the default to get started:

```bash
ollama pull gemma4:12b
```

The agents depend on **tool calling**, so use models that support it. On [ollama.com/search](https://ollama.com/search?c=tools), filter by the *tools* tag. Small models (2B and below) tend to call tools less reliably.

### 4. Check that it works

List the models you have pulled:

```bash
ollama list
```

Chat with a model directly (type `/bye` to exit):

```bash
ollama run gemma4:12b
```

Check the OpenAI-compatible endpoint the agents use:

```bash
curl http://localhost:11434/v1/models
```

### 5. Run the agents

```bash
uv run main.py
```

```bash
uv run agentic_ai.py
```

Inside `agentic_ai.py`, use `/models` to see the registry and `/model local-qwen` (or any other entry) to switch.

### Add your own local model

1. Pull it, for example `ollama pull llama3.2:3b`.
2. Add an entry to `MODELS` in `agentic_ai.py`:

   ```python
   "local-llama": ModelConfig(
       base_url="http://localhost:11434/v1",
       api_key="ollama",  # Ollama ignores the key, but the client requires one
       model="llama3.2:3b",
   ),
   ```

3. Switch to it with `/model local-llama`.

To use a different model in `main.py`, change `MODEL` at the top of the file.

### Use Ollama on another machine

To run models on a stronger machine on your network (for example a GPU box):

1. On that machine, make the server listen on all network interfaces:

   ```bash
   OLLAMA_HOST=0.0.0.0 ollama serve
   ```

2. In `main.py` and `agentic_ai.py`, change `localhost` in `base_url` to that machine's IP, for example `http://192.168.0.32:11434/v1`.

Only do this on a trusted network, because Ollama has no authentication.

### Troubleshooting

| Problem | Fix |
| --- | --- |
| `Connection refused` / `APIConnectionError` | The server isn't running. Start it with `ollama serve` or open the Ollama app. |
| `model "..." not found` | Pull it with `ollama pull <model>`. The name must match `ollama list` exactly. |
| `... does not support tools` | That model can't call tools. Switch to one with the *tools* tag. |
| Very slow replies | The model is too big for your RAM or GPU. Try a smaller one, such as `local-smallgemma`. |
| First reply is slow | Ollama loads the model into memory on the first request. Later replies are faster. |

---

## Configuration

### Ollama endpoint
Both scripts point to an Ollama server on the local machine, `http://localhost:11434/v1`:

- `main.py`: the `base_url` passed to `OpenAI(...)`
- `agentic_ai.py`: the `base_url` of each `local-*` entry in `MODELS`

To use a server on another machine, see [Use Ollama on another machine](#use-ollama-on-another-machine).

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

Example: ask the agent to build a React calculator. It writes every file into `src/workspace/`:

```
You: create a react js calculator project in a folder called reactcalculator. Include package.json, public/index.html, src/index.js, src/App.js and src/App.css

Tool call: create_file with arguments: {'file_name': 'reactcalculator/package.json', 'content': '{\n  "name": "react-calculator", ...'}
Tool call: create_file with arguments: {'file_name': 'reactcalculator/public/index.html', 'content': '<!DOCTYPE html>\n<html lang="en">...'}
Tool call: create_file with arguments: {'file_name': 'reactcalculator/src/index.js', 'content': "import React from 'react';\n..."}
Tool call: create_file with arguments: {'file_name': 'reactcalculator/src/App.js', 'content': "import { useState } from 'react';\n..."}
Tool call: create_file with arguments: {'file_name': 'reactcalculator/src/App.css', 'content': '.calculator {\n  display: grid; ...'}

Assistant: I've created a React calculator project in reactcalculator/. To run it:
  cd src/workspace/reactcalculator
  npm install
  npm start
```

Then run the generated app (requires [Node.js](https://nodejs.org/)):

```bash
cd src/workspace/reactcalculator && npm install && npm start
```

Name the files you need in the prompt, especially `public/index.html` and `src/index.js`. Smaller models sometimes leave them out, and then `npm start` fails with `Could not find a required file`. Output also differs from model to model, so check the files before you run them.

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
