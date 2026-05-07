#!/usr/bin/env python3
import os
import sys
import argparse
from web import app
from config import CLR_INFO, CLR_RESET

def main():
    parser = argparse.ArgumentParser(description="Ask Repo Controller")
    parser.add_argument("--cli", action="store_true", help="Force CLI mode (Not fully modularized yet)")
    parser.add_argument("-p", "--port", type=int, default=5000, help="Port for the web UI")
    
    args, unknown = parser.parse_known_args()

    if len(sys.argv) == 1 or not args.cli:
        print(f"{CLR_INFO}[INFO] Starting Ask Repo UI on http://127.0.0.1:{args.port}{CLR_RESET}")
        app.run(host="0.0.0.0", port=args.port, debug=False)
    else:
        print("CLI mode is currently under refactor for the modular version. Use GUI or original script.")

if __name__ == "__main__":
    main()
