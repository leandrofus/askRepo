import os
import subprocess
import shlex
import sys
import re
from config import CLR_LOG, CLR_RESET, PROVIDERS, CLR_INFO, CLR_ERROR, CLR_WARNING

def sanitize_output(line):
    # Eliminar secuencias de escape ANSI (colores, movimientos de cursor, spinners)
    ansi_escape = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')
    line = ansi_escape.sub('', line)
    
    # Eliminar caracteres de control individuales (como los de los spinners de Ollama)
    line = ''.join(c for c in line if ord(c) >= 32 or c in '\n\r\t')

    # Lista de prefijos o frases que queremos ignorar
    ignored_patterns = [
        "[ExtensionManager]",
        "Error loading agent",
        "Invalid agent definition",
        "Missing mandatory YAML frontmatter",
        "Agent Markdown files MUST start",
        "triple-dashes",
        "name: my-agent",
        "---)",
        "List directory done",
        "Files above",
        "Error executing tool",
        "Invalid regular expression",
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
    
    # Si la línea queda vacía tras la limpieza, la ignoramos
    if not line.strip():
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
        
        # Prepend system prompt to the main prompt if provided
        final_prompt = prompt
        if system_prompt:
            final_prompt = f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\nUSER MESSAGE:\n{prompt}"
            
        prompt_quoted = shlex.quote(final_prompt)
        command_str = f"gemini --prompt {prompt_quoted} {session_arg} -y --dangerously-skip-permissions"
    else:
        template = preset["template"]
        selected_model = model or preset["default_model"]
        
        # Resiliencia para Ollama: si el modelo no existe, usar el primero disponible
        if provider_key == "ollama":
            available = fetch_available_models("ollama")
            if available and selected_model not in available:
                selected_model = available[0]
                state_proxy["logs"] += f"{CLR_WARNING}[OLLAMA] Model '{model}' not found. Using fallback: '{selected_model}'{CLR_RESET}\n"

        # Inyectar contexto de archivos para proveedores que no son Gemini
        file_context = ""
        try:
            # Listamos archivos en el directorio actual (limitado a los 10 más relevantes/recientes)
            files = [f for f in os.listdir(cwd) if os.path.isfile(os.path.join(cwd, f))]
            # Priorizamos logs y archivos de texto
            files.sort(key=lambda x: (not x.endswith('.log'), not x.endswith('.txt'), x))
            
            for f_name in files[:10]:
                f_path = os.path.join(cwd, f_name)
                # Solo leer archivos de texto razonables (< 100KB)
                if os.path.getsize(f_path) < 100000:
                    try:
                        with open(f_path, 'r', encoding='utf-8', errors='ignore') as f_content:
                            content = f_content.read(4000) # Leer los primeros 4000 caracteres
                            file_context += f"\n--- FILE: {f_name} ---\n{content}\n"
                    except: pass
            
            if file_context:
                state_proxy["logs"] += f"{CLR_INFO}[CONTEXT] Injected context from {len(files[:10])} local files.{CLR_RESET}\n"
        except Exception as e:
            state_proxy["logs"] += f"{CLR_ERROR}[CONTEXT] Error reading files: {str(e)}{CLR_RESET}\n"

        # Inyectar historial de chat para mantener el contexto (si existe)
        history_context = ""
        if state_proxy.get("chat_history"):
            history_context = "\n".join([f"{'USER' if m['role'] == 'user' else 'ASSISTANT'}: {m['text']}" for m in state_proxy["chat_history"][-6:]]) # Últimos 6 mensajes
            history_context = f"\n[CHAT_HISTORY]\n{history_context}\n"

        # For other providers, we might still want to prepend system prompt if not handled by template
        final_prompt = prompt
        if file_context or history_context:
            final_prompt = f"""{history_context}
[KNOWLEDGE_BASE_CONTEXT]
The following are snippets from local files in '{cwd}' that might be relevant to the user's request.
{file_context}
[END_CONTEXT]

USER QUESTION:
{prompt}

Instructions: Use the provided context and history to answer accurately. If the information isn't in the context, say so."""
        
        if system_prompt:
            final_prompt = f"SYSTEM_INSTRUCTIONS: {system_prompt}\n\n{final_prompt}"
        
        prompt_quoted = shlex.quote(final_prompt)
        command_str = template.format(
            model=selected_model,
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
            
            # Capturar SESSION_ID de Gemini si aparece en los logs
            session_match = re.search(r'--resume\s+([a-zA-Z0-9_-]{10,})', line)
            if session_match:
                state_proxy["active_session"] = session_match.group(1)

            if clean_line:
                # Solo el texto limpio va a la UI y al historial
                state_proxy["logs"] += clean_line
                full_output.append(clean_line)

    process.wait()
    
    # Fallback to 'latest' if no session ID was captured for gemini
    if provider_key == "gemini" and not state_proxy.get("active_session"):
        state_proxy["active_session"] = "latest"

    return "".join(full_output)

def fetch_available_models(provider_key):
    """
    Fetches available models for a given provider. 
    Uses CLI commands where possible (e.g. Ollama) or predefined lists for remote providers.
    """
    if provider_key == "ollama":
        try:
            res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                # Format: NAME [ID] [SIZE] [MODIFIED]
                lines = res.stdout.strip().split('\n')[1:]
                return sorted([line.split()[0] for line in lines if line.strip()])
        except Exception as e:
            print(f"Error fetching Ollama models: {e}")
    
    elif provider_key == "gemini":
        return [
            "gemini-2.0-flash", 
            "gemini-1.5-flash", 
            "gemini-1.5-pro", 
            "gemini-2.0-flash-thinking-exp",
            "gemini-3-flash-preview",
            "gemini-2.0-pro-exp-02-05",
            "gemini-3-pro-preview"
        ]
    
    elif provider_key == "codex":
        try:
            import os
            import json
            cache_path = os.path.expanduser("~/.codex/models_cache.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    data = json.load(f)
                    models = [m["slug"] for m in data.get("models", []) if "slug" in m]
                    if models:
                        return sorted(list(set(models)))
        except Exception as e:
            print(f"Error fetching Codex models: {e}")
        return ["gpt-5.4", "gpt-5.4-mini"]

    elif provider_key == "claude":
        try:
            res = subprocess.run(["claude", "agents"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                # Format: agent-name · model-name
                lines = res.stdout.strip().split('\n')
                models = set()
                for line in lines:
                    if '·' in line:
                        parts = line.split('·')
                        if len(parts) > 1:
                            m = parts[1].strip()
                            if m and m != 'inherit':
                                models.add(m)
                if models: return sorted(list(models))
        except: pass
        return ["sonnet", "haiku", "opus"]
    
    elif provider_key == "llm":
        try:
            res = subprocess.run(["llm", "models"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                lines = res.stdout.strip().split('\n')
                return sorted([line.split(':')[0].strip() for line in lines if ':' in line])
        except: pass
        return ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]

    # Fallback to the default model defined in config
    preset = PROVIDERS.get(provider_key, {})
    default = preset.get("default_model")
    return [default] if default else []
