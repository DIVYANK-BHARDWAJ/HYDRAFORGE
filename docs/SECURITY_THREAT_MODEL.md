# HYDRAFORGE — Security Threat Model
**System:** Automated Untrusted Machine Learning Evaluation Platform  
**Model Framework:** STRIDE & Defense-in-Depth  
**Date:** 2026-11-05  

---

## 1. Threat Landscape & Trust Boundaries

```
[ UNTRUSTED ZONE ]           [ BOUNDARY 1 ]          [ ISOLATION SANDBOX ]       [ BOUNDARY 2 ]          [ TRUSTED ZONE ]
Participant GitHub Repo  ---> SSRF Filter   ---> Docker Isolated Container ---> Output Validator ---> Host Evaluator / DB
(Arbitrary Code/Deps)         & Commit Pin         (--network none, UID 10001)   (Schema & Bounds)     (Hidden Ground Truth)
```

---

## 2. STRIDE Threat Analysis Matrix

| Threat Category | Specific Attack Vector | Mitigation Control | Verification Test |
| :--- | :--- | :--- | :--- |
| **Spoofing** | Participant submits malicious commit after intake | Server captures immutable 40-char SHA at intake; worker checks out exact SHA | `test_immutable_commit_preservation` |
| **Tampering** | Model attempts to modify ground-truth benchmark files | Input directory mounted read-only; labels stored in non-mounted separate directory | `test_attempts_to_read_hidden_labels` |
| **Repudiation** | Team disputes score or claims different code evaluated | Complete audit log with input SHA256, output SHA256, and telemetry hash recorded in DB | `test_complete_end_to_end_synthetic_scoring_workflow` |
| **Information Disclosure** | SSRF attack via repository URL (AWS IMDS `169.254.169.254`, internal services) | Strict URL validation, DNS resolution checks, private CIDR filtering | `test_repository_url_ssrf_direct_private_ip_rejected` |
| **Denial of Service** | Infinite loops, memory bombs, fork bombs, GPU exhaustion | Non-root UID, cgroups limits (4GB RAM, 2 CPU), pids limit 64, 300s timeout | `test_1_infinite_loop`, `test_2_excessive_memory_allocation` |
| **Elevation of Privilege** | Container escape to host filesystem or Docker socket | Capabilities dropped (`--cap-drop ALL`), `no-new-privileges`, Docker socket never mounted into sandbox | `test_9_attempts_to_access_docker_socket` |

---

## 3. Defense-in-Depth Principles

1. **Fail-Closed Default**: Any timeout, crash, or unexpected behavior immediately terminates execution with zero score awarded.
2. **Zero-Trust Network**: Containers run with `--network none`. No outbound socket can be opened.
3. **Least Privilege**: Workers and participant containers execute under unprivileged user IDs (`10001:10001`).
