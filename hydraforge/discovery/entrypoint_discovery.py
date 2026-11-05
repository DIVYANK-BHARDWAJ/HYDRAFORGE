"""
hydraforge/discovery/entrypoint_discovery.py
Static entrypoint discovery engine.
Combines manifest scripts, documentation commands, and static AST analysis
of Python files to detect inference interfaces without executing participant code.
Safely detects ambiguities and never guesses when multiple candidates exist.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from hydraforge.discovery.discovery_models import (
    CandidateEntrypoint,
    CommandType,
    ConfidenceLevel,
    DiscoveredCommand,
    InterfaceStatus,
    ManifestRecord,
    ProposedInterfaceMapping,
)


class EntrypointDiscovery:
    """Discovers inference entry points statically across manifests, docs, and code AST."""

    def discover_entrypoints(
        self,
        repo_root: Path,
        manifest_records: List[ManifestRecord],
        doc_commands: List[DiscoveredCommand],
        python_files: List[str]
    ) -> Tuple[List[CandidateEntrypoint], InterfaceStatus, Optional[ProposedInterfaceMapping], List[str]]:
        """
        Synthesize evidence from manifests, documentation, and AST analysis.
        Returns:
            (candidate_entrypoints, interface_status, proposed_mapping, warnings)
        """
        repo_root = Path(repo_root).resolve()
        candidates: List[CandidateEntrypoint] = []
        warnings: List[str] = []

        # 1. Inspect manifest-declared console scripts
        for m in manifest_records:
            for script_name, target in m.entrypoints.items():
                if any(k in script_name.lower() for k in ("predict", "infer", "forecast", "run", "model")):
                    # Resolve module to relative file path if possible
                    mod_part = target.split(":")[0].strip()
                    potential_path = mod_part.replace(".", "/") + ".py"
                    resolved_file = m.path
                    for prefix in ("", "src/"):
                        cand_path = f"{prefix}{potential_path}"
                        if (repo_root / cand_path).is_file():
                            resolved_file = cand_path
                            break

                    candidates.append(CandidateEntrypoint(
                        file_path=resolved_file,
                        entrypoint_type="package_script",
                        callable_name=target,
                        detected_purpose=CommandType.INFERENCE,
                        confidence=ConfidenceLevel.HIGH,
                        execution_signature=f"{script_name} ({target})",
                        input_arguments=[],
                        output_arguments=[]
                    ))

        # 2. Inspect documented inference commands
        for cmd in doc_commands:
            if cmd.command_type == CommandType.INFERENCE and cmd.executable_script:
                script_path = cmd.executable_script
                # Normalize path relative to repo root
                norm_script = script_path.replace("\\", "/").lstrip("./")
                candidates.append(CandidateEntrypoint(
                    file_path=norm_script,
                    entrypoint_type="documented_command",
                    args_parser="cli",
                    detected_purpose=CommandType.INFERENCE,
                    confidence=cmd.confidence,
                    execution_signature=cmd.raw_command,
                    input_arguments=cmd.input_flags,
                    output_arguments=cmd.output_flags,
                ))

        # 3. Static AST analysis of candidate Python source files
        for rel_py in python_files:
            abs_py = repo_root / rel_py
            if not abs_py.is_file():
                continue

            ast_cand = self._inspect_python_file_ast(abs_py, rel_py, warnings)
            if ast_cand:
                # Avoid duplicate if already found with higher confidence
                existing = [c for c in candidates if c.file_path == rel_py]
                if not existing:
                    candidates.append(ast_cand)

        # 4. Filter and score candidate inference entrypoints
        inference_candidates = [
            c for c in candidates
            if c.detected_purpose in (CommandType.INFERENCE, CommandType.EVALUATION)
        ]

        # 5. Interface Status Determination (Fail-Closed, Non-Guessing Policy)
        if not inference_candidates:
            # Check if there are training scripts
            has_train = any(c.detected_purpose == CommandType.TRAINING for c in candidates)
            if has_train:
                warnings.append("Detected model training entrypoints, but no recognizable inference interface.")
            return candidates, InterfaceStatus.INTERFACE_NOT_FOUND, None, warnings

        # Deduplicate candidates referencing the exact same file
        unique_targets: Dict[str, CandidateEntrypoint] = {}
        for c in inference_candidates:
            tgt = c.file_path.replace("\\", "/").lstrip("./")
            if tgt not in unique_targets or (c.confidence == ConfidenceLevel.HIGH and unique_targets[tgt].confidence != ConfidenceLevel.HIGH):
                unique_targets[tgt] = c

        distinct_candidates = list(unique_targets.values())

        if len(distinct_candidates) == 1:
            chosen = distinct_candidates[0]
            mapping = self._build_proposed_mapping(chosen)
            return candidates, InterfaceStatus.INTERFACE_IDENTIFIED, mapping, warnings

        # Multiple candidate inference entrypoints exist!
        # NON-NEGOTIABLE PRINCIPLE: Do NOT guess! Classify as INTERFACE_AMBIGUOUS.
        ambiguous_scripts = [c.file_path for c in distinct_candidates]
        warnings.append(
            f"Ambiguous inference interface: detected {len(distinct_candidates)} candidate "
            f"entrypoints ({', '.join(ambiguous_scripts)}). Manual organizer clarification required."
        )
        return candidates, InterfaceStatus.INTERFACE_AMBIGUOUS, None, warnings

    def _inspect_python_file_ast(
        self, abs_path: Path, rel_path: str, warnings: List[str]
    ) -> Optional[CandidateEntrypoint]:
        """Perform static AST analysis on a Python module without executing it."""
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
            tree = ast.parse(source, filename=rel_path)
        except Exception as e:
            # SyntaxError or encoding issues in participant code
            return None

        has_main_guard = False
        args_parser: Optional[str] = None
        input_args: List[str] = []
        output_args: List[str] = []
        is_training = False
        is_inference = False
        callable_name: Optional[str] = None

        # Inspect AST nodes
        for node in ast.walk(tree):
            # Check for if __name__ == '__main__':
            if isinstance(node, ast.If):
                test = node.test
                if isinstance(test, ast.Compare):
                    left = getattr(test.left, "id", None)
                    if left == "__name__":
                        has_main_guard = True

            # Check for argument parsers (argparse, click, sys.argv)
            if isinstance(node, ast.Call):
                func_attr = getattr(node.func, "attr", None)
                func_id = getattr(node.func, "id", None)

                if func_attr == "ArgumentParser" or func_id == "ArgumentParser":
                    args_parser = "argparse"
                elif func_attr in ("command", "group") or func_id in ("command", "group"):
                    args_parser = "click"

                # Check parser.add_argument('--input', ...)
                if func_attr == "add_argument":
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            val_lower = arg.value.lower()
                            if any(k in val_lower for k in ("input", "data", "test", "case")):
                                input_args.append(arg.value)
                            elif any(k in val_lower for k in ("output", "pred", "out")):
                                output_args.append(arg.value)

            # Check function definitions
            if isinstance(node, ast.FunctionDef):
                fname_lower = node.name.lower()
                if any(k in fname_lower for k in ("predict", "forecast", "infer", "run_model")):
                    is_inference = True
                    if not callable_name:
                        callable_name = node.name
                elif any(k in fname_lower for k in ("train", "fit", "optimizer")):
                    is_training = True

            # Check class definitions
            if isinstance(node, ast.ClassDef):
                cname_lower = node.name.lower()
                if any(k in cname_lower for k in ("model", "predictor", "forecaster", "net")):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name.lower() in ("predict", "forward", "__call__"):
                            is_inference = True
                            if not callable_name:
                                callable_name = f"{node.name}.{item.name}"

        # Combine heuristic signals
        path_lower = rel_path.lower()
        if any(k in path_lower for k in ("train", "trainer", "fit")):
            is_training = True
        if any(k in path_lower for k in ("predict", "forecast", "infer")):
            is_inference = True

        if is_training and not is_inference:
            return CandidateEntrypoint(
                file_path=rel_path,
                entrypoint_type="ast_inferred",
                args_parser=args_parser,
                detected_purpose=CommandType.TRAINING,
                confidence=ConfidenceLevel.MEDIUM,
            )

        if is_inference or has_main_guard or input_args or output_args:
            conf = ConfidenceLevel.HIGH if (has_main_guard and (input_args or output_args)) else ConfidenceLevel.MEDIUM
            return CandidateEntrypoint(
                file_path=rel_path,
                entrypoint_type="ast_inferred",
                callable_name=callable_name,
                args_parser=args_parser or ("sys.argv" if has_main_guard else None),
                detected_purpose=CommandType.INFERENCE,
                confidence=conf,
                input_arguments=input_args,
                output_arguments=output_args,
            )

        return None

    def _build_proposed_mapping(self, candidate: CandidateEntrypoint) -> ProposedInterfaceMapping:
        """Formulate execution command mapping for single identified interface."""
        target = candidate.file_path.replace("\\", "/")

        # Case 1: CLI script with explicit input and output arguments
        has_in = bool(candidate.input_arguments)
        has_out = bool(candidate.output_arguments)

        if has_in and has_out:
            in_flag = candidate.input_arguments[0]
            out_flag = candidate.output_arguments[0]
            return ProposedInterfaceMapping(
                interface_type="CLI_FILE_IN_OUT",
                executable_target=target,
                input_mechanism=f"{in_flag} <benchmark_input_path>",
                output_mechanism=f"{out_flag} <predictions_output_path>",
                command_template=f"python {target} {in_flag} {{input_file}} {out_flag} {{output_file}}",
                requires_adapter=False,
                adapter_notes="Native support for file-in/file-out CLI flags."
            )

        # Case 2: Standard CLI script with standard main guard
        if candidate.args_parser in ("argparse", "click", "sys.argv") or candidate.entrypoint_type == "documented_command":
            return ProposedInterfaceMapping(
                interface_type="CLI_INFERRED",
                executable_target=target,
                input_mechanism="--input <benchmark_input_path>",
                output_mechanism="--output <predictions_output_path>",
                command_template=f"python {target} --input {{input_file}} --output {{output_file}}",
                requires_adapter=False,
                adapter_notes="Standard CLI entrypoint. Supports standard --input and --output arguments."
            )

        # Case 3: In-memory callable or module function
        if candidate.callable_name:
            return ProposedInterfaceMapping(
                interface_type="PYTHON_ADAPTER",
                executable_target=target,
                input_mechanism="In-memory BenchmarkInputRecord dictionary",
                output_mechanism="In-memory PredictionRecord collection",
                command_template=f"python -m hydraforge_shim --target {target}:{candidate.callable_name} --input {{input_file}} --output {{output_file}}",
                requires_adapter=True,
                adapter_notes=f"Exposes function/class '{candidate.callable_name}'. Wrap with lightweight CLI shim at runtime."
            )

        return ProposedInterfaceMapping(
            interface_type="MANUAL_REVIEW_REQUIRED",
            executable_target=target,
            input_mechanism="Unknown",
            output_mechanism="Unknown",
            requires_adapter=True,
            adapter_notes="Entrypoint structure requires manual organizer verification."
        )
