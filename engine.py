import subprocess
import shlex
import sys
from config import CLR_LOG, CLR_RESET, PROVIDERS

def sanitize_output(line):
    # Lista de prefijos o frases que queremos ignorar (Boilerplate de la CLI y errores de carga)
    ignored_patterns = [
        "[ExtensionManager]",
        "Error loading agent",
        "Invalid agent definition",
        "Missing mandatory YAML frontmatter",
        "Agent Markdown files MUST start",
        "triple-dashes",
        "name: my-agent",       # Más genérico para atrapar variaciones
        "---)",
        "List directory done",  # Metadata de herramientas
        "Files above",
        "Error executing tool", # Errores de ejecución de herramientas internas
        "Invalid regular expression", # Error específico de regex en herramientas
        "YOLO mode is enabled",
        "All tool calls will be automatically approved",
        "Gemini CLI - Defaults to interactive mode",
        "Launch Gemini CLI",
        "Usage: gemini",
        "--- FILE CONTENT",
        "IMPORTANT: The file content has been truncated"
    ]
    for pattern in ignored_patterns:
        if pattern in line:
            return None
    return line

def execute_llm_command(full_prompt, cwd, provider_key, model, state_proxy, gui_mode=False):
    preset = PROVIDERS.get(provider_key, PROVIDERS["gemini"])
    template = preset["template"]
    prompt_quoted = shlex.quote(full_prompt)
    
    command_str = template.format(
        model=model or preset["default_model"],
        prompt_quoted=prompt_quoted
    )
    
    process = subprocess.Popen(
        command_str,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd,
        bufsize=1,
        universal_newlines=True
    )

    full_output = []
    while True:
        if state_proxy["stop_requested"]:
            process.terminate()
            break
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            # Sanitizamos la línea antes de procesarla
            clean_line = sanitize_output(line)
            
            # Siempre imprimimos en consola real para debugging
            sys.stdout.write(f"{CLR_LOG}{line}{CLR_RESET}")
            sys.stdout.flush()
            
            if clean_line:
                if gui_mode:
                    state_proxy["logs"] += clean_line
                full_output.append(clean_line)

    process.wait()
    return "".join(full_output) if process.returncode == 0 else f"\n\n> ERROR: Command failed with code {process.returncode}\n"

def execute_chat_command(prompt, cwd, provider_key, model, state_proxy, system_prompt=None):
    preset = PROVIDERS.get(provider_key, PROVIDERS["gemini"])
    prompt_quoted = shlex.quote(prompt)
    
    if provider_key == "gemini":
        session_arg = ""
        if state_proxy.get("active_session"):
            session_arg = f"--resume {state_proxy['active_session']}"
        
        system_arg = ""
        if system_prompt:
            system_arg = f"--system {shlex.quote(system_prompt)}"
            
        command_str = f"gemini --prompt {prompt_quoted} {session_arg} {system_arg} --yolo"
    else:
        template = preset["template"]
        command_str = template.format(
            model=model or preset["default_model"],
            prompt_quoted=prompt_quoted
        )

    process = subprocess.Popen(
        command_str,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd,
        bufsize=1,
        universal_newlines=True
    )

    full_output = []
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            clean_line = sanitize_output(line)
            
            # Consola real (con todo)
            sys.stdout.write(line)
            sys.stdout.flush()
            
            if clean_line:
                # Solo el texto limpio va a la UI y al historial
                state_proxy["logs"] += clean_line
                full_output.append(clean_line)

    process.wait()
    
    if provider_key == "gemini" and not state_proxy.get("active_session"):
        state_proxy["active_session"] = "latest"

    return "".join(full_output)
