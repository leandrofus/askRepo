import subprocess
from config import CLR_ERROR, CLR_SUCCESS

def run_git_command(args, cwd, state_proxy):
    state_proxy["logs"] += f"Executing: git {' '.join(args)}\n"
    res = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        state_proxy["logs"] += f"{CLR_ERROR}Git Error: {res.stderr}{CLR_RESET}\n"
        return False
    state_proxy["logs"] += f"{CLR_SUCCESS}Success.{CLR_RESET}\n"
    return True
