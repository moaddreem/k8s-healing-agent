"""Verification: the same independent health check the lab uses (HTTP from inside the cluster)."""
import os
import subprocess
import time
from pathlib import Path

CHECK = Path(__file__).resolve().parent.parent / "lab" / "check.sh"


def check(ns="demo"):
    """-> (healthy, output). Exit code 0 of check.sh means healthy."""
    p = subprocess.run(["bash", str(CHECK)], capture_output=True, text=True, timeout=120, env={**os.environ, "NS": ns})
    return p.returncode == 0, p.stdout.strip()


def wait_healthy(timeout=60, interval=4, ns="demo"):
    """Poll the health check until it passes or the time runs out."""
    start = time.time()
    while True:
        ok, out = check(ns)
        if ok or time.time() - start > timeout:
            return ok, out
        time.sleep(interval)
