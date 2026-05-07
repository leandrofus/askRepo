import os
import threading
import time
import json
import markdown
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from config import execution_state, PROVIDERS, DEFAULT_SYSTEM_PROMPT, DEFAULT_TASK_TEMPLATE, DEFAULT_KB_TEMPLATE, CLR_INFO, CLR_ERROR, CLR_SUCCESS, CLR_WARNING, CLR_RESET
from parser import parse_capabilities
from engine import execute_llm_command, execute_chat_command
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
            f.write(f"**Provider:** {provider}\n\n")

    def chat_bg():
        response = execute_chat_command(prompt, repo, provider, model, execution_state, system_prompt=system_prompt)
        
        # Persist to file
        with open(execution_state["chat_file"], "a") as f:
            f.write(f"### 👤 User\n{prompt}\n\n")
            f.write(f"### 🤖 Assistant\n{response}\n\n---\n\n")
        
        execution_state["chat_history"].append({"role": "user", "text": prompt})
        execution_state["chat_history"].append({"role": "assistant", "text": response})
        execution_state["is_running"] = False
        
    threading.Thread(target=chat_bg).start()
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
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Output path is forced into RESULTS_DIR for persistence
        output_name = secure_filename(request.form.get('output', 'Detailed_Manual.md'))
        if not output_name.endswith('.md'): output_name += '.md'
        output_path = os.path.join(RESULTS_DIR, output_name)

        config = {
            "prompt": request.form.get('prompt'),
            "task_template": request.form.get('task_template'),
            "repo": request.form.get('repo'),
            "output": output_path,
            "mode": request.form.get('mode'),
            "git_url": request.form.get('git_url'),
            "git_branch": request.form.get('git_branch'),
            "git_pull": request.form.get('git_pull') == 'true',
            "provider": request.form.get('provider'),
            "model": request.form.get('model'),
            "input_path": file_path
        }
        execution_state["current_config"] = config
        execution_state["tasks_list"] = parse_capabilities(file_path, config["mode"])
        execution_state["progress"] = 0
        execution_state["total"] = len(execution_state["tasks_list"])
    else:
        # KB Mode persistence
        output_name = f"KB_{int(time.time())}.md"
        output_path = os.path.join(RESULTS_DIR, output_name)
        
        config = {
            "kb_dir": request.form.get('kb_dir'),
            "kb_question": request.form.get('kb_question'),
            "kb_template": request.form.get('kb_template'),
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

@app.route('/status')
def get_status(): return jsonify(execution_state)

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
        if mode == 'w': out.write(f"# Ask Repo: Technical Manual\n**Target:** {target_repo}\n\n")
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
        f.write(f"# Knowledge Base Answer\n**Folder:** {config['kb_dir']}\n**Question:** {config['kb_question']}\n\n{result}")
    execution_state["logs"] += f"\n{CLR_SUCCESS}KB Answer saved to {os.path.basename(config['output'])}{CLR_RESET}\n"
