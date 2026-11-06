"""HYDRAFORGE — Automated Evaluation Engine for the BASINSHIFT Hydrological Challenge.

Provides submission contract validation, secure execution isolation,
and a deterministic 6-dimension evaluation metric engine.
"""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv_if_present() -> None:
    """Load key-value pairs from root .env into os.environ without requiring external packages."""
    root_dir = Path(__file__).resolve().parent.parent
    env_file = root_dir / ".env"
    if not env_file.is_file():
        env_file = Path(".env")
    if env_file.is_file():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass


_load_dotenv_if_present()

__version__ = "0.1.0"
__contract_version__ = "1.0.0"
