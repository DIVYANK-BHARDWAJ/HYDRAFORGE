"""Repository Integrity, File Tree Hashing, and Artifact Fingerprinting."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List, Tuple


def compute_tree_hash(root_dir: Path) -> str:
    """Compute deterministic SHA-256 tree hash over all regular files in a directory."""
    root_dir = Path(root_dir).resolve()
    file_hashes: List[Tuple[str, str]] = []

    for path in sorted(root_dir.rglob("*")):
        if path.is_file() and not path.is_symlink():
            rel_path = str(path.relative_to(root_dir)).replace("\\", "/")
            hasher = hashlib.sha256()
            try:
                with open(path, "rb") as f:
                    while chunk := f.read(65536):
                        hasher.update(chunk)
                file_hashes.append((rel_path, hasher.hexdigest()))
            except OSError:
                pass

    tree_hasher = hashlib.sha256()
    for rel_path, file_hash in file_hashes:
        entry = f"{rel_path}:{file_hash}\n"
        tree_hasher.update(entry.encode("utf-8"))

    return tree_hasher.hexdigest()

