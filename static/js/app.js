let currentTargetId = '', currentMode = 'batch';
const folderModal = new bootstrap.Modal(document.getElementById('folderModal'));

function switchMode(mode) {
    currentMode = mode;
    ['modeBatch', 'modeKB', 'modeChat', 'modeReports'].forEach(id => document.getElementById(id).classList.toggle('active', id === 'mode' + mode.charAt(0).toUpperCase() + mode.slice(1)));
    document.getElementById('configCard').classList.toggle('d-none', mode === 'reports');
    document.getElementById('reportsCard').classList.toggle('d-none', mode !== 'reports');
    document.getElementById('monitorCard').classList.toggle('d-none', mode === 'reports' || mode === 'chat');
    document.getElementById('chatCard').classList.toggle('d-none', mode !== 'chat');
    document.getElementById('viewerCard').classList.toggle('d-none', mode !== 'reports');

    document.getElementById('batchInputs').classList.toggle('d-none', mode !== 'batch');
    document.getElementById('kbInputs').classList.toggle('d-none', mode !== 'kb');
    document.getElementById('chatSettings').classList.toggle('d-none', mode !== 'chat');
    document.getElementById('mainActionBtns').classList.toggle('d-none', mode === 'chat' || mode === 'reports');

    if (mode === 'reports') loadReportsList();
    if (mode === 'batch') document.getElementById('startBtn').innerText = 'RUN INVESTIGATION';
    if (mode === 'kb') document.getElementById('startBtn').innerText = 'ASK KNOWLEDGE BASE';
}

async function loadReportsList() {
    const res = await fetch('/results'), files = await res.json();
    const list = document.getElementById('reportsList'); list.innerHTML = '';
    files.forEach(f => {
        const btn = document.createElement('button'); btn.className = 'list-group-item list-group-item-action bg-transparent text-white border-secondary small py-3 d-flex justify-content-between';
        btn.innerHTML = `<span>📄 ${f}</span><span class="text-accent">VIEW</span>`;
        btn.onclick = async () => {
            const r = await fetch(`/results/${f}`), d = await r.json();
            document.getElementById('viewerTitle').innerText = f;
            document.getElementById('reportContent').innerHTML = d.html;
        };
        list.appendChild(btn);
    });
}

function closeViewer() { document.getElementById('reportContent').innerHTML = ''; }
function updateProviderHint() {
    const k = document.getElementById('provider').value;
    document.getElementById('model').placeholder = PROVIDERS[k].default_model;
}
updateProviderHint();

async function openFolderBrowser(tid) { currentTargetId = tid; loadDirectory(document.getElementById(tid).value || 'HOME'); folderModal.show(); }
async function loadDirectory(path) {
    const res = await fetch(`/ls?path=${encodeURIComponent(path)}`), items = await res.json();
    const container = document.getElementById('explorerContent'); container.innerHTML = `<div class="explorer-item mb-2 p-2 bg-dark border border-secondary" onclick="loadDirectory('${path.split('/').slice(0, -1).join('/') || '/'}')">⬅ .. (Go Up)</div>`;
    items.forEach(item => {
        if (!item.is_dir) return;
        const div = document.createElement('div'); div.className = 'explorer-item d-flex justify-content-between align-items-center mb-1';
        div.innerHTML = `<span>📁 ${item.name}</span>`; div.onclick = () => loadDirectory(item.path);
        const s = document.createElement('button'); s.className = 'btn btn-sm btn-primary px-3'; s.innerText = 'SELECT';
        s.onclick = (e) => { e.stopPropagation(); document.getElementById(currentTargetId).value = item.path; folderModal.hide(); };
        div.appendChild(s); container.appendChild(div);
    });
}

document.getElementById('startBtn').onclick = async () => {
    const fd = new FormData();
    fd.append('op_mode', currentMode); fd.append('provider', document.getElementById('provider').value); fd.append('model', document.getElementById('model').value);
    if (currentMode === 'batch') {
        fd.append('prompt', document.getElementById('systemPrompt').value); fd.append('task_template', document.getElementById('taskTemplate').value);
        fd.append('repo', document.getElementById('repoDir').value); fd.append('output', document.getElementById('outputFile').value);
        fd.append('mode', document.getElementById('parseMode').value); fd.append('git_url', document.getElementById('gitUrl').value);
        const fi = document.getElementById('fileInput'); if (fi.files[0]) fd.append('file', fi.files[0]); else { alert("File required"); return; }
    } else {
        fd.append('kb_dir', document.getElementById('kbDir').value); fd.append('kb_question', document.getElementById('kbQuestion').value);
        if (!document.getElementById('kbDir').value || !document.getElementById('kbQuestion').value) { alert("Missing fields"); return; }
    }
    await fetch('/run', { method: 'POST', body: fd });
};

const chatInput = document.getElementById('chatInput'), chatSendBtn = document.getElementById('chatSendBtn'), chatBox = document.getElementById('chatBox');

chatInput.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'Enter') {
        e.preventDefault();
        chatSendBtn.click();
    }
});

chatSendBtn.onclick = async () => {
    const msg = chatInput.value; if (!msg) return;
    appendMessage('user', msg); chatInput.value = '';
    const res = await fetch('/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
            message: msg, 
            repo: document.getElementById('chatRepo').value, 
            provider: document.getElementById('provider').value, 
            model: document.getElementById('model').value,
            system_prompt: document.getElementById('chatSystemPrompt').value
        })
    });
};

function appendMessage(role, text) {
    const div = document.createElement('div'); 
    div.className = `chat-bubble bubble-${role} ${role === 'assistant' ? 'markdown-content' : ''}`;
    if (role === 'assistant') {
        div.innerHTML = marked.parse(text);
    } else {
        div.innerText = text;
    }
    chatBox.appendChild(div); 
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function clearChat() { await fetch('/chat/clear', { method: 'POST' }); chatBox.innerHTML = ''; }

async function updateStatus() {
    const res = await fetch('/status'), data = await res.json();
    const badge = document.getElementById('statusBadge'), startC = document.getElementById('startBtnContainer'), stopC = document.getElementById('stopBtnContainer'), resumeC = document.getElementById('resumeBtnContainer');
    if (data.is_running) { badge.className = "badge bg-success"; badge.innerHTML = "RUNNING"; startC.className = "col-6"; stopC.className = "col-6"; resumeC.className = "col-6 d-none"; }
    else {
        badge.className = "badge bg-secondary"; badge.innerHTML = "IDLE";
        if (data.mode === 'batch' && data.progress > 0 && data.progress < data.total) { startC.className = "col-4"; stopC.className = "col-4 d-none"; resumeC.className = "col-8"; }
        else { startC.className = "col-12"; stopC.className = "col-6 d-none"; resumeC.className = "col-6 d-none"; }
    }
    document.getElementById('progressBar').style.width = (data.total > 0 ? (data.progress / data.total) * 100 : 0) + "%";
    document.getElementById('progressText').innerHTML = Math.round(data.total > 0 ? (data.progress / data.total) * 100 : 0) + "%";
    document.getElementById('countText').innerHTML = data.progress + " / " + data.total;
    document.getElementById('currentTask').innerHTML = data.current_task || "-";
    document.getElementById('logOutput').innerHTML = data.logs;

    // Sync chat history
    if (currentMode === 'chat' && data.chat_history.length > chatBox.children.length) {
        chatBox.innerHTML = ''; data.chat_history.forEach(m => appendMessage(role_map(m.role), m.text));
    }
}
const role_map = r => r === 'assistant' ? 'assistant' : 'user';
setInterval(updateStatus, 800);
