"""Process Resource Monitoring and Timeout Supervisor."""

from __future__ import annotations

import subprocess
import time
from typing import Optional, Tuple
import psutil

from hydraforge.runner.errors import ExecutionTimeoutError, ResourceLimitExceededError


def run_process_with_monitoring(
    args: list[str],
    cwd: str,
    env: dict[str, str],
    timeout_seconds: int = 300,
    max_memory_mb: float = 4096.0,
    poll_interval_sec: float = 0.1
) -> Tuple[int, str, str, float, Optional[float]]:
    """Execute a process tree with strict wall-clock timeout and peak RSS memory tracking.

    Returns:
        (exit_code, stdout, stderr, runtime_seconds, peak_memory_mb)
    """
    start_time = time.perf_counter()
    peak_rss_bytes = 0

    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        ps_proc = psutil.Process(proc.pid)
    except psutil.NoSuchProcess:
        ps_proc = None

    stdout_data = ""
    stderr_data = ""

    while proc.poll() is None:
        elapsed = time.perf_counter() - start_time
        if elapsed > timeout_seconds:
            # Terminate and kill entire process tree
            _kill_process_tree(proc.pid)
            proc.wait(timeout=5)
            raise ExecutionTimeoutError(
                f"Execution exceeded timeout limit of {timeout_seconds} seconds (elapsed: {elapsed:.2f}s)."
            )

        # Track memory usage of process and all descendants
        if ps_proc and ps_proc.is_running():
            try:
                current_rss = ps_proc.memory_info().rss
                for child in ps_proc.children(recursive=True):
                    try:
                        current_rss += child.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                if current_rss > peak_rss_bytes:
                    peak_rss_bytes = current_rss

                current_mb = current_rss / (1024 * 1024)
                if current_mb > max_memory_mb:
                    _kill_process_tree(proc.pid)
                    proc.wait(timeout=5)
                    raise ResourceLimitExceededError(
                        f"Memory usage ({current_mb:.1f} MB) exceeded limit of {max_memory_mb:.1f} MB."
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        time.sleep(poll_interval_sec)

    stdout_data, stderr_data = proc.communicate()
    runtime = time.perf_counter() - start_time
    peak_mb = (peak_rss_bytes / (1024 * 1024)) if peak_rss_bytes > 0 else None

    return proc.returncode, stdout_data, stderr_data, runtime, peak_mb


def _kill_process_tree(pid: int) -> None:
    """Terminate and kill all descendants of a process tree."""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        parent.terminate()
        # Give grace period then force kill
        _, still_alive = psutil.wait_procs(children + [parent], timeout=2.0)
        for p in still_alive:
            try:
                p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

