import sys

sys.stdout.reconfigure(encoding="utf-8")  # so emoji don't crash the Windows console

import asyncio
import json
import os
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from pydantic import BaseModel

ROOT = Path(__file__).parent
WORKSPACE = ROOT / "src/workspace"
ASSETS = ROOT / "src/assets"
MEMORY_FILE = ROOT / "memory.md"
MCP_CONFIG = ROOT / "mcp_servers.json"


# ---------------------------------------------------------------------------
# Pillar 3: the model registry. Every entry is just an OpenAI-compatible
# endpoint. Cloud or local, frontier or free - same client, same harness.
# ---------------------------------------------------------------------------

class ModelConfig(BaseModel):
    base_url: str
    api_key: str = "none"
    model: str


MODELS: dict[str, ModelConfig] = {
    "local-gemma": ModelConfig(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        model="gemma4:12b",
    ),
    "local-smallgemma": ModelConfig(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        model="gemma4:e2b",
    ),
    "local-smallqwen": ModelConfig(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        model="qwen3.5:2b",
    ),
    "local-phi4": ModelConfig(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        model="phi4-mini:latest",
    ),
    "local-qwen": ModelConfig(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        model="qwen2.5-coder:7b",
    ),
    "gpt": ModelConfig(
        base_url="https://api.openai.com/v1",
        api_key=os.getenv("OPENAI_API_KEY", ""),
        model="gpt-5.2",
    ),
    "claude": ModelConfig(
        # Anthropic's OpenAI-compatible endpoint - same client works.
        base_url="https://api.anthropic.com/v1/",
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        model="claude-sonnet-5-5",
    ),
}

model_name = "local-gemma"  # switch at runtime with /model


# ---------------------------------------------------------------------------
# Pillar 2: memory. A markdown file in the prompt + a tool to append to it.
# ---------------------------------------------------------------------------

def load_memory() -> str:
    if MEMORY_FILE.is_file():
        return MEMORY_FILE.read_text(encoding="utf-8")
    return "(nothing saved yet)"


def save_memory(fact: str) -> str:
    with MEMORY_FILE.open("a", encoding="utf-8") as f:
        f.write(f"- {fact}\n")
    return f"saved: {fact}"


# ---------------------------------------------------------------------------
# Local tools (the ones we wrote by hand back in v1)
# ---------------------------------------------------------------------------

def resolve_workspace_path(filename: str) -> Path | None:
    """Resolve filename inside WORKSPACE; None if it escapes (../, absolute path, symlink)."""
    path = (WORKSPACE / filename).resolve()
    return path if path.is_relative_to(WORKSPACE.resolve()) else None


def list_files(folder: str = "") -> str:
    path = resolve_workspace_path(folder)
    if path is None:
        return f"error: {folder} is outside the workspace"
    if not path.is_dir():
        return f"error: no folder {folder}"
    return "\n".join(
        p.name + ("/" if p.is_dir() else "") for p in sorted(path.iterdir())
    ) or "(empty)"


def read_file(filename: str) -> str:
    path = resolve_workspace_path(filename)
    if path is None:
        return f"error: {filename} is outside the workspace"
    return path.read_text(encoding="utf-8") if path.is_file() else f"error: no {filename}"


def write_file(filename: str, content: str) -> str:
    file_path = resolve_workspace_path(filename)
    if file_path is None:
        return f"error: {filename} is outside the workspace"
    # Automatically creates any missing parent folders/directories
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"wrote {filename}"


LOCAL_TOOLS = {
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    "save_memory": save_memory,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "List files and folders in the user's workspace. Folders end "
                "with '/'. Pass 'folder' to list a subfolder."
            ),
            "parameters": {
                "type": "object",
                "properties": {"folder": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read one file from the user's workspace folder.",
            "parameters": {
                "type": "object",
                "properties": {"filename": {"type": "string"}},
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a file in the user's workspace folder. Automatically creates any missing parent folders/directories",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Save one short fact about the user to long-term memory. "
                "Use whenever you learn something lasting: their name, "
                "preferences, projects, recurring tasks."
                "save if user says 'remember that ...' or 'save this in memory ...'"
            ),
            "parameters": {
                "type": "object",
                "properties": {"fact": {"type": "string"}},
                "required": ["fact"],
            },
        },
    },
]


SYSTEM_PROMPT = """You are a helpful personal assistant running inside a \
custom harness. Be concise.

The user's workspace folder holds their personal files: notes, todo lists, \
ideas. You have tools to list, read, and write those files. Never claim you \
lack access to the user's files or tasks - use your tools to look.

Here is what you remember about the user from previous sessions:
{memory}

When you learn a new lasting fact about the user, save it with save_memory."""

# the running conversation - shared by every model we switch to
messages = [{"role": "system", "content": SYSTEM_PROMPT.format(memory=load_memory())}]


# ---------------------------------------------------------------------------
# Pillar 1: MCP (same component we built in v3)
# ---------------------------------------------------------------------------

mcp_sessions: dict[str, ClientSession] = {}  # tool name -> its server session


async def connect_mcp(stack: AsyncExitStack):
    """Launch every server in mcp_servers.json and merge in its tools."""
    config = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    for name, spec in config["mcpServers"].items():
        params = StdioServerParameters(command=spec["command"], args=spec["args"])
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except Exception as e:
            print(f"  [mcp] '{name}' failed to start: {e}")
            continue

        tools = (await session.list_tools()).tools
        for tool in tools:
            mcp_sessions[tool.name] = session
            TOOL_SCHEMAS.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
            )
        print(f"  [mcp] connected '{name}': {[t.name for t in tools]}")


async def call_tool(name: str, args: dict) -> str:
    # any tool failure (bad arguments, missing file, MCP error) goes back to the
    # model as text so it can correct itself, instead of crashing the harness
    try:
        if name in LOCAL_TOOLS:
            return LOCAL_TOOLS[name](**args)
        if name in mcp_sessions:
            result = await mcp_sessions[name].call_tool(name, args)
            return "\n".join(c.text for c in result.content if hasattr(c, "text"))
        return f"error: unknown tool {name}"
    except Exception as e:
        return f"error: {name} failed: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# The agent loop (unchanged since v2)
# ---------------------------------------------------------------------------

async def run_agent(user_message: str) -> str:
    cfg = MODELS[model_name]
    client = AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key)

    messages.append({"role": "user", "content": user_message})
    while True:
        response = await client.chat.completions.create(
            model=cfg.model, messages=messages, tools=TOOL_SCHEMAS
        )
        message = response.choices[0].message
        if not message.tool_calls:
            messages.append({"role": "assistant", "content": message.content})
            return message.content or ""

        messages.append(message)
        for call in message.tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}  # malformed JSON from the model; call_tool reports what is missing
            print(f"  [tool] {call.function.name}({args})")
            result = await call_tool(call.function.name, args)
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

def handle_command(line: str) -> bool:
    """Returns True if the line was a command."""
    global model_name
    if not line.startswith("/"):
        return False
    cmd, _, arg = line.partition(" ")
    if cmd == "/models":
        for name, cfg in MODELS.items():
            marker = "*" if name == model_name else " "
            print(f" {marker} {name:<12} {cfg.model}  ({cfg.base_url})")
    elif cmd == "/model":
        if arg in MODELS:
            model_name = arg
            print(f"  switched to {arg} ({MODELS[arg].model})")
        else:
            print(f"  unknown model '{arg}' - try /models")
    elif cmd == "/tools":
        for schema in TOOL_SCHEMAS:
            fn = schema["function"]
            origin = "local" if fn["name"] in LOCAL_TOOLS else "mcp"
            print(f"  [{origin}] {fn['name']}: {fn['description'][:60]}")
    elif cmd == "/memory":
        print(load_memory())
    elif cmd == "/quit":
        raise SystemExit
    else:
        print("  commands: /models /model <name> /tools /memory /quit")
    return True


async def main():
    async with AsyncExitStack() as stack:
        print("starting harness...")
        await connect_mcp(stack)
        print(
            f"\nharness ready - model: {model_name} "
            f"({MODELS[model_name].model}), "
            f"{len(TOOL_SCHEMAS)} tools, memory loaded"
        )
        print("type /models, /model <name>, /tools, /memory, or just talk\n")
        try:
            while True:
                line = (await asyncio.to_thread(input, "you: ")).strip()
                if not line or handle_command(line):
                    continue
                print("\nassistant:", await run_agent(line), "\n")
        except (EOFError, KeyboardInterrupt, SystemExit):
            print("\nbye!")


if __name__ == "__main__":
    asyncio.run(main())
