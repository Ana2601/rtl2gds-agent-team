from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path, timeout: int = 600, env: dict | None = None) -> tuple[int, str]:
    """Run a tool; on timeout kill the whole process group."""
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         start_new_session=True, env={**os.environ, **(env or {})})
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, _ = p.communicate()
        return 124, (out or "") + f"\nTIMEOUT after {timeout}s"
