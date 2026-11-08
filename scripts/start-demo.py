#!/usr/bin/env python3
"""Start the local demo and manual review bridge; stop only these child processes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]


def available(port):
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0


def wait_ready(url, process, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("A demo process stopped. Inspect the local log files.")
        try:
            with request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return json.load(response)
        except (OSError, ValueError, error.URLError):
            time.sleep(.25)
    raise RuntimeError("Startup timed out. Inspect the local log files.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-only", action="store_true", help="Start the chat and gateway without agents")
    parser.add_argument("--python", help="Python with the dependencies in requirements.txt installed")
    args = parser.parse_args()
    candidates = [ROOT / ".venv/bin/python"]
    python = args.python or os.environ.get("RELAY_PYTHON") or next((str(p) for p in candidates if p.is_file()), sys.executable)
    if not args.engine_only:
        checked = subprocess.run([python, "-c", "import fastapi,uvicorn,httpx,websockets"], capture_output=True)
        if checked.returncode:
            parser.error("Install requirements.txt in a virtual environment, then pass --python .venv/bin/python.")
    for port in ([4318] if args.engine_only else [4318, 4319]):
        if not available(port):
            parser.error(f"Port {port} is already in use. Stop that demo instance before starting another.")
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    os.chmod(runtime, 0o700)
    processes, streams = [], []

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        for module, name, extra, url, timeout in [
            ("engine.server", "engine", ["--port", "4318", "--bridge-port", "4319"], "http://127.0.0.1:4318/api/state", 25),
            *([] if args.engine_only else [("agents.bridge", "agents", [], "http://127.0.0.1:4319/health", 120)]),
        ]:
            stream = (runtime / f"{name}.log").open("a")
            streams.append(stream)
            child = subprocess.Popen([python, "-u", "-m", module, *extra], cwd=ROOT,
                                     stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(child)
            wait_ready(url, child, timeout)
            print(f"{name.capitalize()} ready.", flush=True)
        print("Open http://127.0.0.1:4318", flush=True)
        print("Manual review mode. Operations wait for the fictional owner's deliberate approval.", flush=True)
        print(f"Press Ctrl+C to stop these demo processes. Logs: {runtime}", flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(.5)
        raise RuntimeError("A demo process stopped. Inspect the local log files.")
    except KeyboardInterrupt:
        print("Stopping Relay.", flush=True)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        for stream in streams:
            stream.close()


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
