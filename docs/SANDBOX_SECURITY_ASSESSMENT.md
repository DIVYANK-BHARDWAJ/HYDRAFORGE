# HYDRAFORGE — Sandbox Security Assessment
**Scope:** Docker Isolated Runner & Untrusted Code Execution Boundary  
**Date:** 2026-11-05  

---

## 1. 20-Point Security Test Battery Results

Every security control was evaluated through automated offensive payloads in `tests/test_worker_security.py`. All 20 tests passed:

1. **Infinite Loop Enforcement**: Terminated at exactly 300s via `ResourceMonitor` SIGKILL.
2. **Excessive Memory Allocation**: OOM killed by cgroups at 4GB cap; host system unaffected.
3. **CPU Core Exhaustion**: Hard capped at 2.0 CPUs; no starvation of host processes.
4. **Process Fork Bomb**: Limited by `pids-limit 64`; child fork attempts rejected by kernel.
5. **Filesystem Traversal**: Sandboxed in `/workspace`; host paths (`/etc`, `/root`, `/home`) unreadable.
6. **Symlink Escape**: Symlinks resolving outside the repository directory fail validation before mounting.
7. **Ground-Truth Label Exfiltration**: Hidden labels stored outside the container mount tree; inaccessible.
8. **Host File Access**: Read-only mounts prevent any writes to host storage.
9. **Docker Socket Access**: `/var/run/docker.sock` is strictly forbidden from participant mounts.
10. **Cross-Tenant Data Exposure**: Scratch directories are cryptographically salted per job ID (`job_<uuid>`).
11. **Network Services Access**: Container launched with `--network none`; DNS and socket operations fail immediately.
12. **Malicious Dependency Execution**: `setup.py` / `pip install` executed in isolated build container with timeout.
13. **Malicious setup.py**: Arbitrary code execution during install trapped inside container.
14. **Malicious README Commands**: Markdown instructions are parsed for metadata only; never executed.
15. **Output Path Traversal**: Output paths resolving with `../` are rejected by `OutputCollector`.
16. **Output Symlink Manipulation**: Symlinked output files are rejected and uncollected.
17. **Timeout Enforcement**: Enforced at container level and thread watchdog level.
18. **Clean Worker Termination**: Container removed (`docker rm -f`) on any exit signal.
19. **Cleanup After Failure**: Scratch files and containers completely wiped on failure.
20. **Fail-Closed on Worker Unavailable**: If Docker daemon is unreachable, execution halts fail-closed.

