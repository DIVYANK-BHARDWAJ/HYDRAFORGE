"""
hydraforge/discovery/manifest_detector.py
Static, unprivileged project manifest and dependency parser.
Extracts declared dependencies, Python versions, and package entrypoints
WITHOUT executing setup.py, running pip, or installing packages.
"""

from __future__ import annotations

import ast
import configparser
import os
import re
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from hydraforge.discovery.discovery_models import (
    ConfidenceLevel,
    ManifestRecord,
)


class ManifestDetector:
    """Detects and parses package manifests safely without code execution."""

    def detect_manifests(
        self,
        repo_root: Path
    ) -> Tuple[List[ManifestRecord], List[str], List[str]]:
        """
        Scan repository directory for manifests and extract dependencies.
        Returns:
            (manifest_records, aggregate_unique_dependencies, warnings)
        """
        repo_root = Path(repo_root).resolve()
        manifest_records: List[ManifestRecord] = []
        all_deps: Set[str] = set()
        warnings: List[str] = []

        for root, _, files in os.walk(repo_root):
            for fname in files:
                fpath = Path(root) / fname
                rel_path = fpath.relative_to(repo_root).as_posix()
                fname_lower = fname.lower()

                # 1. requirements.txt and variants
                if fname_lower.startswith("requirements") and fname_lower.endswith(".txt"):
                    rec = self._parse_requirements_txt(fpath, rel_path, warnings)
                    if rec:
                        manifest_records.append(rec)
                        all_deps.update(rec.declared_dependencies)

                # 2. pyproject.toml
                elif fname_lower == "pyproject.toml":
                    rec = self._parse_pyproject_toml(fpath, rel_path, warnings)
                    if rec:
                        manifest_records.append(rec)
                        all_deps.update(rec.declared_dependencies)

                # 3. setup.cfg
                elif fname_lower == "setup.cfg":
                    rec = self._parse_setup_cfg(fpath, rel_path, warnings)
                    if rec:
                        manifest_records.append(rec)
                        all_deps.update(rec.declared_dependencies)

                # 4. setup.py (AST static parse ONLY, never execute)
                elif fname_lower == "setup.py":
                    rec = self._parse_setup_py_ast(fpath, rel_path, warnings)
                    if rec:
                        manifest_records.append(rec)
                        all_deps.update(rec.declared_dependencies)

                # 5. Pipfile
                elif fname_lower == "pipfile":
                    rec = self._parse_pipfile(fpath, rel_path, warnings)
                    if rec:
                        manifest_records.append(rec)
                        all_deps.update(rec.declared_dependencies)

                # 6. environment.yml / conda.yaml
                elif fname_lower in ("environment.yml", "environment.yaml", "conda.yml", "conda.yaml"):
                    rec = self._parse_conda_yaml(fpath, rel_path, warnings)
                    if rec:
                        manifest_records.append(rec)
                        all_deps.update(rec.declared_dependencies)

                # 7. Dockerfile
                elif fname_lower == "dockerfile" or fname_lower.startswith("dockerfile."):
                    rec = self._parse_dockerfile(fpath, rel_path, warnings)
                    if rec:
                        manifest_records.append(rec)

                # 8. Makefile
                elif fname_lower in ("makefile", "gnumakefile"):
                    rec = self._parse_makefile(fpath, rel_path, warnings)
                    if rec:
                        manifest_records.append(rec)

        return manifest_records, sorted(list(all_deps)), warnings

    def _parse_requirements_txt(
        self, fpath: Path, rel_path: str, warnings: List[str]
    ) -> Optional[ManifestRecord]:
        """Safely parse pip requirements lines."""
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            warnings.append(f"Could not read '{rel_path}': {e}")
            return None

        dependencies: List[str] = []
        for line in lines:
            line = line.strip()
            # Ignore comments, empty lines, and pip flags (-r, -i, -f, --extra-index-url)
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Strip trailing comments
            clean_dep = line.split("#")[0].strip()
            if clean_dep:
                dependencies.append(clean_dep)

        return ManifestRecord(
            path=rel_path,
            manifest_type="requirements.txt",
            declared_dependencies=dependencies,
            confidence=ConfidenceLevel.HIGH,
            raw_config_summary={"dependency_count": len(dependencies)}
        )

    def _parse_pyproject_toml(
        self, fpath: Path, rel_path: str, warnings: List[str]
    ) -> Optional[ManifestRecord]:
        """Parse PEP 621 / Poetry pyproject.toml."""
        try:
            with open(fpath, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            warnings.append(f"Malformed pyproject.toml at '{rel_path}': {e}")
            return None

        deps: List[str] = []
        entrypoints: Dict[str, str] = {}
        py_version: Optional[str] = None

        # Standard PEP 621 [project]
        project = data.get("project", {})
        if isinstance(project, dict):
            deps.extend(project.get("dependencies", []))
            py_version = project.get("requires-python")
            # [project.scripts]
            scripts = project.get("scripts", {})
            if isinstance(scripts, dict):
                for k, v in scripts.items():
                    entrypoints[k] = str(v)

        # Poetry [tool.poetry]
        poetry = data.get("tool", {}).get("poetry", {})
        if isinstance(poetry, dict):
            p_deps = poetry.get("dependencies", {})
            if isinstance(p_deps, dict):
                for pkg, spec in p_deps.items():
                    if pkg.lower() == "python":
                        py_version = str(spec)
                    else:
                        deps.append(f"{pkg} ({spec})" if spec != "*" else pkg)
            # [tool.poetry.scripts]
            p_scripts = poetry.get("scripts", {})
            if isinstance(p_scripts, dict):
                for k, v in p_scripts.items():
                    entrypoints[k] = str(v)

        return ManifestRecord(
            path=rel_path,
            manifest_type="pyproject.toml",
            declared_dependencies=deps,
            python_version=py_version,
            entrypoints=entrypoints,
            confidence=ConfidenceLevel.HIGH,
            raw_config_summary={"has_project_section": bool(project), "has_poetry": bool(poetry)}
        )

    def _parse_setup_cfg(
        self, fpath: Path, rel_path: str, warnings: List[str]
    ) -> Optional[ManifestRecord]:
        """Parse setup.cfg metadata and options."""
        cfg = configparser.ConfigParser()
        try:
            cfg.read(fpath, encoding="utf-8")
        except Exception as e:
            warnings.append(f"Malformed setup.cfg at '{rel_path}': {e}")
            return None

        deps: List[str] = []
        entrypoints: Dict[str, str] = {}
        py_version: Optional[str] = None

        if cfg.has_section("options"):
            install_req = cfg.get("options", "install_requires", fallback="")
            if install_req:
                deps.extend([d.strip() for d in install_req.splitlines() if d.strip()])
            py_version = cfg.get("options", "python_requires", fallback=None)

        if cfg.has_section("options.entry_points"):
            for k, v in cfg.items("options.entry_points"):
                entrypoints[k] = v.strip()

        return ManifestRecord(
            path=rel_path,
            manifest_type="setup.cfg",
            declared_dependencies=deps,
            python_version=py_version,
            entrypoints=entrypoints,
            confidence=ConfidenceLevel.HIGH,
            raw_config_summary={"sections": cfg.sections()}
        )

    def _parse_setup_py_ast(
        self, fpath: Path, rel_path: str, warnings: List[str]
    ) -> Optional[ManifestRecord]:
        """
        Static AST analysis of setup.py.
        STRICT SECURITY: Never executes, imports, or invokes setup.py.
        """
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            tree = ast.parse(content, filename=rel_path)
        except Exception as e:
            warnings.append(f"Failed to parse AST of '{rel_path}': {e}")
            return None

        deps: List[str] = []
        entrypoints: Dict[str, str] = {}
        py_version: Optional[str] = None

        # Inspect AST calls looking for setup(...)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if func_name == "setup":
                    for kw in node.keywords:
                        if kw.arg == "install_requires" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            for elt in kw.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    deps.append(elt.value)
                        elif kw.arg == "python_requires" and isinstance(kw.value, ast.Constant):
                            py_version = str(kw.value.value)
                        elif kw.arg == "entry_points":
                            if isinstance(kw.value, ast.Dict):
                                for k, v in zip(kw.value.keys, kw.value.values):
                                    if isinstance(k, ast.Constant):
                                        entrypoints[str(k.value)] = "declared_in_setup_py"

        return ManifestRecord(
            path=rel_path,
            manifest_type="setup.py",
            declared_dependencies=deps,
            python_version=py_version,
            entrypoints=entrypoints,
            confidence=ConfidenceLevel.MEDIUM,
            raw_config_summary={"parsed_via_static_ast": True}
        )

    def _parse_pipfile(
        self, fpath: Path, rel_path: str, warnings: List[str]
    ) -> Optional[ManifestRecord]:
        """Parse Pipfile format."""
        try:
            with open(fpath, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            warnings.append(f"Malformed Pipfile at '{rel_path}': {e}")
            return None

        deps: List[str] = []
        packages = data.get("packages", {})
        if isinstance(packages, dict):
            for pkg, ver in packages.items():
                deps.append(f"{pkg} ({ver})" if ver != "*" else pkg)

        return ManifestRecord(
            path=rel_path,
            manifest_type="Pipfile",
            declared_dependencies=deps,
            confidence=ConfidenceLevel.HIGH,
            raw_config_summary={"packages_count": len(deps)}
        )

    def _parse_conda_yaml(
        self, fpath: Path, rel_path: str, warnings: List[str]
    ) -> Optional[ManifestRecord]:
        """Parse environment.yml / conda.yaml format."""
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            warnings.append(f"Malformed conda environment YAML at '{rel_path}': {e}")
            return None

        deps: List[str] = []
        py_version: Optional[str] = None

        if isinstance(data, dict):
            raw_deps = data.get("dependencies", [])
            if isinstance(raw_deps, list):
                for item in raw_deps:
                    if isinstance(item, str):
                        if item.startswith("python="):
                            py_version = item.split("=")[1]
                        else:
                            deps.append(item)
                    elif isinstance(item, dict) and "pip" in item:
                        pip_items = item.get("pip", [])
                        if isinstance(pip_items, list):
                            for p in pip_items:
                                if isinstance(p, str):
                                    deps.append(f"{p} (pip)")

        return ManifestRecord(
            path=rel_path,
            manifest_type="conda.yaml",
            declared_dependencies=deps,
            python_version=py_version,
            confidence=ConfidenceLevel.HIGH,
            raw_config_summary={"conda_channels": data.get("channels", []) if isinstance(data, dict) else []}
        )

    def _parse_dockerfile(
        self, fpath: Path, rel_path: str, warnings: List[str]
    ) -> Optional[ManifestRecord]:
        """Extract ENTRYPOINT, CMD, and base image from Dockerfile without executing."""
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            warnings.append(f"Could not read Dockerfile '{rel_path}': {e}")
            return None

        entrypoints: Dict[str, str] = {}
        cmd_match = re.search(r"^\s*CMD\s+(.*)$", content, re.MULTILINE)
        if cmd_match:
            entrypoints["docker_cmd"] = cmd_match.group(1).strip()

        entry_match = re.search(r"^\s*ENTRYPOINT\s+(.*)$", content, re.MULTILINE)
        if entry_match:
            entrypoints["docker_entrypoint"] = entry_match.group(1).strip()

        from_match = re.search(r"^\s*FROM\s+([^\s]+)", content, re.MULTILINE)
        base_img = from_match.group(1).strip() if from_match else "unknown"

        return ManifestRecord(
            path=rel_path,
            manifest_type="Dockerfile",
            entrypoints=entrypoints,
            confidence=ConfidenceLevel.MEDIUM,
            raw_config_summary={"base_image": base_img}
        )

    def _parse_makefile(
        self, fpath: Path, rel_path: str, warnings: List[str]
    ) -> Optional[ManifestRecord]:
        """Extract target rules from Makefile without running make."""
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            warnings.append(f"Could not read Makefile '{rel_path}': {e}")
            return None

        targets = re.findall(r"^([a-zA-Z0-9_-]+):", content, re.MULTILINE)
        entrypoints = {f"make_{t}": f"make {t}" for t in targets}

        return ManifestRecord(
            path=rel_path,
            manifest_type="Makefile",
            entrypoints=entrypoints,
            confidence=ConfidenceLevel.LOW,
            raw_config_summary={"targets": targets}
        )

