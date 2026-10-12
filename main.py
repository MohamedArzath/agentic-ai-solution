import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

from openai import OpenAI
from pathlib import Path

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
MODEL="gemma4:12b"
WORKSPACE=Path(__file__).parent / "src/workspace"
ASSETS=Path(__file__).parent / "src/assets"

# ------- tools functions --------

def resolve_workspace_path(file_name: str) -> Path | None:
    # resolve "../", absolute paths and symlinks, then reject anything outside the workspace
    file_path = (WORKSPACE / file_name).resolve()
    if not file_path.is_relative_to(WORKSPACE.resolve()):
        return None
    return file_path

def list_files() -> str:
    files = [f.name for f in WORKSPACE.iterdir() if f.is_file()]
    return json.dumps(files, indent=2)

def get_file_content(file_name: str) -> str:
    file_path = resolve_workspace_path(file_name)
    if file_path is None:
        return json.dumps({"error": f"'{file_name}' is outside the workspace."}, indent=2)
    if not file_path.exists() or not file_path.is_file():
        return json.dumps({"error": f"File '{file_name}' does not exist."}, indent=2)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return json.dumps({"file_name": file_name, "content": content}, indent=2)

def create_file(file_name: str, content: str) -> str:
    file_path = resolve_workspace_path(file_name)
    if file_path is None:
        return json.dumps({"error": f"'{file_name}' is outside the workspace."}, indent=2)
    file_path.parent.mkdir(parents=True, exist_ok=True)  # allow paths like "app/src/App.js"
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return json.dumps({"message": f"File '{file_name}' created successfully."}, indent=2)

TOOLS = {
    "list_files": list_files,
    "get_file_content": get_file_content,
    "create_file": create_file,
}

# -------- TOOLS defenition for the model --------
TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all files in the workspace directory. do not add arguments",
            "parameters": {"type": "object","properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_content",
            "description": "Get the content of a file in the workspace directory.",
            "parameters": {"type": "object", "properties": {"file_name": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a new file in the workspace directory with the specified content. file_name may include folders (e.g. 'app/src/App.js'); missing folders are created.",
            "parameters": {"type": "object", "properties": {"file_name": {"type": "string"}, "content": {"type": "string"}}},
        },
    },
]

def chat(user_input: str) -> str:
    if user_input.lower() in ["exit", "quit"]:
        print("Exiting chat...")
        sys.exit(0)
    messages =[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": user_input}
    ]

    while True:
        response = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS_DEFINITION,
        )
        message = response.choices[0].message

        # check if model requested a tool call
        if not message.tool_calls:
            return message.content or "No response from the assistant."
        
        messages.append(message)

        for call in message.tool_calls:
            tool_name = call.function.name
            try:
                tool_args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                tool_args = {}
            print(f"\nTool call: {tool_name} with arguments: {tool_args}")
            # send tool errors back to the model instead of crashing the chat
            try:
                if tool_name not in TOOLS:
                    raise ValueError(f"unknown tool '{tool_name}'")
                tool_response = TOOLS[tool_name](**tool_args)
            except Exception as e:
                tool_response = json.dumps({"error": f"{tool_name} failed: {type(e).__name__}: {e}"}, indent=2)
            messages.append({"role": "tool", "tool_call_id": call.id, "name": tool_name, "content": tool_response})

            
if __name__ == "__main__":
    print(f"Welcome to the chat! Model: ({MODEL}) Type 'exit' or 'quit' to leave.")
    try:
        while True:
            user_input = input("\nYou: ")
            print(f"\nAssistant: {chat(user_input)}")
    except (EOFError, KeyboardInterrupt):
        print("\nExiting chat...")
        sys.exit(0)