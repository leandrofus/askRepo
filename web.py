import os
import subprocess
import threading
import time
import json
import re
import markdown
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from config import execution_state, PROVIDERS, DEFAULT_SYSTEM_PROMPT, DEFAULT_TASK_TEMPLATE, DEFAULT_KB_TEMPLATE, CLR_INFO, CLR_ERROR, CLR_SUCCESS, CLR_WARNING, CLR_RESET
from parser import parse_capabilities
from engine import execute_llm_command, execute_chat_command, fetch_available_models
from ollama_marketplace import search_ollama_marketplace
from git_utils import run_git_command

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['UPLOAD_FOLDER'] = '/tmp/ask_repo_uploads'
# Dynamic results path based on the module location
RESULTS_DIR = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html', 
                          providers=PROVIDERS, 
                          providers_json=json.dumps(PROVIDERS),
                          default_system_prompt=DEFAULT_SYSTEM_PROMPT,
                          default_task_template=DEFAULT_TASK_TEMPLATE,
                          default_kb_template=DEFAULT_KB_TEMPLATE)

@app.route('/ls')
def list_dir():
    home = os.path.expanduser('~')
    path = request.args.get('path', home)
    if not path or path == 'HOME':
        path = home
    try:
        items = []
        for entry in os.scandir(path):
            items.append({"name": entry.name, "path": entry.path, "is_dir": entry.is_dir()})
        return jsonify(sorted(items, key=lambda x: (not x['is_dir'], x['name'])))
    except: return jsonify([])

@app.route('/results')
def list_results():
    try:
        files = [f for f in os.listdir(RESULTS_DIR) if f.endswith('.md')]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(RESULTS_DIR, x)), reverse=True)
        return jsonify(files)
    except: return jsonify([])

@app.route('/results/<filename>')
def get_result(filename):
    filename = secure_filename(filename)
    path = os.path.join(RESULTS_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
    
    with open(path, 'r') as f:
        content = f.read()
    
    html_content = markdown.markdown(content, extensions=['fenced_code', 'codehilite', 'tables'])
    return jsonify({"raw": content, "html": html_content})

@app.route('/results/summarize', methods=['POST'])
def summarize_report():
    if execution_state["is_running"]: return jsonify({"error": "Engine busy"}), 400
    data = request.json
    filename = secure_filename(data.get('filename'))
    provider = data.get('provider')
    model = data.get('model')
    
    path = os.path.join(RESULTS_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
        
    with open(path, 'r') as f:
        content = f.read()

    # Si es muy largo, tomamos partes clave para no exceder límites
    if len(content) > 50000:
        content = content[:25000] + "\n... [TRUNCATED] ...\n" + content[-25000:]

    summary_prompt = f"POR FAVOR, GENERA UN RESUMEN EJECUTIVO TÉCNICO DE ESTA INVESTIGACIÓN. Destaca los hallazgos principales, la arquitectura detectada y los puntos críticos.\n\nCONTENIDO DEL REPORTE:\n{content}"
    
    execution_state["is_running"] = True
    execution_state["logs"] = f"{CLR_INFO}[SUMMARIZE] Analyzing report: {filename}...{CLR_RESET}\n"
    
    def report_summary_bg():
        system_p = "Act as a technical lead. Summarize the provided technical report concisely but thoroughly."
        response = execute_chat_command(summary_prompt, os.getcwd(), provider, model, execution_state, system_prompt=system_p)
        
        # Insert summary at the beginning of the file
        with open(path, 'r') as f:
            original = f.read()
        
        with open(path, 'w') as f:
            f.write(f"# 📝 EXECUTIVE SUMMARY\n{response}\n\n---\n\n" + original)
            
        execution_state["is_running"] = False
        execution_state["logs"] += f"{CLR_SUCCESS}[SUMMARIZE] Summary added to {filename}.{CLR_RESET}\n"
        
    threading.Thread(target=report_summary_bg).start()
    return jsonify({"status": "processing"})

@app.route('/results/save', methods=['POST'])
def save_chat():
    history = execution_state.get("chat_history", [])
    filename = f"Chat_Session_{int(time.time())}.md"
    path = os.path.join(RESULTS_DIR, filename)
    
    with open(path, 'w') as f:
        # Guardar ID de sesión si existe (para Gemini)
        if execution_state.get("active_session"):
            f.write(f"<!-- SESSION_ID: {execution_state['active_session']} -->\n")
        
        # Guardar el último system prompt usado para poder recuperarlo
        if execution_state.get("last_system_prompt"):
            f.write(f"\n<div class='system-prompt-block'><strong>Last Used System Prompt</strong>\n{execution_state['last_system_prompt']}</div>\n\n")

        for msg in history:
            f.write(f"### {msg['role'].upper()}\n\n{msg['text'].strip()}\n\n")
            
    return jsonify({"status": "saved", "filename": filename})

@app.route('/results/resume', methods=['POST'])
def resume_report():
    data = request.json
    filename = secure_filename(data.get('filename'))
    path = os.path.join(RESULTS_DIR, filename)
    
    if not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
        
    with open(path, 'r') as f:
        content = f.read()

    new_history = []
    # Intentar recuperar SESSION_ID de metadatos (comentario HTML)
    session_match = re.search(r'<!-- SESSION_ID: (.*?) -->', content)
    if session_match:
        execution_state["active_session"] = session_match.group(1).strip()
        execution_state["logs"] += f"{CLR_INFO}[RESUME] Recovered Gemini Session: {execution_state['active_session']}{CLR_RESET}\n"
    else:
        execution_state["active_session"] = None

    # Intentar parsear si es un formato de chat guardado
    if "### USER" in content or "### ASSISTANT" in content:
        parts = re.split(r'### (USER|ASSISTANT)\n+', content)
        for i in range(1, len(parts), 2):
            role = parts[i].lower()
            text = parts[i+1].strip()
            if text:
                new_history.append({"role": role, "text": text})
    else:
        # Si es un reporte normal, lo cargamos como contexto inicial del asistente
        new_history.append({"role": "assistant", "text": f"He cargado el reporte '{filename}'. ¿Qué te gustaría profundizar sobre estos resultados?\n\n---\n\n" + content[:10000]})

    execution_state["chat_history"] = new_history
    
    # Intentar recuperar el último SYSTEM PROMPT
    # Buscamos la última ocurrencia del bloque de prompt del sistema
    system_prompt = None
    prompt_blocks = re.findall(r"<div class='system-prompt-block'><strong>.*?</strong>\n(.*?)</div>", content, re.DOTALL)
    if prompt_blocks:
        system_prompt = prompt_blocks[-1].strip()
        execution_state["last_system_prompt"] = system_prompt

    return jsonify({
        "status": "resumed", 
        "history_count": len(new_history),
        "system_prompt": system_prompt
    })

@app.route('/chat', methods=['POST'])
def chat():
    if execution_state["is_running"]: return jsonify({"error": "Engine busy"}), 400
    data = request.json
    prompt = data.get('message')
    repo = data.get('repo') or os.getcwd()
    provider = data.get('provider')
    model = data.get('model')
    system_prompt = data.get('system_prompt')
    if not prompt: return jsonify({"error": "Empty message"}), 400
    
    execution_state["is_running"] = True
    execution_state["logs"] = f"{CLR_INFO}[CHAT] Thinking...{CLR_RESET}\n"
    
    # Initialize chat session file if not exists
    if not execution_state.get("chat_file"):
        session_id = int(time.time())
        execution_state["chat_file"] = os.path.join(RESULTS_DIR, f"Chat_Session_{session_id}.md")
        with open(execution_state["chat_file"], "w") as f:
            f.write(f"# Interactive Chat Session: {session_id}\n")
            f.write(f"**Target Repo:** {repo}\n")
            f.write(f"**Provider:** {provider}\n")
            if system_prompt:
                f.write(f"\n<div class='system-prompt-block'><strong>Initial System Prompt</strong>\n{system_prompt}</div>\n\n")
            f.write(f"\n---\n\n")
        execution_state["last_system_prompt"] = system_prompt

    def chat_bg():
        # Detect and log System Prompt changes
        if system_prompt != execution_state.get("last_system_prompt"):
            with open(execution_state["chat_file"], "a") as f:
                f.write(f"\n<div class='system-prompt-block'><strong>System Prompt Updated</strong>\n{system_prompt}</div>\n\n")
            execution_state["last_system_prompt"] = system_prompt

        response = execute_chat_command(prompt, repo, provider, model, execution_state, system_prompt=system_prompt)
        
        # Persist to file
        with open(execution_state["chat_file"], "a") as f:
            f.write(f"### USER\n{prompt}\n\n")
            f.write(f"### ASSISTANT\n{response}\n\n---\n\n")
        
        execution_state["chat_history"].append({"role": "user", "text": prompt})
        execution_state["chat_history"].append({"role": "assistant", "text": response})
        execution_state["is_running"] = False
        
    threading.Thread(target=chat_bg).start()
    return jsonify({"status": "processing"})

@app.route('/chat/summarize', methods=['POST'])
def summarize_chat():
    if execution_state["is_running"]: return jsonify({"error": "Engine busy"}), 400
    data = request.json
    repo = data.get('repo') or os.getcwd()
    provider = data.get('provider')
    model = data.get('model')
    system_prompt = data.get('system_prompt')
    
    if not execution_state["chat_history"]:
        return jsonify({"error": "No history to summarize"}), 400

    history_text = "\n".join([f"{m['role'].upper()}: {m['text']}" for m in execution_state["chat_history"]])
    summary_prompt = f"POR FAVOR, RESUME ESTA CONVERSACIÓN HASTA EL MOMENTO. Destaca los puntos clave, decisiones tomadas e información técnica relevante.\n\nHISTORIAL:\n{history_text}"
    
    execution_state["is_running"] = True
    execution_state["logs"] = f"{CLR_INFO}[SUMMARIZE] Generating session summary...{CLR_RESET}\n"
    
    def summary_bg():
        final_system = f"{system_prompt}\n\nAct as a summarization assistant. Use the persona defined above to summarize the conversation history provided."
        response = execute_chat_command(summary_prompt, repo, provider, model, execution_state, system_prompt=final_system)
        
        if execution_state.get("chat_file"):
            with open(execution_state["chat_file"], "a") as f:
                f.write(f"\n<div class='system-prompt-block'><strong>System Prompt used for Summary</strong>\n{system_prompt}</div>\n\n")
                f.write(f"\n## 📝 Session Summary\n{response}\n\n---\n\n")
        
        execution_state["chat_history"].append({
            "role": "assistant", 
            "text": f"<div class='system-prompt-block'><strong>System Prompt used for Summary</strong>\n{system_prompt}</div>\n\n### 📝 SESSION SUMMARY\n{response}"
        })
        execution_state["is_running"] = False
        
    threading.Thread(target=summary_bg).start()
    return jsonify({"status": "processing"})

@app.route('/chat/clear', methods=['POST'])
def clear_chat():
    execution_state["chat_history"] = []
    execution_state["active_session"] = None
    execution_state["chat_file"] = None
    execution_state["logs"] = "Chat context cleared. New session file will be created.\n"
    return jsonify({"status": "cleared"})

@app.route('/run', methods=['POST'])
def run_task():
    if execution_state["is_running"]: return jsonify({"error": "Already running"}), 400
    
    mode = request.form.get('op_mode', 'batch')
    execution_state["mode"] = mode
    
    if mode == 'batch':
        if 'file' not in request.files: return jsonify({"error": "No file uploaded"}), 400
        file = request.files['file']
        if not file.filename.endswith('.md'):
            return jsonify({"error": "Taskfile must be a .md file"}), 400
            
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Output path validation
        out_val = request.form.get('output', '').strip()
        if not out_val:
            output_name = f"Audit_Report_{int(time.time())}.md"
        else:
            output_name = secure_filename(out_val)
            if not output_name or output_name == ".md":
                output_name = f"Audit_Report_{int(time.time())}.md"
            elif not output_name.endswith('.md'):
                output_name += '.md'
        
        output_path = os.path.join(RESULTS_DIR, output_name)

        config = {
            "prompt": request.form.get('prompt'),
            "task_template": request.form.get('task_template'),
            "repo": request.form.get('repo'),
            "output": output_path,
            "mode": "markdown",  # Forzado a markdown por el usuario
            "git_url": request.form.get('git_url'),
            "git_branch": request.form.get('git_branch'),
            "git_pull": request.form.get('git_pull') == 'true',
            "provider": request.form.get('provider'),
            "model": request.form.get('model'),
            "input_path": file_path
        }
        execution_state["current_config"] = config
        execution_state["tasks_list"] = parse_capabilities(file_path, "markdown")
        execution_state["progress"] = 0
        execution_state["total"] = len(execution_state["tasks_list"])
    else:
        # KB Mode persistence
        output_name = f"KB_{int(time.time())}.md"
        output_path = os.path.join(RESULTS_DIR, output_name)
        
        from config import DEFAULT_KB_TEMPLATE
        config = {
            "kb_dir": request.form.get('kb_dir'),
            "kb_question": request.form.get('kb_question'),
            "kb_template": request.form.get('kb_template') or DEFAULT_KB_TEMPLATE,
            "provider": request.form.get('provider'),
            "model": request.form.get('model'),
            "output": output_path
        }
        execution_state["current_config"] = config
        execution_state["progress"] = 0
        execution_state["total"] = 1
        execution_state["current_task"] = "Knowledge Base Query"

    execution_state["stop_requested"] = False
    threading.Thread(target=process_thread).start()
    return jsonify({"status": "started"})

@app.route('/stop', methods=['POST'])
def stop_task():
    execution_state["stop_requested"] = True
    execution_state["is_running"] = False
    execution_state["logs"] += f"\n{CLR_WARNING}[STOP] Stop requested by user.{CLR_RESET}\n"
    return jsonify({"status": "stop_requested"})

@app.route('/resume', methods=['POST'])
def resume_task():
    if execution_state["is_running"]: return jsonify({"error": "Already running"}), 400
    execution_state["stop_requested"] = False
    threading.Thread(target=process_thread).start()
    execution_state["logs"] += f"\n{CLR_INFO}[RESUME] Resuming investigation...{CLR_RESET}\n"
    return jsonify({"status": "resumed"})

@app.route('/status')
def get_status(): return jsonify(execution_state)

@app.route('/api/models/<provider>')
def get_models(provider):
    models = fetch_available_models(provider)
    return jsonify(models)

@app.route('/api/ollama/marketplace')
def ollama_marketplace():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    results = search_ollama_marketplace(query)
    return jsonify(results)

@app.route('/api/ollama/pull', methods=['POST'])
def ollama_pull():
    data = request.json
    model_name = data.get('model')
    if not model_name:
        return jsonify({"error": "No model specified"}), 400
    
    execution_state["is_running"] = True
    execution_state["logs"] = f"{CLR_INFO}[OLLAMA] Pulling model {model_name}...{CLR_RESET}\n"
    
    def pull_bg():
        try:
            # We use subprocess directly to see the progress if possible
            process = subprocess.Popen(
                ["ollama", "pull", model_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            for line in process.stdout:
                execution_state["logs"] += line
            process.wait()
            if process.returncode == 0:
                execution_state["logs"] += f"{CLR_SUCCESS}[OLLAMA] Model {model_name} pulled successfully.{CLR_RESET}\n"
            else:
                execution_state["logs"] += f"{CLR_ERROR}[OLLAMA] Failed to pull model {model_name}.{CLR_RESET}\n"
        except Exception as e:
            execution_state["logs"] += f"{CLR_ERROR}[OLLAMA] Error: {e}{CLR_RESET}\n"
        finally:
            execution_state["is_running"] = False
            
    threading.Thread(target=pull_bg).start()
    return jsonify({"status": "processing"})

def run_git_command(args, cwd, state_proxy):
    state_proxy["logs"] += f"Executing: git {' '.join(args)}\n"
    res = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        state_proxy["logs"] += f"{CLR_ERROR}Git Error: {res.stderr}{CLR_RESET}\n"
        return False
    state_proxy["logs"] += f"{CLR_SUCCESS}Success.{CLR_RESET}\n"
    return True

def process_thread():
    global execution_state
    execution_state["is_running"] = True
    config = execution_state["current_config"]
    
    if execution_state["mode"] == "batch":
        process_batch(config)
    else:
        process_kb(config)
        
    execution_state["is_running"] = False

def process_batch(config):
    tasks = execution_state["tasks_list"]
    target_repo = config["repo"]
    
    if execution_state["progress"] == 0:
        if config.get("git_url"):
            temp_repo = os.path.join("/tmp", f"ask_repo_{int(time.time())}")
            execution_state["logs"] += f"{CLR_INFO}[GIT] Cloning to {temp_repo}...{CLR_RESET}\n"
            if not run_git_command(["clone", config["git_url"], temp_repo], "/tmp", execution_state): return
            target_repo = temp_repo
            execution_state["current_config"]["repo"] = target_repo

        if os.path.exists(os.path.join(target_repo, ".git")):
            if config.get("git_branch"):
                if not run_git_command(["checkout", config["git_branch"]], target_repo, execution_state): return
            if config.get("git_pull"): run_git_command(["pull"], target_repo, execution_state)

    output_path = config["output"]
    mode = 'w' if execution_state["progress"] == 0 else 'a'
    
    with open(output_path, mode) as out:
        if mode == 'w':
            header = f"""# 📑 TECHNICAL AUDIT REPORT
> **Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}
> **Model:** {config['model']} ({config['provider']})
> **Target:** `{target_repo}`
> **Status:** Full Investigation

---
"""
            out.write(header)
        start_idx = execution_state["progress"]
        for i in range(start_idx, len(tasks)):
            if execution_state["stop_requested"]: return
            task = tasks[i]
            execution_state["current_task"] = task["sub_point"]
            out.write(f"## {task['category']} | {task['point']} | {task['sub_point']}\n")
            details = execute_llm_command(config["task_template"].format(
                system_prompt=config["prompt"], repo_dir=target_repo,
                category=task['category'], point=task['point'], sub_point=task['sub_point']
            ), target_repo, config["provider"], config["model"], execution_state, gui_mode=True)
            out.write(details + "\n\n---\n\n")
            out.flush()
            execution_state["progress"] = i + 1
    execution_state["current_task"] = "Completed"

def process_kb(config):
    execution_state["logs"] += f"{CLR_INFO}[KB] Analyzing Knowledge Base at: {config['kb_dir']}{CLR_RESET}\n"
    try:
        full_prompt = config["kb_template"].format(kb_dir=config["kb_dir"], question=config["kb_question"])
    except Exception as e:
        execution_state["logs"] += f"{CLR_ERROR}Template Error: {str(e)}{CLR_RESET}\n"
        return

    result = execute_llm_command(full_prompt, config["kb_dir"], config["provider"], config["model"], execution_state, gui_mode=True)
    execution_state["progress"] = 1
    execution_state["current_task"] = "KB Answer Ready"
    
    with open(config["output"], "w") as f:
        header = f"""# 🧠 KNOWLEDGE BASE ANALYSIS
> **Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}
> **Source:** `{config['kb_dir']}`
> **Model:** {config['model']}

## ❓ Question
{config['kb_question']}

---
## 🎯 Analysis Result
"""
        f.write(header + result)
    execution_state["logs"] += f"\n{CLR_SUCCESS}KB Answer saved to {os.path.basename(config['output'])}{CLR_RESET}\n"
