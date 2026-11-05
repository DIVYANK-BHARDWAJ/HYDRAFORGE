"""Isolation Policies, Environment Scrubbing, and Hidden-Label Protection."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Set

DANGEROUS_ENV_PREFIXES: Tuple[str, ...] = (
    "AWS_",
    "AZURE_",
    "GCP_",
    "GOOGLE_",
    "GITHUB_",
    "GITLAB_",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "API_KEY",
    "PRIVATE_",
    "DATABASE_",
    "MONGO_",
    "POSTGRES_",
    "HTTP_PROXY",
    "HTTPS_PROXY"
)


class LabelLeakageSecurityViolation(Exception):
    """Raised when ground-truth labels are detected in a participant execution path."""
    pass


def scrub_environment(base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return a sanitized environment stripped of secrets, tokens, and proxies."""
    source = base_env if base_env is not None else os.environ

    safe_env: Dict[str, str] = {
        # Retain standard runtime variables
        "PATH": source.get("PATH", ""),
        "SYSTEMROOT": source.get("SYSTEMROOT", "C:\\Windows"),
        "WINDIR": source.get("WINDIR", "C:\\Windows"),
        "TEMP": source.get("TEMP", "/tmp"),
        "TMP": source.get("TMP", "/tmp"),
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HYDRAFORGE_ISOLATED": "1"
    }

    # Pass through only safe, non-sensitive variables
    for k, v in source.items():
        k_upper = k.upper()
        if any(k_upper.startswith(prefix) for prefix in DANGEROUS_ENV_PREFIXES):
            continue
        if "KEY" in k_upper or "SECRET" in k_upper or "TOKEN" in k_upper or "AUTH" in k_upper:
            continue
        safe_env[k] = v

    return safe_env


def verify_hidden_label_shielding(
    input_path: Path,
    command_args: List[str],
    environment: Dict[str, str]
) -> None:
    """Strictly assert that no ground-truth label directory or parameter is exposed.

    Guarantees:
    - input_path does not point to labels directory.
    - command_args do not contain references to 'labels.json' or 'labels'.
    - environment does not contain label file paths or targets.
    """
    input_str = str(input_path).replace("\\", "/").lower()

    if "/labels" in input_str or "labels.json" in input_str:
        raise LabelLeakageSecurityViolation(
            f"SECURITY VIOLATION: Participant input path points to organizer label storage: '{input_path}'"
        )

    for arg in command_args:
        arg_norm = arg.replace("\\", "/").lower()
        if "/labels/" in arg_norm or "labels.json" in arg_norm:
            raise LabelLeakageSecurityViolation(
                f"SECURITY VIOLATION: Command-line arguments expose hidden ground-truth labels: '{arg}'"
            )

    for k, v in environment.items():
        v_norm = str(v).replace("\\", "/").lower()
        if "/labels/" in v_norm or "labels.json" in v_norm:
            raise LabelLeakageSecurityViolation(
                f"SECURITY VIOLATION: Environment variable '{k}' exposes hidden label path: '{v}'"
            )

