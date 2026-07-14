import os
import subprocess
import time
import signal
import sys

BASE_DIR = "/Users/hyunchanan/Documents/GitHub"
PYTHON_CMD = "/opt/homebrew/Caskroom/miniconda/base/bin/python3"
UVICORN_CMD = "/opt/homebrew/Caskroom/miniconda/base/bin/uvicorn"
STREAMLIT_CMD = "/opt/homebrew/Caskroom/miniconda/base/bin/streamlit"

modules = {
    "SG_proj_001": {"cmd": [UVICORN_CMD, "api.main:app", "--host", "0.0.0.0", "--port", "8001"], "cwd": "SG_proj_001"},
    "SG_proj_002": {"cmd": [UVICORN_CMD, "src.main:app", "--host", "0.0.0.0", "--port", "8002"], "cwd": "SG_proj_002"},
    "SG_proj_003": {"cmd": [UVICORN_CMD, "src.main:app", "--host", "0.0.0.0", "--port", "8003"], "cwd": "SG_proj_003"},
    "SG_proj_004": {"cmd": [UVICORN_CMD, "src.main:app", "--host", "0.0.0.0", "--port", "8004"], "cwd": "SG_proj_004"},
    "SG_proj_006": {"cmd": [UVICORN_CMD, "api:app", "--host", "0.0.0.0", "--port", "8506"], "cwd": "SG_proj_006"},
    "SG_proj_007": {"cmd": [UVICORN_CMD, "api:app", "--host", "0.0.0.0", "--port", "8007"], "cwd": "SG_proj_007"},
    "SG_proj_009": {"cmd": [UVICORN_CMD, "api:app", "--host", "0.0.0.0", "--port", "8009"], "cwd": "SG_proj_009"},
    "SG_proj_010": {"cmd": [UVICORN_CMD, "src.main:app", "--host", "0.0.0.0", "--port", "8010"], "cwd": "SG_proj_010"},
    "SG_proj_011": {"cmd": [UVICORN_CMD, "src.main:app", "--host", "0.0.0.0", "--port", "8011"], "cwd": "SG_proj_011"},
    "SG_proj_012": {"cmd": [UVICORN_CMD, "src.main:app", "--host", "0.0.0.0", "--port", "8012"], "cwd": "SG_proj_012"},
    "SG_proj_013": {"cmd": [UVICORN_CMD, "src.main:app", "--host", "0.0.0.0", "--port", "8013"], "cwd": "SG_proj_013"},
    "SG_proj_014": {"cmd": [UVICORN_CMD, "src.main:app", "--host", "0.0.0.0", "--port", "8024"], "cwd": "SG_proj_014"},
}

env = os.environ.copy()
env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
# Setup env vars for 014
env["MODULE_001_URL"] = "http://127.0.0.1:8001"
env["MODULE_002_URL"] = "http://127.0.0.1:8002"
env["MODULE_003_URL"] = "http://127.0.0.1:8003"
env["MODULE_004_URL"] = "http://127.0.0.1:8004"
env["MODULE_006_URL"] = "http://127.0.0.1:8506"
env["MODULE_007_URL"] = "http://127.0.0.1:8007"
env["MODULE_009_URL"] = "http://127.0.0.1:8009"
env["MODULE_010_URL"] = "http://127.0.0.1:8010"
env["MODULE_011_URL"] = "http://127.0.0.1:8011"
env["MODULE_012_URL"] = "http://127.0.0.1:8012"
env["MODULE_013_URL"] = "http://127.0.0.1:8013"
env["MODULE_014_URL"] = "http://127.0.0.1:8024"

processes = []

def cleanup(signum, frame):
    print("\nCleaning up processes...")
    for p in processes:
        p.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

print("Starting local orchestrator for all modules...")
for name, config in modules.items():
    cwd = os.path.join(BASE_DIR, config["cwd"])
    env["PYTHONPATH"] = cwd
    p = subprocess.Popen(config["cmd"], cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    processes.append(p)
    print(f"Started {name} with PID {p.pid}")

print("All modules started. Running in background. Press Ctrl+C to stop.")
while True:
    time.sleep(1)
