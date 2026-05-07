# 🚀 Ask Repo: Autonomous Investigation & Intelligence Engine

**Ask Repo** is a polyvalent, multi-provider orchestration engine designed for autonomous research, codebase auditing, and document intelligence. By leveraging agentic LLMs with full tool access, it transcends simple code inspection to become a comprehensive research assistant capable of investigating any topic through local data or the live web.

---

## ✨ Polyvalent Intelligence Features

- 🌐 **Web-Augmented Research:** Integrated web search capabilities allow the engine to fetch real-time information, verify facts, and research topics beyond the local environment.
- 🏗️ **Autonomous Code Auditing:** Surgical analysis of repositories for architectural mapping, security vulnerabilities, and logic flows (Batch Mode).
- 🧠 **Omniscient Knowledge Base:** Processes unstructured document folders (.pdf, .md, .docx, .txt) to act as a specialized consultant on your private data.
- 💬 **Interactive Agentic Chat:** Real-time, tool-enabled conversation. The agent can read files, execute shell commands, and perform web searches to fulfill complex requests.
- 🤖 **Multi-Provider Orchestration:** Seamlessly switch between Gemini (with Tool Use), Ollama, Claude, and custom CLI-based models.
- 🎨 **Premium Cyberpunk UI:** A high-contrast, real-time dashboard designed for monitoring complex multi-step investigations.

---

## 🚀 Quick Start

### 1. Prerequisites
- **Python 3.10+**
- An LLM CLI tool (e.g., `gemini-cli` or `ollama`).
- *Note: For web search and tool-use, the `gemini` provider with a compatible agent is recommended.*

### 2. Installation
```bash
git clone https://github.com/leandrofus/askrepo.git
cd Askrepo
pip install -r requirements.txt
```

### 3. Run
```bash
python3 main.py
```
Access the dashboard at [http://127.0.0.1:5000](http://127.0.0.1:5000).

---

## ⚙️ Operational Modes

### 1. 📂 Batch Repo (Code Investigation)
Automate the analysis of massive codebases. Upload a `taskfile` (list of investigation points) and let the engine generate a comprehensive Markdown report.
- **Use Case:** "Generate a security audit of all authentication endpoints."

### 2. 🧠 Knowledge Base (Document Research)
Point the engine to a folder of documents. It will use its tools to search, read, and synthesize information from your local files.
- **Use Case:** "Explain our company's remote work policy based on these PDF manuals."

### 3. 💬 Interactive Chat (Polyvalent Assistant)
A free-form environment where the agent has full autonomy. It can explore your repository, search the web for documentation, or help you learn a new technology from scratch.
- **Use Case:** "Investigate why this library is deprecated and find a modern alternative using web search."

---

## 🧠 Prompt Engineering: Defining Your Agent

Customize the **System Prompt** to pivot the engine's expertise:

1.  **The Global Researcher:** 
    > "You are a polyvalent research assistant. Use web search to complement local data. Provide deep dives into technical topics with cited sources."
2.  **The Cyber-Security Auditor:** 
    > "You are a Senior Pen-tester. Focus on exploitability, CVE matching via web search, and local code vulnerabilities."
3.  **The Technical Consultant:** 
    > "Act as a specialized consultant. Analyze the provided documentation and explain complex concepts to non-technical stakeholders."

---

## 🏗️ Architecture

- `main.py`: Application entry point.
- `web.py`: Flask-based control plane and real-time monitoring.
- `engine.py`: The orchestration layer that interfaces with agentic CLI tools.
- `parser.py`: Logic for processing structured task lists.
- `results/`: Persistent storage for generated intelligence reports.

---

## 📜 License
MIT License - Developed with ❤️ by **Leandro Fusco**
