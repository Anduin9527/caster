#!/usr/bin/env python3
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from _config import API_URL

root = Path(__file__).resolve().parents[1]
state = root / "service.json"
lock = (root / "service.lock").open("a")
fcntl.flock(lock, fcntl.LOCK_EX)


def ticks(pid):
    return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()[19]


def owned():
    if not state.exists():
        return None
    s = json.loads(state.read_text())
    pid = s["pid"]
    try:
        if ticks(pid) != s["ticks"]:
            return None
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
        entrypoints = (b"aigc.api:app", b"scripts/start_api.py")
        if (
            not any(entrypoint in cmd for entrypoint in entrypoints)
            or Path(f"/proc/{pid}/cwd").resolve() != root
        ):
            return None
        return s
    except (OSError, ValueError):
        return None


cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
s = owned()
if cmd == "stop":
    if s:
        os.kill(s["pid"], signal.SIGTERM)
        for _ in range(100):
            if not owned():
                break
            time.sleep(0.1)
        else:
            raise SystemExit("Shutdown pending; no force kill performed")
    print(json.dumps({"running": bool(owned())}))
elif cmd == "start":
    if not s:
        log = (root / "backend.log").open("ab")
        p = subprocess.Popen(
            ["bash", str(root / "scripts/run.sh")],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        state.write_text(json.dumps({"pid": p.pid, "ticks": ticks(p.pid)}))
        for _ in range(100):
            try:
                d = json.load(urllib.request.urlopen(API_URL + "/health", timeout=1))
                if d["worker_alive"] and owned():
                    break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            raise SystemExit("Startup failed: see backend.log")
    print(json.dumps({"running": bool(owned()), "service": owned()}))
elif cmd == "status":
    try:
        health = json.load(urllib.request.urlopen(API_URL + "/health", timeout=2))
    except Exception:
        health = None
    print(json.dumps({"running": bool(s), "service": s, "health": health}))
else:
    raise SystemExit("usage: service.py start|stop|status")
