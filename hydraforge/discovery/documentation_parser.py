"""
hydraforge/discovery/documentation_parser.py
Documentation and README parser for extracting documented CLI commands,
differentiating training vs. inference commands, detecting arguments,
and flagging malicious instructions without executing any commands.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hydraforge.discovery.discovery_models import (
    CommandType,
    ConfidenceLevel,
    DiscoveredCommand,
)

MALICIOUS_PATTERNS = [
    (re.compile(r"\brm\s+-[rf]{1,2}\s+[/~]", re.IGNORECASE), "Destructive filesystem deletion (rm -rf /)"),
    (re.compile(r"curl\s+.*\|\s*(bash|sh)", re.IGNORECASE), "Untrusted pipe to shell (curl | bash)"),
    (re.compile(r"wget\s+.*\|\s*(bash|sh)", re.IGNORECASE), "Untrusted pipe to shell (wget | sh)"),
    (re.compile(r"\bnc\s+.*-e\s+", re.IGNORECASE), "Reverse shell network execution (nc -e)"),
    (re.compile(r"\bsudo\s+", re.IGNORECASE), "Privilege escalation attempt (sudo)"),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", re.IGNORECASE), "Fork bomb attack"),
    (re.compile(r"\bchmod\s+777\s+[/~]", re.IGNORECASE), "Unsafe global permission modification"),
]

TRAINING_KEYWORDS = {"train", "training", "fit", "fitting", "epochs", "batch_size", "loss", "trainer", "optimizer"}
INFERENCE_KEYWORDS = {"predict", "prediction", "infer", "inference", "forecast", "forecasting", "predict.py", "inference.py", "eval"}
TEST_KEYWORDS = {"pytest", "unittest", "test", "tests"}
INSTALL_KEYWORDS = {"pip install", "conda install", "git clone", "docker build", "poetry install"}


class DocumentationParser:
    """Parses README files and documentation safely without execution."""

    def parse_repository_docs(
        self,
        repo_root: Path
    ) -> Tuple[Dict[str, Any], List[DiscoveredCommand], List[str]]:
        """
        Scan repository documentation for commands and usage instructions.
        Returns:
            (doc_findings_dict, discovered_commands, warnings)
        """
        repo_root = Path(repo_root).resolve()
        findings: Dict[str, Any] = {
            "readme_files_found": [],
            "has_quickstart": False,
            "has_usage_section": False,
        }
        commands: List[DiscoveredCommand] = []
        warnings: List[str] = []

        candidate_docs = []
        for p in repo_root.glob("README*"):
            if p.is_file():
                candidate_docs.append(p)
        for p in (repo_root / "docs").glob("*.md"):
            if p.is_file():
                candidate_docs.append(p)

        for doc_path in candidate_docs:
            rel_doc = doc_path.relative_to(repo_root).as_posix()
            findings["readme_files_found"].append(rel_doc)

            try:
                with open(doc_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception as e:
                warnings.append(f"Failed to read documentation '{rel_doc}': {e}")
                continue

            doc_cmds, doc_warnings = self.extract_commands_from_text(content, rel_doc)
            commands.extend(doc_cmds)
            warnings.extend(doc_warnings)

            # Check structural cues
            content_lower = content.lower()
            if "quickstart" in content_lower or "getting started" in content_lower:
                findings["has_quickstart"] = True
            if "usage" in content_lower or "how to run" in content_lower:
                findings["has_usage_section"] = True

        return findings, commands, warnings

    def extract_commands_from_text(
        self, text: str, source_file: str
    ) -> Tuple[List[DiscoveredCommand], List[str]]:
        """Extract shell commands from markdown code fences or command lines."""
        discovered: List[DiscoveredCommand] = []
        warnings: List[str] = []

        # 1. Extract markdown fenced code blocks: ```bash ... ```, ```sh ... ```, etc.
        fence_pattern = re.compile(r"```(?:bash|sh|shell|console|python)?\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
        blocks = fence_pattern.findall(text)

        raw_candidates: List[str] = []
        for block in blocks:
            for line in block.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Strip leading prompt markers like '$ ', '> '
                cleaned = re.sub(r"^[\$>]+\s*", "", line).strip()
                if cleaned:
                    raw_candidates.append(cleaned)

        # 2. Also look for lines starting with "$ python" or "python" in prose
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("$ python") or line.startswith("$ ./") or line.startswith("$ bash"):
                cleaned = re.sub(r"^[\$>]+\s*", "", line).strip()
                if cleaned not in raw_candidates:
                    raw_candidates.append(cleaned)

        for cmd in raw_candidates:
            # Check security patterns first
            is_malicious = False
            security_note = None
            for pat, desc in MALICIOUS_PATTERNS:
                if pat.search(cmd):
                    is_malicious = True
                    security_note = f"Malicious command pattern detected in {source_file}: {desc}"
                    warnings.append(security_note)
                    break

            cmd_type, target_script, in_flags, out_flags, confidence = self._classify_command_string(cmd)

            discovered.append(DiscoveredCommand(
                raw_command=cmd,
                command_type=cmd_type,
                source_file=source_file,
                executable_script=target_script,
                input_flags=in_flags,
                output_flags=out_flags,
                confidence=confidence,
                notes=f"Found in {source_file}",
                is_malicious=is_malicious,
                security_warning=security_note,
            ))

        return discovered, warnings

    def _classify_command_string(
        self, cmd: str
    ) -> Tuple[CommandType, Optional[str], List[str], List[str], ConfidenceLevel]:
        """Classify command type, target script, and input/output argument flags."""
        cmd_lower = cmd.lower()

        # Check install commands
        if any(cmd_lower.startswith(k) for k in INSTALL_KEYWORDS):
            return CommandType.BUILD_OR_INSTALL, None, [], [], ConfidenceLevel.HIGH

        # Check test commands
        if any(k in cmd_lower for k in TEST_KEYWORDS) and "python" not in cmd_lower:
            return CommandType.TEST, None, [], [], ConfidenceLevel.HIGH

        # Extract target script from python commands: "python <script.py> ..." or "python -m <module> ..."
        target_script = None
        tokens = cmd.split()
        for idx, token in enumerate(tokens):
            if token in ("python", "python3") and idx + 1 < len(tokens):
                next_tok = tokens[idx + 1]
                if next_tok == "-m" and idx + 2 < len(tokens):
                    target_script = tokens[idx + 2]
                elif not next_tok.startswith("-"):
                    target_script = next_tok
                break
            elif token.endswith(".py") or token.startswith("./"):
                target_script = token
                break

        # Extract input/output argument flags
        in_flags = []
        out_flags = []
        for idx, token in enumerate(tokens):
            t_lower = token.lower()
            if any(t_lower == f or t_lower.startswith(f"{f}=") for f in ("--input", "--in", "-i", "--data", "--test-file", "--cases")):
                in_flags.append(token)
            if any(t_lower == f or t_lower.startswith(f"{f}=") for f in ("--output", "--out", "-o", "--predictions", "--pred")):
                out_flags.append(token)

        # Distinguish inference vs. training vs. evaluation
        has_train_words = any(w in cmd_lower for w in TRAINING_KEYWORDS)
        has_infer_words = any(w in cmd_lower for w in INFERENCE_KEYWORDS) or len(in_flags) > 0 or len(out_flags) > 0

        if has_infer_words and not has_train_words:
            conf = ConfidenceLevel.HIGH if (in_flags or out_flags) else ConfidenceLevel.MEDIUM
            return CommandType.INFERENCE, target_script, in_flags, out_flags, conf

        if has_train_words and not has_infer_words:
            return CommandType.TRAINING, target_script, in_flags, out_flags, ConfidenceLevel.HIGH

        if has_train_words and has_infer_words:
            # Command contains both (e.g. train_and_eval.py)
            return CommandType.EVALUATION, target_script, in_flags, out_flags, ConfidenceLevel.MEDIUM

        if target_script:
            return CommandType.UNKNOWN, target_script, in_flags, out_flags, ConfidenceLevel.LOW

        return CommandType.UNKNOWN, None, in_flags, out_flags, ConfidenceLevel.LOW

