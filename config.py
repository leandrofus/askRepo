# Global state for Ask Repo
execution_state = {
    "is_running": False,
    "stop_requested": False,
    "progress": 0,
    "total": 0,
    "logs": "",
    "current_task": "",
    "current_config": None,
    "tasks_list": [],
    "mode": "batch",
    "chat_history": [],
    "active_session": None
}

# ANSI Colors
CLR_RESET = "\033[0m"
CLR_INFO = "\033[94m"
CLR_SUCCESS = "\033[92m"
CLR_WARNING = "\033[93m"
CLR_ERROR = "\033[91m"
CLR_PROGRESS = "\033[95m"
CLR_LOG = "\033[90m"

PROVIDERS = {
    "gemini": {
        "name": "Gemini (CLI - Tool Use)",
        "template": "gemini --skip-trust --prompt {prompt_quoted} --yolo",
        "default_model": "gemini-2.0-flash"
    },
    "ollama": {
        "name": "Ollama",
        "template": "ollama run {model} {prompt_quoted}",
        "default_model": "mistral:latest"
    },
    "claude": {
        "name": "Claude (anthropic-cli)",
        "template": "claude {prompt_quoted}",
        "default_model": "claude-3-5-sonnet"
    },
    "llm": {
        "name": "LLM (SimonW Tool)",
        "template": "llm -m {model} {prompt_quoted}",
        "default_model": "gpt-4o"
    },
    "codex": {
        "name": "Codex (CLI)",
        "template": "codex --skip-trust --model {model} --prompt {prompt_quoted}",
        "default_model": "gpt-5.4"
    },
    "custom": {
        "name": "Custom Command",
        "template": "{model} --input {prompt_quoted}",
        "default_model": "my-tool"
    }
}

DEFAULT_SYSTEM_PROMPT = "you are a system architect."
DEFAULT_TASK_TEMPLATE = """Instructions: {system_prompt}

Task: Investigate files in {repo_dir}. 
analize the repository and give me {category} -> {point} -> {sub_point} """

DEFAULT_KB_TEMPLATE = """Instructions: Act as a knowledge assistant. You have access to the local folder: {kb_dir}
Question: {question}

Use your tools to search and read relevant files (.md, .pdf, .docx, .txt, etc.) in the folder to answer accurately."""
