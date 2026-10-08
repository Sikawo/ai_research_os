#!/usr/bin/env python3
"""Validate the route-neutral Industry Resume AI/ATS analysis sidecar.

This validator uses only the Python standard library.  It checks the bundled
JSON Schema, then enforces cross-record evidence, provenance, mode-boundary,
gate-propagation, and privacy invariants that JSON Schema cannot express.
It validates the deterministic sidecar contract and does not execute an LLM
or claim that a model-generation pipeline ran.

One JSON result object is written to stdout and a concise summary to stderr.
Exit status is 0 for a valid analysis, 1 for failed invariants, and 2 for
invocation or unreadable/malformed-input errors.
"""

from __future__ import annotations

import argparse
from collections import Counter
import difflib
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator

try:  # Support both package import and direct script execution.
    from .validate_gatedsprint_state import _load_json, _schema_errors
except ImportError:  # pragma: no cover - exercised by CLI subprocess tests.
    from validate_gatedsprint_state import _load_json, _schema_errors


GATE_CONFIG = {
    "GATE_0": "jd_decomposition",
    "GATE_1": "eligibility",
    "GATE_2": "evidence_mapping",
    "GATE_3": "semantic_alignment",
    "GATE_4": "ats_parse",
    "GATE_5": "ai_recruiter",
    "GATE_6": "recruiter_scan",
    "GATE_7": "hiring_manager",
    "GATE_8": "integrity",
}
GATE_DISPLAY_NAMES = {
    "GATE_0": "JD decomposition",
    "GATE_1": "Eligibility",
    "GATE_2": "Evidence mapping",
    "GATE_3": "Semantic alignment",
    "GATE_4": "ATS parse",
    "GATE_5": "AI recruiter",
    "GATE_6": "Recruiter scan",
    "GATE_7": "Hiring manager",
    "GATE_8": "Integrity",
}
GATE_AUDIT_LABEL_PATTERNS = {
    "GATE_0": re.compile(r"(?i)\bJD\s+decomposition\b"),
    "GATE_1": re.compile(r"(?i)\beligibility\b"),
    "GATE_2": re.compile(r"(?i)\bevidence\s+mapping\b"),
    "GATE_3": re.compile(r"(?i)\b(?:semantic|terminology)\s+alignment\b"),
    "GATE_4": re.compile(r"(?i)\bATS\s+(?:parse|extraction)\b"),
    "GATE_5": re.compile(r"(?i)\b(?:AI\s+recruiter|qualification\s+evidence)\b"),
    "GATE_6": re.compile(r"(?i)\b(?:recruiter(?:/top-third)?\s+scan|top-third\s+scan)\b"),
    "GATE_7": re.compile(r"(?i)\bhiring[-\s]+manager(?:\s+review)?\b"),
    "GATE_8": re.compile(r"(?i)\bintegrity\b"),
}

ROLE_DIMENSIONS = (
    "depth",
    "specificity",
    "mechanistic_thinking",
    "ownership",
    "development",
    "rigor",
    "innovation",
    "translation",
    "collaboration",
    "independence",
    "leadership",
    "output_relevance",
    "claim_credibility",
)
SCIENTIFIC_ONLY_DIMENSIONS = {
    "depth",
    "mechanistic_thinking",
    "development",
    "rigor",
    "innovation",
    "translation",
    "output_relevance",
}
ROLE_RELEVANT_DIMENSIONS = set(ROLE_DIMENSIONS) - SCIENTIFIC_ONLY_DIMENSIONS

EVIDENCE_SOURCE_TYPE_BY_SOURCE = {
    "BASELINE_RESUME": "resume",
    "CURRENT_RESUME": "resume",
    "CV": "cv",
    "CANDIDATE_PROFILE": "candidate_profile",
    "PUBLICATION": "publication",
    "PROJECT_FILE": "project_file",
    "USER_VERIFIED_FACTS": "user_verified_fact",
    "OTHER": "other",
}

SPLIT_AUDIT_OUTPUT_TYPES = {
    "JD_ANALYSIS",
    "REQUIREMENT_EVIDENCE_MATRIX",
    "AI_RECRUITER_AUDIT",
    "ATS_PARSE_AUDIT",
    "HUMAN_RECRUITER_AUDIT",
    "HIRING_MANAGER_AUDIT",
    "INTEGRITY_AUDIT",
    "FINAL_GAP_REPORT",
    "REQUIREMENTS_JSON",
    "EVIDENCE_MATRIX_JSON",
    "AUDIT_SUMMARY_JSON",
}

AI_AUDIT_OUTPUT_TYPES = SPLIT_AUDIT_OUTPUT_TYPES | {
    "MARKDOWN_AUDIT_PACKAGE",
    "DASHBOARD",
}
OUTPUT_FORMATS_BY_ARTIFACT = {
    "MARKDOWN_AUDIT_PACKAGE": {"MD"},
    "DASHBOARD": {"MD"},
    "REQUIREMENTS_JSON": {"JSON"},
    "EVIDENCE_MATRIX_JSON": {"JSON"},
    "AUDIT_SUMMARY_JSON": {"JSON"},
}
FORBIDDEN_SCORE_KEYS = {
    "match_score",
    "overall_match_score",
    "match_percentage",
    "opaque_match_percentage",
    "workday_score",
    "hiredscore_score",
    "ranking_score",
}
PROPRIETARY_SCORE_PHRASES = (
    "exact workday score",
    "hiredscore replica",
    "workday ranking predictor",
)
FILE_URI_RE = re.compile(r"(?i)(?<![A-Za-z0-9+])file:(?:/{1,3}|[A-Za-z]:[\\/]|\\\\)")
WINDOWS_DRIVE_RE = re.compile(r"(?i)(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
UNC_PATH_RE = re.compile(r"\\\\[^\\/\s:*?\"<>|]+[\\/][^\\/\s:*?\"<>|]+")
WINDOWS_ROOT_RE = re.compile(r"\\(?=[^\\/\r\n]+(?:[\\/]|$))")
TILDE_PATH_RE = re.compile(r"~(?:[A-Za-z_][A-Za-z0-9._-]*)?[\\/]")
EMBEDDED_POSIX_PATH_RE = re.compile(r":/(?!/)")
AUDIT_SECTION_PATTERNS = {
    "job-description analysis": re.compile(
        r"(?im)^#{1,6}\s+.*(?:\bJD\b|Job\s+Description).*$"
    ),
    "requirement-to-evidence matrix": re.compile(
        r"(?im)^#{1,6}\s+.*Requirement(?:\s*[-\u2013\u2014\u2192]\s*|\s+To\s+|\s*-\s*To\s*-\s*|\s+)Evidence.*$"
    ),
    "gate results": re.compile(
        r"(?im)^#{1,6}\s+.*(?:Decision\s+Dashboard|Audit\s+Results|Gate\s+Results|Gates?\s+0\s*[-\u2013\u2014]\s*8|Exact[-\s]+Candidate\s+Audits).*$"
    ),
}
@dataclass(frozen=True)
class Issue:
    check_id: str
    severity: str
    affected_requirement: str | None
    explanation: str


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _walk(value: Any, path: str = "$") -> Iterator[tuple[str, str | None, Any]]:
    stack: list[tuple[str, str | None, Any]] = []
    if isinstance(value, dict):
        stack.extend(
            (f"{path}.{key}", key, item)
            for key, item in reversed(list(value.items()))
        )
    elif isinstance(value, list):
        stack.extend(
            (f"{path}[{index}]", None, item)
            for index, item in reversed(list(enumerate(value)))
        )
    while stack:
        current_path, key, item = stack.pop()
        yield current_path, key, item
        if isinstance(item, dict):
            stack.extend(
                (f"{current_path}.{child_key}", child_key, child_value)
                for child_key, child_value in reversed(list(item.items()))
            )
        elif isinstance(item, list):
            stack.extend(
                (f"{current_path}[{index}]", None, child_value)
                for index, child_value in reversed(list(enumerate(item)))
            )


def _status_from_rating(rating: Any) -> str:
    return {
        "STRONG": "PASS",
        "ACCEPTABLE": "PASS_WITH_WARNINGS",
        "WEAK": "FAIL",
    }.get(rating, "FAIL")


def _worst_status(*statuses: Any) -> str:
    rank = {"PASS": 0, "PASS_WITH_WARNINGS": 1, "FAIL": 2, "NOT_RUN": -1}
    valid = [value for value in statuses if value in rank]
    return max(valid, key=lambda value: rank[value]) if valid else "FAIL"


def _is_safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or FILE_URI_RE.search(value):
        return False
    pure = PurePosixPath(value)
    return not pure.is_absolute() and ".." not in pure.parts and pure.as_posix() == value


def _contains_local_path(value: str) -> bool:
    known_posix_roots = {
        "Applications",
        "Library",
        "System",
        "Users",
        "Volumes",
        "Windows",
        "bin",
        "boot",
        "dev",
        "data",
        "etc",
        "home",
        "lib",
        "lib64",
        "mnt",
        "nfs",
        "opt",
        "private",
        "Program Files",
        "ProgramData",
        "proc",
        "root",
        "run",
        "scratch",
        "sbin",
        "srv",
        "sys",
        "tmp",
        "usr",
        "var",
        "workspace",
        "workspaces",
    }

    def posix_tail_is_pathlike(index: int) -> bool:
        match = re.match(r"/([^\s`'\"<>{}\[\](),;|]+)", value[index:])
        if match is None:
            return False
        parts = [part for part in match.group(1).split("/") if part]
        return bool(parts) and parts[0].casefold() in {
            root.casefold() for root in known_posix_roots
        }

    def windows_tail_is_pathlike(index: int) -> bool:
        match = re.match(r"\\([^\\/\r\n]+)(?:[\\/]|$)", value[index:])
        return match is not None and match.group(1).strip().casefold() in {
            root.casefold() for root in known_posix_roots
        }

    def prefix_declares_path(index: int) -> bool:
        prefix = value[:index]
        if "📁" in prefix[-4:]:
            return True
        return re.search(
            r"(?i)(?:path|source|file|folder|directory|dir|location|root|mount|label)\s*[._\-)\]}>=\u2013\u2014:]*$",
            prefix,
        ) is not None

    def is_latex_control(index: int) -> bool:
        match = re.match(r"\\([A-Za-z]+)", value[index:])
        if match is None:
            return False
        prefix = value[:index]
        if re.search(r"(?i)\b(?:latex|tex|formula|equation|command)\s*$", prefix):
            return True
        return match.group(1).casefold() in {
            "alpha",
            "approx",
            "array",
            "bar",
            "begin",
            "beta",
            "cases",
            "cdot",
            "chi",
            "cos",
            "delta",
            "epsilon",
            "end",
            "eq",
            "eta",
            "exp",
            "frac",
            "gamma",
            "ge",
            "geq",
            "gt",
            "hat",
            "infty",
            "int",
            "kappa",
            "lambda",
            "le",
            "left",
            "leftarrow",
            "leftrightarrow",
            "leq",
            "log",
            "lt",
            "max",
            "matrix",
            "mathrm",
            "min",
            "mu",
            "nu",
            "nabla",
            "neq",
            "omega",
            "oint",
            "overline",
            "partial",
            "phi",
            "pi",
            "pm",
            "prod",
            "psi",
            "rho",
            "right",
            "rightarrow",
            "sigma",
            "sim",
            "sin",
            "sqrt",
            "sum",
            "tau",
            "text",
            "textbf",
            "textit",
            "theta",
            "times",
            "to",
            "upsilon",
            "vec",
            "xi",
            "zeta",
        }

    def boundary_kind(index: int) -> str:
        if index == 0:
            return "strong"
        previous = value[index - 1]
        if previous.isspace() or previous in "=,:;":
            return "strong"
        category = unicodedata.category(previous)
        if category in {"Ps", "Pi"}:
            return "strong"
        if category[:1] in {"L", "N", "M"} or previous in "_./+":
            return "attached"
        before_previous = value[index - 2] if index >= 2 else None
        if category.startswith("S") or "ARROW" in unicodedata.name(previous, ""):
            return "symbolic"
        if (
            before_previous is None
            or before_previous.isspace()
            or before_previous in "=,:;"
            or unicodedata.category(before_previous) in {"Ps", "Pi"}
        ):
            return "strong"
        return "ambiguous"

    if any(pattern.search(value) for pattern in (WINDOWS_DRIVE_RE, UNC_PATH_RE)):
        return True
    for match in TILDE_PATH_RE.finditer(value):
        if boundary_kind(match.start()) != "attached" or prefix_declares_path(
            match.start()
        ):
            return True
    for pattern in (WINDOWS_ROOT_RE,):
        for match in pattern.finditer(value):
            index = match.start()
            previous = value[index - 1] if index else None
            following = value[index + 1] if index + 1 < len(value) else None
            if previous == "\\" or following == "\\":
                continue
            if prefix_declares_path(index) or windows_tail_is_pathlike(index):
                return True
            if is_latex_control(index):
                continue
            if boundary_kind(index) != "attached":
                return True
    for match in re.finditer(r"\\", value):
        index = match.start()
        previous = value[index - 1] if index else None
        following = value[index + 1] if index + 1 < len(value) else None
        if previous == "\\" or following == "\\":
            continue
        if windows_tail_is_pathlike(index) or prefix_declares_path(index):
            return True
        if boundary_kind(index) == "strong" and not is_latex_control(index):
            return True
    for match in re.finditer(r"//", value):
        prefix = value[: match.start()]
        if prefix.endswith(":") and re.search(r"[A-Za-z][A-Za-z0-9+.-]*:$", prefix):
            continue
        if boundary_kind(match.start()) != "attached":
            return True
    for index, character in enumerate(value):
        if character != "/":
            continue
        previous = value[index - 1] if index else None
        following = value[index + 1] if index + 1 < len(value) else None
        if previous == "/" or following == "/":
            continue
        boundary = boundary_kind(index)
        if boundary == "attached":
            continue
        if following is None:
            if boundary == "strong":
                return True
            continue
        if following.isspace() or following in "([{":
            continue
        if boundary == "strong":
            return True
        if boundary in {"ambiguous", "symbolic"} and (
            posix_tail_is_pathlike(index) or prefix_declares_path(index)
        ):
            return True
    return False


def _source_paths(source: dict[str, Any]) -> set[str]:
    return {
        value
        for field in ("relative_path", "extracted_text_relative_path")
        if isinstance((value := source.get(field)), str) and value
    }


def _source_hashes(source: dict[str, Any]) -> set[str]:
    return {
        value
        for field in ("sha256", "extracted_text_sha256")
        if isinstance((value := source.get(field)), str) and value
    }


def _sources_alias(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return bool(
        _source_paths(left) & _source_paths(right)
        or _source_hashes(left) & _source_hashes(right)
    )


def _markdown_section(text: str, heading_pattern: re.Pattern[str]) -> str | None:
    match = heading_pattern.search(text)
    if match is None:
        return None
    heading = match.group(0)
    level = len(heading) - len(heading.lstrip("#"))
    tail = text[match.end() :]
    next_heading = re.search(rf"(?m)^#{{1,{level}}}\s+", tail)
    section = tail[: next_heading.start()] if next_heading is not None else tail
    return section.strip()


def _has_contract_token(text: str, token: str, boundary_chars: str) -> bool:
    return (
        re.search(
            rf"(?<![{boundary_chars}]){re.escape(token)}(?![{boundary_chars}])",
            text,
        )
        is not None
    )


class IndustryResumeValidator:
    def __init__(self, analysis: dict[str, Any], schema: dict[str, Any]) -> None:
        self.analysis = analysis
        self.schema = schema
        self.issues: list[Issue] = []
        self.sources: dict[str, dict[str, Any]] = {}
        self.facts: dict[str, dict[str, Any]] = {}
        self.requirements: dict[str, dict[str, Any]] = {}
        self.evidence: dict[str, dict[str, Any]] = {}
        self.eligibility: dict[str, dict[str, Any]] = {}
        self.qualifications: dict[str, dict[str, Any]] = {}
        self.gaps: dict[str, dict[str, Any]] = {}
        self.gates: dict[str, dict[str, Any]] = {}
        self.evaluator_runs: dict[str, dict[str, Any]] = {}
        self.claims: dict[str, dict[str, Any]] = {}
        self.outputs: dict[str, dict[str, Any]] = {}

    def issue(
        self,
        check_id: str,
        explanation: str,
        *,
        requirement: str | None = None,
        severity: str = "ERROR",
    ) -> None:
        self.issues.append(Issue(check_id, severity, requirement, explanation))

    def _index(
        self,
        field: str,
        key: str,
        target: dict[str, dict[str, Any]],
        check_id: str,
    ) -> None:
        for item in _records(self.analysis.get(field)):
            identifier = item.get(key)
            if not isinstance(identifier, str) or not identifier:
                continue
            if identifier in target:
                self.issue(check_id, f"duplicate {field} identifier {identifier!r}")
            else:
                target[identifier] = item

    def run(self) -> list[Issue]:
        schema_errors = _schema_errors(self.analysis, self.schema, self.schema)
        for message in schema_errors[:100]:
            self.issue("INDUSTRY_RESUME.SCHEMA", message)
        if len(schema_errors) > 100:
            self.issue(
                "INDUSTRY_RESUME.SCHEMA",
                f"{len(schema_errors) - 100} additional schema errors omitted",
            )

        self._index("sources", "source_id", self.sources, "INDUSTRY_RESUME.ID_UNIQUE")
        self._index("candidate_facts", "fact_id", self.facts, "INDUSTRY_RESUME.ID_UNIQUE")
        self._index("requirements", "id", self.requirements, "INDUSTRY_RESUME.ID_UNIQUE")
        self._index("evidence_items", "id", self.evidence, "INDUSTRY_RESUME.ID_UNIQUE")
        self._index("eligibility_results", "requirement_id", self.eligibility, "INDUSTRY_RESUME.RESULT_UNIQUE")
        self._index("qualification_results", "requirement_id", self.qualifications, "INDUSTRY_RESUME.RESULT_UNIQUE")
        self._index("gaps", "gap_id", self.gaps, "INDUSTRY_RESUME.ID_UNIQUE")
        self._index("gate_results", "gate_id", self.gates, "INDUSTRY_RESUME.RESULT_UNIQUE")
        self._index(
            "evaluator_runs",
            "evaluator_run_id",
            self.evaluator_runs,
            "INDUSTRY_RESUME.ID_UNIQUE",
        )
        self._index("claim_provenance", "resume_claim_id", self.claims, "INDUSTRY_RESUME.ID_UNIQUE")
        self._index("outputs", "artifact_type", self.outputs, "INDUSTRY_RESUME.OUTPUT_UNIQUE")

        self._validate_privacy_and_scoring()
        # Cross-record checks assume schema-shaped collections. Fail closed on
        # schema errors so malformed model output can never crash the CLI.
        if schema_errors:
            return self.issues
        self._validate_mode_boundaries()
        self._validate_configuration()
        self._validate_sources()

        config = self.analysis.get("config")
        if not isinstance(config, dict):
            return self.issues
        if not config.get("ai_ats_mode"):
            self._validate_disabled_mode()
            return self.issues

        self._validate_target()
        self._validate_references()
        self._validate_requirement_structure()
        self._validate_evidence()
        self._validate_eligibility_and_gaps()
        self._validate_semantic_alignment()
        self._validate_qualifications()
        self._validate_claim_provenance()
        self._validate_audits()
        self._validate_evaluator_runs()
        self._validate_gates_and_status()
        self._validate_metrics()
        self._validate_outputs()
        return self.issues

    def _validate_privacy_and_scoring(self) -> None:
        for path, key, value in _walk(self.analysis):
            normalized_key = key.casefold() if isinstance(key, str) else None
            if normalized_key in FORBIDDEN_SCORE_KEYS:
                self.issue(
                    "INDUSTRY_RESUME.OPAQUE_SCORE",
                    f"opaque or proprietary score field is forbidden at {path}",
                )
            if normalized_key == "overall_match_percentage" and value is not None:
                self.issue(
                    "INDUSTRY_RESUME.OPAQUE_SCORE",
                    "overall_match_percentage must remain null; report qualification coverage counts instead",
                )
            if isinstance(value, str):
                lowered = value.casefold()
                if (
                    FILE_URI_RE.search(value)
                    or _contains_local_path(value)
                    or EMBEDDED_POSIX_PATH_RE.search(value)
                ):
                    self.issue(
                        "INDUSTRY_RESUME.PRIVACY",
                        f"local absolute path or file URL is forbidden at {path}",
                    )
                if any(phrase in lowered for phrase in PROPRIETARY_SCORE_PHRASES):
                    self.issue(
                        "INDUSTRY_RESUME.PROPRIETARY_CLAIM",
                        f"proprietary scoring equivalence claim is forbidden at {path}",
                    )

        logging = self.analysis.get("logging")
        if isinstance(logging, dict) and any(
            logging.get(field) is not expected
            for field, expected in (
                ("summary_only", True),
                ("resume_content_logged", False),
                ("candidate_evidence_logged", False),
                ("local_paths_logged", False),
            )
        ):
            self.issue(
                "INDUSTRY_RESUME.PRIVACY",
                "logging must remain summary-only and exclude resume content, candidate evidence, and local paths",
            )

    def _validate_mode_boundaries(self) -> None:
        run = self.analysis.get("run")
        config = self.analysis.get("config")
        if not isinstance(run, dict) or not isinstance(config, dict):
            return
        policy = run.get("execution_policy")
        operation = run.get("operation")
        if policy == "SPRINT_SELF_DRIVING":
            if operation != "SELF_DRIVING":
                self.issue(
                    "INDUSTRY_RESUME.MODE_BOUNDARY",
                    "self-driving Sprint must use operation SELF_DRIVING",
                )
            if run.get("approval_ledger_created"):
                self.issue(
                    "INDUSTRY_RESUME.MODE_BOUNDARY",
                    "self-driving Sprint must not create a GatedSprint approval ledger",
                )
        elif policy == "GATEDSPRINT":
            if operation == "SELF_DRIVING":
                self.issue(
                    "INDUSTRY_RESUME.MODE_BOUNDARY",
                    "GatedSprint cannot use the self-driving operation",
                )
            if not run.get("approval_ledger_created"):
                self.issue(
                    "INDUSTRY_RESUME.MODE_BOUNDARY",
                    "GatedSprint requires its approval ledger",
                )
            if operation in {"DIAGNOSE", "NEGOTIATE", "RECEIPT"}:
                if run.get("revisions_applied"):
                    self.issue(
                        "INDUSTRY_RESUME.MODE_BOUNDARY",
                        f"GatedSprint {operation} is no-edit and cannot apply resume revisions",
                    )
                final_output = self.outputs.get("FINAL_RESUME")
                if final_output and final_output.get("status") == "CREATED":
                    self.issue(
                        "INDUSTRY_RESUME.MODE_BOUNDARY",
                        f"GatedSprint {operation} cannot create a clean final resume",
                    )
            if run.get("revisions_applied") and not run.get("authorization_verified"):
                self.issue(
                    "INDUSTRY_RESUME.MODE_BOUNDARY",
                    "GatedSprint revisions require verified implementation authorization",
                )

        cycle = run.get("revision_cycle")
        limit = config.get("max_revision_cycles")
        if isinstance(cycle, int) and isinstance(limit, int) and cycle > limit:
            self.issue(
                "INDUSTRY_RESUME.REVISION_LIMIT",
                f"revision cycle {cycle} exceeds configured maximum {limit}",
            )

    def _validate_sources(self) -> None:
        run = self.analysis.get("run")
        config = self.analysis.get("config")
        if not isinstance(run, dict) or not isinstance(config, dict):
            return
        for source_id, source in self.sources.items():
            if not _is_safe_relative_path(source.get("relative_path")):
                self.issue(
                    "INDUSTRY_RESUME.SOURCE_PATH",
                    f"source {source_id!r} must use a normalized safe relative path",
                )
            extracted_path = source.get("extracted_text_relative_path")
            if extracted_path is not None and not _is_safe_relative_path(extracted_path):
                self.issue(
                    "INDUSTRY_RESUME.SOURCE_PATH",
                    f"source {source_id!r} extracted text must use a normalized safe relative path",
                )
        job_description_paths = set().union(
            *(
                _source_paths(source)
                for source in self.sources.values()
                if source.get("source_type") == "JOB_DESCRIPTION"
            )
        )
        job_description_hashes = set().union(
            *(
                _source_hashes(source)
                for source in self.sources.values()
                if source.get("source_type") == "JOB_DESCRIPTION"
            )
        )
        for source_id, source in self.sources.items():
            if (
                source.get("source_type") != "JOB_DESCRIPTION"
                and source.get("candidate_evidence_allowed") is True
                and (
                    _source_paths(source) & job_description_paths
                    or _source_hashes(source) & job_description_hashes
                )
            ):
                self.issue(
                    "INDUSTRY_RESUME.SOURCE_ALIAS",
                    f"candidate-evidence source {source_id!r} cannot alias job-description bytes or path",
                )
        current_id = run.get("current_resume_source_id")
        current_hash = run.get("current_resume_hash")
        if not config.get("ai_ats_mode"):
            return
        current = self.sources.get(current_id) if isinstance(current_id, str) else None
        if current is None:
            self.issue(
                "INDUSTRY_RESUME.CURRENT_RESUME",
                "AI/ATS mode requires a registered current resume source",
            )
        elif (
            current.get("source_type") != "CURRENT_RESUME"
            or not current.get("is_current")
            or not current.get("content_authority")
            or current.get("sha256") != current_hash
        ):
            self.issue(
                "INDUSTRY_RESUME.CURRENT_RESUME",
                "current resume ID/hash must bind a current authoritative CURRENT_RESUME source",
            )
        else:
            for source_id, source in self.sources.items():
                if source_id == current_id or source.get("candidate_evidence_allowed") is not True:
                    continue
                shared_path = bool(_source_paths(source) & _source_paths(current))
                shared_hash = bool(_source_hashes(source) & _source_hashes(current))
                baseline_exception = source.get("source_type") == "BASELINE_RESUME"
                if shared_path or (
                    shared_hash
                    and not (
                        baseline_exception and run.get("revisions_applied") is False
                    )
                ):
                    self.issue(
                        "INDUSTRY_RESUME.SOURCE_ALIAS",
                        f"candidate-evidence source {source_id!r} cannot alias generated-current-resume bytes or path",
                    )
        baseline_ids = [
            source_id
            for source_id, source in self.sources.items()
            if source.get("source_type") == "BASELINE_RESUME"
            and source.get("content_authority") is True
        ]
        if run.get("revisions_applied") is True:
            if len(baseline_ids) != 1:
                self.issue(
                    "INDUSTRY_RESUME.REVISION_PROVENANCE",
                    "a revised resume requires exactly one authoritative BASELINE_RESUME source for deterministic claim coverage",
                )
        elif run.get("operation") in {"RELEASE", "SELF_DRIVING"}:
            if len(baseline_ids) != 1:
                self.issue(
                    "INDUSTRY_RESUME.REVISION_PROVENANCE",
                    "a final unchanged resume requires exactly one authoritative BASELINE_RESUME source",
                )
            elif self.sources[baseline_ids[0]].get("sha256") != current_hash:
                self.issue(
                    "INDUSTRY_RESUME.REVISION_PROVENANCE",
                    "revisions_applied=false requires final current-resume bytes to equal the authoritative baseline",
                )
        visible = [
            source_id
            for source_id, source in self.sources.items()
            if source.get("visible_to_ai_recruiter")
        ]
        if visible != [current_id]:
            self.issue(
                "INDUSTRY_RESUME.RECRUITER_SOURCE_BOUNDARY",
                "only the exact current resume may be visible as candidate evidence to the AI recruiter audit",
            )
        if not any(
            source.get("source_type") == "JOB_DESCRIPTION"
            and source.get("content_authority")
            for source in self.sources.values()
        ):
            self.issue(
                "INDUSTRY_RESUME.JD_SOURCE",
                "AI/ATS mode requires an authoritative job-description source",
            )

    def _validate_configuration(self) -> None:
        config = self.analysis.get("config")
        if not isinstance(config, dict):
            return
        for field in ("required_min_level_target", "preferred_min_level_target"):
            value = config.get(field)
            if isinstance(value, int) and not 0 <= value <= 4:
                self.issue(
                    "INDUSTRY_RESUME.EVIDENCE_TARGET",
                    f"{field} must use the bounded evidence scale 0-4",
                )
        if config.get("ai_ats_mode") is True and config.get("save_structured_audits") is not True:
            self.issue(
                "INDUSTRY_RESUME.STRUCTURED_SIDECAR",
                "AI/ATS mode requires save_structured_audits=true because this analysis JSON is the canonical structured sidecar",
            )

    def _validate_disabled_mode(self) -> None:
        run = self.analysis.get("run", {})
        analytical_fields = (
            "candidate_facts",
            "requirements",
            "evidence_items",
            "eligibility_results",
            "semantic_alignments",
            "qualification_results",
            "gaps",
            "gate_results",
            "evaluator_runs",
            "claim_provenance",
            "removed_claims",
        )
        if any(self.analysis.get(field) for field in analytical_fields):
            self.issue(
                "INDUSTRY_RESUME.BACKWARD_COMPATIBILITY",
                "ai_ats_mode=false must not emit Industry Resume analysis records",
            )
        if self.analysis.get("audits") is not None or self.analysis.get("metrics") is not None:
            self.issue(
                "INDUSTRY_RESUME.BACKWARD_COMPATIBILITY",
                "ai_ats_mode=false must leave AI/ATS audits and metrics null",
            )
        if self.analysis.get("target") is not None:
            self.issue(
                "INDUSTRY_RESUME.BACKWARD_COMPATIBILITY",
                "ai_ats_mode=false must leave the Industry Resume target summary null",
            )
        if isinstance(run, dict) and run.get("overall_status") != "NOT_RUN":
            self.issue(
                "INDUSTRY_RESUME.BACKWARD_COMPATIBILITY",
                "ai_ats_mode=false requires overall_status NOT_RUN",
            )
        for artifact_type in AI_AUDIT_OUTPUT_TYPES:
            artifact = self.outputs.get(artifact_type)
            if artifact and artifact.get("status") == "CREATED":
                self.issue(
                    "INDUSTRY_RESUME.BACKWARD_COMPATIBILITY",
                    f"ai_ats_mode=false cannot create {artifact_type}",
                )

    def _validate_target(self) -> None:
        """Validate exact JD binding; textual extraction itself remains evaluator work."""

        target = self.analysis.get("target")
        if not isinstance(target, dict):
            self.issue(
                "INDUSTRY_RESUME.TARGET",
                "AI/ATS mode requires a structured Gate 0 target summary",
            )
            return
        job_source = self.sources.get(target.get("job_description_source_id"))
        if (
            job_source is None
            or job_source.get("source_type") != "JOB_DESCRIPTION"
            or job_source.get("content_authority") is not True
            or job_source.get("is_current") is not True
            or job_source.get("sha256") != target.get("job_description_hash")
        ):
            self.issue(
                "INDUSTRY_RESUME.TARGET_SOURCE",
                "target must bind the exact current authoritative JOB_DESCRIPTION source ID/hash",
            )
        target_source_id = target.get("job_description_source_id")
        target_source_hash = target.get("job_description_hash")
        if not self.requirements:
            self.issue(
                "INDUSTRY_RESUME.JD_DECOMPOSITION",
                "AI/ATS mode requires at least one JobRequirement extracted from the target description",
            )
        elif not any(
            requirement.get("screenable") is True
            for requirement in self.requirements.values()
        ):
            self.issue(
                "INDUSTRY_RESUME.JD_DECOMPOSITION",
                "Gate 0 must identify at least one screenable target requirement",
            )
        for requirement_id, requirement in self.requirements.items():
            if (
                requirement.get("source_id") != target_source_id
                or requirement.get("source_hash") != target_source_hash
                or not isinstance(requirement.get("source_location"), str)
                or not requirement.get("source_location")
            ):
                self.issue(
                    "INDUSTRY_RESUME.REQUIREMENT_SOURCE",
                    "each JobRequirement must bind the exact target JD source ID/hash and a source location",
                    requirement=requirement_id,
                )
        required_ids = {
            requirement_id
            for requirement_id, requirement in self.requirements.items()
            if requirement.get("priority") == "required"
        }
        preferred_ids = {
            requirement_id
            for requirement_id, requirement in self.requirements.items()
            if requirement.get("priority") == "preferred"
        }
        if set(target.get("required_requirement_ids", [])) != required_ids:
            self.issue(
                "INDUSTRY_RESUME.TARGET",
                "target required_requirement_ids must exactly match required JobRequirement records",
            )
        if set(target.get("preferred_requirement_ids", [])) != preferred_ids:
            self.issue(
                "INDUSTRY_RESUME.TARGET",
                "target preferred_requirement_ids must exactly match preferred JobRequirement records",
            )
        for field in ("screen_out_requirement_ids", "differentiator_requirement_ids"):
            unknown = set(target.get(field, [])) - set(self.requirements)
            if unknown:
                self.issue(
                    "INDUSTRY_RESUME.TARGET",
                    f"target {field} references unknown requirements: {', '.join(sorted(unknown))}",
                )

    def _validate_references(self) -> None:
        for fact_id, fact in self.facts.items():
            source = self.sources.get(fact.get("source_id"))
            if source is None:
                self.issue(
                    "INDUSTRY_RESUME.REFERENCE",
                    f"candidate fact {fact_id!r} references an unknown source",
                )
            elif (
                source.get("candidate_evidence_allowed") is not True
                or source.get("content_authority") is not True
                or source.get("source_type") == "JOB_DESCRIPTION"
            ):
                self.issue(
                    "INDUSTRY_RESUME.EVIDENCE_AUTHORITY",
                    f"candidate fact {fact_id!r} must bind authoritative non-JD candidate evidence",
                )
            elif fact.get("source_hash") != source.get("sha256"):
                self.issue(
                    "INDUSTRY_RESUME.PROVENANCE",
                    f"candidate fact {fact_id!r} source hash does not match its bound source",
                )
        for evidence_id, item in self.evidence.items():
            requirement_id = item.get("requirement_id")
            if requirement_id not in self.requirements:
                self.issue(
                    "INDUSTRY_RESUME.REFERENCE",
                    f"evidence item {evidence_id!r} references an unknown requirement",
                    requirement=requirement_id if isinstance(requirement_id, str) else None,
                )
            source_id = item.get("source_id")
            if source_id is not None and source_id not in self.sources:
                self.issue(
                    "INDUSTRY_RESUME.REFERENCE",
                    f"evidence item {evidence_id!r} references an unknown source",
                    requirement=requirement_id if isinstance(requirement_id, str) else None,
                )
            elif source_id is not None:
                source = self.sources[source_id]
                expected_source_type = EVIDENCE_SOURCE_TYPE_BY_SOURCE.get(
                    source.get("source_type")
                )
                if (
                    source.get("candidate_evidence_allowed") is not True
                    or source.get("content_authority") is not True
                ):
                    self.issue(
                        "INDUSTRY_RESUME.EVIDENCE_AUTHORITY",
                        f"evidence item {evidence_id!r} binds a source that is not authoritative candidate evidence",
                        requirement=requirement_id if isinstance(requirement_id, str) else None,
                    )
                if item.get("source_hash") != source.get("sha256"):
                    self.issue(
                        "INDUSTRY_RESUME.PROVENANCE",
                        f"evidence item {evidence_id!r} source hash does not match its bound source",
                        requirement=requirement_id if isinstance(requirement_id, str) else None,
                    )
                if expected_source_type is None or item.get("source_type") != expected_source_type:
                    self.issue(
                        "INDUSTRY_RESUME.EVIDENCE_SOURCE_TYPE",
                        f"evidence item {evidence_id!r} source_type does not match its bound source",
                        requirement=requirement_id if isinstance(requirement_id, str) else None,
                    )
            for fact_id in item.get("candidate_fact_ids", []):
                if fact_id not in self.facts:
                    self.issue(
                        "INDUSTRY_RESUME.REFERENCE",
                        f"evidence item {evidence_id!r} references unknown candidate fact {fact_id!r}",
                        requirement=requirement_id if isinstance(requirement_id, str) else None,
                    )

        for field in ("eligibility_results", "qualification_results", "semantic_alignments", "gaps"):
            for item in _records(self.analysis.get(field)):
                requirement_id = item.get("requirement_id")
                if requirement_id not in self.requirements:
                    self.issue(
                        "INDUSTRY_RESUME.REFERENCE",
                        f"{field} references unknown requirement {requirement_id!r}",
                        requirement=requirement_id if isinstance(requirement_id, str) else None,
                    )
                for evidence_id in item.get("evidence_item_ids", []):
                    if evidence_id not in self.evidence:
                        self.issue(
                            "INDUSTRY_RESUME.REFERENCE",
                            f"{field} references unknown evidence item {evidence_id!r}",
                            requirement=requirement_id if isinstance(requirement_id, str) else None,
                        )
                    elif self.evidence[evidence_id].get("requirement_id") != requirement_id:
                        self.issue(
                            "INDUSTRY_RESUME.EVIDENCE_CROSSLINK",
                            f"{field} requirement {requirement_id!r} cites evidence {evidence_id!r} for a different requirement",
                            requirement=requirement_id if isinstance(requirement_id, str) else None,
                        )

    def _validate_requirement_structure(self) -> None:
        """Preserve explicit parent/facet identity for compound requirements."""

        for requirement_id, requirement in self.requirements.items():
            parent_id = requirement.get("parent_requirement_id")
            facet_ids = requirement.get("facet_ids", [])
            compound = requirement.get("compound") is True
            if compound:
                if parent_id is not None or len(facet_ids) < 2:
                    self.issue(
                        "INDUSTRY_RESUME.REQUIREMENT_STRUCTURE",
                        "a compound parent needs no parent and at least two explicit facets",
                        requirement=requirement_id,
                    )
            elif parent_id is None and facet_ids:
                self.issue(
                    "INDUSTRY_RESUME.REQUIREMENT_STRUCTURE",
                    "an independent non-compound requirement cannot own facets",
                    requirement=requirement_id,
                )
            elif parent_id is not None and facet_ids:
                self.issue(
                    "INDUSTRY_RESUME.REQUIREMENT_STRUCTURE",
                    "a facet cannot itself own nested facets",
                    requirement=requirement_id,
                )

            if parent_id is not None:
                parent = self.requirements.get(parent_id)
                if parent is None:
                    self.issue(
                        "INDUSTRY_RESUME.REFERENCE",
                        f"facet references unknown parent requirement {parent_id!r}",
                        requirement=requirement_id,
                    )
                elif (
                    parent_id == requirement_id
                    or parent.get("compound") is not True
                    or requirement_id not in parent.get("facet_ids", [])
                ):
                    self.issue(
                        "INDUSTRY_RESUME.REQUIREMENT_STRUCTURE",
                        "facet parent must be a distinct compound requirement that lists the facet",
                        requirement=requirement_id,
                    )

            for facet_id in facet_ids:
                facet = self.requirements.get(facet_id)
                if facet is None:
                    self.issue(
                        "INDUSTRY_RESUME.REFERENCE",
                        f"compound requirement references unknown facet {facet_id!r}",
                        requirement=requirement_id,
                    )
                elif facet.get("parent_requirement_id") != requirement_id:
                    self.issue(
                        "INDUSTRY_RESUME.REQUIREMENT_STRUCTURE",
                        "compound parent/facet links must be reciprocal",
                        requirement=requirement_id,
                    )

        for requirement_id in self.requirements:
            seen: set[str] = set()
            current_id: Any = requirement_id
            while isinstance(current_id, str) and current_id in self.requirements:
                if current_id in seen:
                    self.issue(
                        "INDUSTRY_RESUME.REQUIREMENT_STRUCTURE",
                        "requirement parent links contain a cycle",
                        requirement=requirement_id,
                    )
                    break
                seen.add(current_id)
                current_id = self.requirements[current_id].get("parent_requirement_id")

    def _validate_evidence(self) -> None:
        for evidence_id, item in self.evidence.items():
            requirement_id = item.get("requirement_id")
            status = item.get("status")
            level = item.get("evidence_level")
            relationship = item.get("relationship_to_requirement")
            if isinstance(level, int) and not 0 <= level <= 4:
                self.issue(
                    "INDUSTRY_RESUME.EVIDENCE_LEVEL",
                    f"evidence item {evidence_id!r} has level {level}; allowed range is 0-4",
                    requirement=requirement_id,
                )
            if status == "absent":
                if any(
                    (
                        level != 0,
                        relationship != "NONE",
                        item.get("source_type") != "none",
                        item.get("source_id") is not None,
                        item.get("source_hash") is not None,
                        item.get("source_location") is not None,
                        item.get("source_excerpt") is not None,
                        bool(item.get("candidate_fact_ids")),
                        item.get("recommended_action") != "leave_as_gap",
                    )
                ):
                    self.issue(
                        "INDUSTRY_RESUME.EVIDENCE_CONSISTENCY",
                        f"absent evidence item {evidence_id!r} must remain level 0, unbound, and leave_as_gap",
                        requirement=requirement_id,
                    )
            else:
                if relationship == "NONE":
                    self.issue(
                        "INDUSTRY_RESUME.EVIDENCE_CONSISTENCY",
                        f"non-absent evidence item {evidence_id!r} cannot use relationship NONE",
                        requirement=requirement_id,
                    )
                if (
                    item.get("source_id") is None
                    or not item.get("candidate_fact_ids")
                    or not isinstance(item.get("source_location"), str)
                    or not item.get("source_location")
                    or not isinstance(item.get("source_excerpt"), str)
                    or not item.get("source_excerpt")
                ):
                    self.issue(
                        "INDUSTRY_RESUME.PROVENANCE",
                        f"non-absent evidence item {evidence_id!r} needs source, location, excerpt, and candidate-fact provenance",
                        requirement=requirement_id,
                    )
            if status == "strong" and isinstance(level, int) and level < 2:
                self.issue(
                    "INDUSTRY_RESUME.EVIDENCE_CONSISTENCY",
                    f"strong evidence item {evidence_id!r} must be level 2 or higher",
                    requirement=requirement_id,
                )
            if status == "implied" and level != 1:
                self.issue(
                    "INDUSTRY_RESUME.EVIDENCE_CONSISTENCY",
                    f"implied evidence item {evidence_id!r} must be level 1",
                    requirement=requirement_id,
                )
            if relationship == "ADJACENT" and isinstance(level, int) and level > 2:
                self.issue(
                    "INDUSTRY_RESUME.ADJACENT_NOT_DIRECT",
                    f"adjacent evidence item {evidence_id!r} cannot exceed level 2",
                    requirement=requirement_id,
                )
            if relationship == "DIRECT":
                fact_ids = item.get("candidate_fact_ids", [])
                if fact_ids and not any(
                    self.facts.get(fact_id, {}).get("direct_experience") for fact_id in fact_ids
                ):
                    self.issue(
                        "INDUSTRY_RESUME.ADJACENT_NOT_DIRECT",
                        f"evidence item {evidence_id!r} is marked DIRECT but no bound fact supports direct experience",
                        requirement=requirement_id,
                    )

    def _evidence_for(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            self.evidence[evidence_id]
            for evidence_id in item.get("evidence_item_ids", [])
            if evidence_id in self.evidence
        ]

    def _is_authorized_direct_evidence(self, item: dict[str, Any]) -> bool:
        source = self.sources.get(item.get("source_id"), {})
        return (
            item.get("relationship_to_requirement") == "DIRECT"
            and isinstance(item.get("evidence_level"), int)
            and item.get("evidence_level") >= 2
            and source.get("candidate_evidence_allowed") is True
            and source.get("content_authority") is True
            and source.get("source_type") != "JOB_DESCRIPTION"
        )

    def _validate_eligibility_and_gaps(self) -> None:
        requirement_ids = set(self.requirements)
        config = self.analysis.get("config", {})
        gates_config = config.get("gates", {}) if isinstance(config, dict) else {}
        eligibility_enabled = (
            isinstance(gates_config, dict) and gates_config.get("eligibility") is True
        )
        if eligibility_enabled and set(self.eligibility) != requirement_ids:
            self.issue(
                "INDUSTRY_RESUME.ELIGIBILITY_COVERAGE",
                "eligibility results must cover every requirement exactly once",
            )
        if not eligibility_enabled and self.eligibility:
            self.issue(
                "INDUSTRY_RESUME.GATE_DATA",
                "disabled Gate 1 requires eligibility_results=[]",
            )

        gap_by_requirement: dict[str, list[dict[str, Any]]] = {}
        for gap in self.gaps.values():
            requirement_id = gap.get("requirement_id")
            if isinstance(requirement_id, str):
                gap_by_requirement.setdefault(requirement_id, []).append(gap)
            evidence = self._evidence_for(gap)
            direct_supported = any(self._is_authorized_direct_evidence(item) for item in evidence)
            if gap.get("category") == "TRUE_GAP":
                if gap.get("resolution_status") != "OPEN" or gap.get("recommended_action") != "leave_as_gap":
                    self.issue(
                        "INDUSTRY_RESUME.TRUE_GAP",
                        "TRUE_GAP must remain OPEN and use leave_as_gap rather than a wording repair",
                        requirement=requirement_id,
                    )
                if direct_supported:
                    self.issue(
                        "INDUSTRY_RESUME.TRUE_GAP",
                        "TRUE_GAP cannot cite direct level 2-4 evidence",
                        requirement=requirement_id,
                    )
            elif gap.get("category") == "RESUME_GAP":
                hidden_support = any(
                    item.get("relationship_to_requirement") == "DIRECT"
                    and isinstance(item.get("evidence_level"), int)
                    and item.get("evidence_level") >= 2
                    and item.get("resume_visibility") in {"missing", "implicit"}
                    for item in evidence
                )
                if not hidden_support:
                    self.issue(
                        "INDUSTRY_RESUME.RESUME_GAP",
                        "RESUME_GAP requires direct source evidence that was missing or implicit in the baseline resume",
                        requirement=requirement_id,
                    )
            elif gap.get("category") == "POSITIONING_GAP":
                visible_support = any(
                    item.get("relationship_to_requirement") == "DIRECT"
                    and isinstance(item.get("evidence_level"), int)
                    and item.get("evidence_level") >= 2
                    and item.get("resume_visibility") == "explicit"
                    for item in evidence
                )
                if not visible_support or gap.get("recommended_action") not in {"move_higher", "strengthen_wording"}:
                    self.issue(
                        "INDUSTRY_RESUME.POSITIONING_GAP",
                        "POSITIONING_GAP requires explicit supported resume evidence and a framing/placement action",
                        requirement=requirement_id,
                    )

        for requirement_id, requirement_gaps in gap_by_requirement.items():
            if len(requirement_gaps) > 1:
                self.issue(
                    "INDUSTRY_RESUME.GAP_TAXONOMY",
                    "a requirement may have at most one current gap classification",
                    requirement=requirement_id,
                )

        if not eligibility_enabled:
            return

        for requirement_id, result in self.eligibility.items():
            evidence = self._evidence_for(result)
            direct_supported = any(self._is_authorized_direct_evidence(item) for item in evidence)
            classification = result.get("classification")
            if classification in {"met", "probably_met_but_not_explicit"} and not direct_supported:
                self.issue(
                    "INDUSTRY_RESUME.ELIGIBILITY",
                    f"{classification} requires direct level 2-4 source evidence",
                    requirement=requirement_id,
                )
            if classification == "not_met" and direct_supported:
                self.issue(
                    "INDUSTRY_RESUME.ELIGIBILITY",
                    "not_met contradicts direct level 2-4 source evidence",
                    requirement=requirement_id,
                )
            requirement_gaps = gap_by_requirement.get(requirement_id, [])
            categories = {gap.get("category") for gap in requirement_gaps}
            true_gaps = [gap for gap in requirement_gaps if gap.get("category") == "TRUE_GAP"]
            if result.get("true_gap") and len(true_gaps) != 1:
                self.issue(
                    "INDUSTRY_RESUME.TRUE_GAP",
                    "eligibility true_gap=true requires exactly one explicit TRUE_GAP record",
                    requirement=requirement_id,
                )
            if classification == "not_met" and not direct_supported and (
                result.get("true_gap") is not True or len(true_gaps) != 1
            ):
                self.issue(
                    "INDUSTRY_RESUME.TRUE_GAP",
                    "not_met without authorized direct evidence must set true_gap=true and preserve exactly one TRUE_GAP",
                    requirement=requirement_id,
                )
            if classification == "probably_met_but_not_explicit" and "RESUME_GAP" not in categories:
                self.issue(
                    "INDUSTRY_RESUME.RESUME_GAP",
                    "probably_met_but_not_explicit requires a RESUME_GAP record",
                    requirement=requirement_id,
                )

    def _validate_semantic_alignment(self) -> None:
        config = self.analysis.get("config", {})
        gates_config = config.get("gates", {}) if isinstance(config, dict) else {}
        if not (isinstance(gates_config, dict) and gates_config.get("semantic_alignment") is True):
            if self.analysis.get("semantic_alignments"):
                self.issue(
                    "INDUSTRY_RESUME.GATE_DATA",
                    "disabled Gate 3 requires semantic_alignments=[]",
                )
            return
        by_requirement: dict[str, list[dict[str, Any]]] = {}
        seen: set[str] = set()
        for alignment in _records(self.analysis.get("semantic_alignments")):
            alignment_id = alignment.get("alignment_id")
            if isinstance(alignment_id, str):
                if alignment_id in seen:
                    self.issue("INDUSTRY_RESUME.ID_UNIQUE", f"duplicate alignment ID {alignment_id!r}")
                seen.add(alignment_id)
            requirement_id = alignment.get("requirement_id")
            if isinstance(requirement_id, str):
                by_requirement.setdefault(requirement_id, []).append(alignment)
            if alignment.get("relationship") == "NOT_EQUIVALENT" and alignment.get("approved_for_revision"):
                self.issue(
                    "INDUSTRY_RESUME.SEMANTIC_EQUIVALENCE",
                    "a NOT_EQUIVALENT term cannot be approved as a resume replacement",
                    requirement=requirement_id,
                )
            if alignment.get("approved_for_revision"):
                evidence = self._evidence_for(alignment)
                if alignment.get("relationship") not in {"EXACT", "SUPPORTED_SYNONYM"} or not any(
                    item.get("relationship_to_requirement") == "DIRECT"
                    and isinstance(item.get("evidence_level"), int)
                    and item.get("evidence_level") >= 2
                    for item in evidence
                ):
                    self.issue(
                        "INDUSTRY_RESUME.SEMANTIC_EQUIVALENCE",
                        "approved terminology requires exact/supported-synonym status and direct level 2-4 evidence",
                        requirement=requirement_id,
                    )
        missing = set(self.requirements) - set(by_requirement)
        if missing:
            self.issue(
                "INDUSTRY_RESUME.SEMANTIC_COVERAGE",
                f"semantic alignment is missing requirements: {', '.join(sorted(missing))}",
            )

    def _validate_qualifications(self) -> None:
        config = self.analysis.get("config", {})
        gates_config = config.get("gates", {}) if isinstance(config, dict) else {}
        if not (isinstance(gates_config, dict) and gates_config.get("ai_recruiter") is True):
            if self.qualifications:
                self.issue(
                    "INDUSTRY_RESUME.GATE_DATA",
                    "disabled Gate 5 requires qualification_results=[]",
                )
            return
        requirement_ids = set(self.requirements)
        if set(self.qualifications) != requirement_ids:
            self.issue(
                "INDUSTRY_RESUME.QUALIFICATION_COVERAGE",
                "AI recruiter results must cover every requirement exactly once",
            )
        run = self.analysis.get("run", {})
        current_id = run.get("current_resume_source_id") if isinstance(run, dict) else None
        current_hash = run.get("current_resume_hash") if isinstance(run, dict) else None

        for requirement_id, result in self.qualifications.items():
            if (
                result.get("evaluated_resume_source_id") != current_id
                or result.get("evaluated_resume_hash") != current_hash
            ):
                self.issue(
                    "INDUSTRY_RESUME.RECRUITER_SOURCE_BOUNDARY",
                    "qualification result is not bound to the exact current resume",
                    requirement=requirement_id,
                )
            evidence = self._evidence_for(result)
            if any(item.get("source_id") != current_id for item in evidence):
                self.issue(
                    "INDUSTRY_RESUME.RECRUITER_SOURCE_BOUNDARY",
                    "AI recruiter result cites evidence outside the current resume",
                    requirement=requirement_id,
                )
            classification = result.get("classification")
            explicit_direct = any(
                item.get("relationship_to_requirement") == "DIRECT"
                and isinstance(item.get("evidence_level"), int)
                and item.get("evidence_level") >= 2
                and item.get("resume_visibility") == "explicit"
                for item in evidence
            )
            if classification == "MET" and not explicit_direct:
                self.issue(
                    "INDUSTRY_RESUME.QUALIFICATION_CLASSIFICATION",
                    "MET requires explicit direct level 2-4 evidence in the current resume",
                    requirement=requirement_id,
                )
            if classification == "PARTIAL" and not evidence:
                self.issue(
                    "INDUSTRY_RESUME.QUALIFICATION_CLASSIFICATION",
                    "PARTIAL requires related or incomplete evidence in the current resume",
                    requirement=requirement_id,
                )
            if classification == "NOT_FOUND" and (
                evidence
                or result.get("evidence_excerpt") is not None
                or result.get("evidence_location") is not None
            ):
                self.issue(
                    "INDUSTRY_RESUME.QUALIFICATION_CLASSIFICATION",
                    "NOT_FOUND must not cite resume evidence",
                    requirement=requirement_id,
                )
            if classification in {"MET", "PARTIAL"} and (
                result.get("evidence_excerpt") is None
                or result.get("evidence_location") is None
            ):
                self.issue(
                    "INDUSTRY_RESUME.QUALIFICATION_CLASSIFICATION",
                    f"{classification} requires an evidence excerpt and location",
                    requirement=requirement_id,
                )
            if classification in {"MET", "PARTIAL"} and not any(
                item.get("source_id") == current_id
                and item.get("source_excerpt") == result.get("evidence_excerpt")
                and item.get("source_location") == result.get("evidence_location")
                for item in evidence
            ):
                self.issue(
                    "INDUSTRY_RESUME.QUALIFICATION_PROVENANCE",
                    f"{classification} excerpt/location must exactly match a cited current-resume evidence item",
                    requirement=requirement_id,
                )
            if (
                classification == "NOT_FOUND"
                and self.requirements.get(requirement_id, {}).get("priority") == "required"
            ):
                authorized_direct = any(
                    self._is_authorized_direct_evidence(item)
                    for item in self.evidence.values()
                    if item.get("requirement_id") == requirement_id
                )
                true_gap_count = sum(
                    gap.get("requirement_id") == requirement_id
                    and gap.get("category") == "TRUE_GAP"
                    for gap in self.gaps.values()
                )
                if not authorized_direct and true_gap_count != 1:
                    self.issue(
                        "INDUSTRY_RESUME.TRUE_GAP",
                        "required NOT_FOUND without authorized direct evidence must preserve exactly one TRUE_GAP",
                        requirement=requirement_id,
                    )

    def _validate_claim_provenance(self) -> None:
        run = self.analysis.get("run", {})
        removed_claims = _records(self.analysis.get("removed_claims"))
        if (
            isinstance(run, dict)
            and run.get("revisions_applied") is True
            and not self.claims
        ):
            self.issue(
                "INDUSTRY_RESUME.PROVENANCE",
                "a revised resume requires nonempty claim provenance for its introduced or strengthened candidate claims",
            )
        removal_ids = [
            item.get("removal_id")
            for item in removed_claims
            if isinstance(item.get("removal_id"), str)
        ]
        if len(removal_ids) != len(set(removal_ids)):
            self.issue(
                "INDUSTRY_RESUME.DUPLICATE_ID",
                "removed-claim IDs must be unique",
            )
        if removed_claims and (
            not isinstance(run, dict) or run.get("revisions_applied") is not True
        ):
            self.issue(
                "INDUSTRY_RESUME.REVISION_PROVENANCE",
                "removed-claim records require a revised resume",
            )
        for removal in removed_claims:
            removal_id = removal.get("removal_id")
            source = self.sources.get(removal.get("baseline_resume_source_id"))
            if (
                source is None
                or source.get("source_type") != "BASELINE_RESUME"
                or source.get("content_authority") is not True
                or source.get("sha256") != removal.get("baseline_resume_hash")
                or removal.get("authorization_verified") is not True
            ):
                self.issue(
                    "INDUSTRY_RESUME.REVISION_PROVENANCE",
                    f"removed claim {removal_id!r} requires authorized hash-bound baseline provenance",
                )
            for requirement_id in removal.get("requirement_ids", []):
                if requirement_id not in self.requirements:
                    self.issue(
                        "INDUSTRY_RESUME.REFERENCE",
                        f"removed claim {removal_id!r} references unknown requirement {requirement_id!r}",
                    )
        true_gap_requirements = {
            gap.get("requirement_id")
            for gap in self.gaps.values()
            if gap.get("category") == "TRUE_GAP" and gap.get("resolution_status") == "OPEN"
        }
        for claim_id, claim in self.claims.items():
            requirement_ids = set(claim.get("requirement_ids", []))
            if isinstance(run, dict) and (
                claim.get("resume_source_id") != run.get("current_resume_source_id")
                or claim.get("resume_hash") != run.get("current_resume_hash")
            ):
                self.issue(
                    "INDUSTRY_RESUME.PROVENANCE",
                    f"claim {claim_id!r} is not bound to the exact current resume ID/hash",
                )
            for requirement_id in requirement_ids:
                if requirement_id not in self.requirements:
                    self.issue(
                        "INDUSTRY_RESUME.REFERENCE",
                        f"claim {claim_id!r} references unknown requirement {requirement_id!r}",
                    )
            fact_ids = claim.get("candidate_fact_ids", [])
            evidence_ids = claim.get("evidence_item_ids", [])
            if any(fact_id not in self.facts for fact_id in fact_ids) or any(
                evidence_id not in self.evidence for evidence_id in evidence_ids
            ):
                self.issue(
                    "INDUSTRY_RESUME.PROVENANCE",
                    f"claim {claim_id!r} contains an unknown fact/evidence reference",
                )
            if claim.get("support_status") == "SUPPORTED" and (not fact_ids or not evidence_ids):
                self.issue(
                    "INDUSTRY_RESUME.PROVENANCE",
                    f"supported claim {claim_id!r} requires both candidate facts and evidence items",
                )
            cited_evidence = [
                self.evidence[evidence_id]
                for evidence_id in evidence_ids
                if evidence_id in self.evidence
            ]
            cited_requirement_ids = {
                item.get("requirement_id") for item in cited_evidence
            }
            cited_fact_ids = {
                fact_id
                for item in cited_evidence
                for fact_id in item.get("candidate_fact_ids", [])
            }
            if claim.get("support_status") == "SUPPORTED" and (
                not requirement_ids
                or cited_requirement_ids != requirement_ids
                or cited_fact_ids != set(fact_ids)
            ):
                self.issue(
                    "INDUSTRY_RESUME.PROVENANCE_CROSSLINK",
                    f"supported claim {claim_id!r} must use only evidence for its requirements and exactly the facts covered by that evidence",
                )
            relationship = claim.get("revision_relationship")
            baseline_source_id = claim.get("baseline_resume_source_id")
            baseline_hash = claim.get("baseline_resume_hash")
            baseline_excerpt = claim.get("baseline_resume_excerpt")
            baseline_source = (
                self.sources.get(baseline_source_id)
                if isinstance(baseline_source_id, str)
                else None
            )
            if relationship in {"UNCHANGED", "STRENGTHENED"}:
                if (
                    baseline_source is None
                    or baseline_source.get("source_type") != "BASELINE_RESUME"
                    or baseline_source.get("content_authority") is not True
                    or baseline_source.get("candidate_evidence_allowed") is not True
                    or baseline_source.get("sha256") != baseline_hash
                    or not isinstance(baseline_excerpt, str)
                ):
                    self.issue(
                        "INDUSTRY_RESUME.REVISION_PROVENANCE",
                        f"{relationship.lower()} claim {claim_id!r} requires an authoritative hash-bound baseline-resume excerpt",
                    )
                elif relationship == "UNCHANGED" and baseline_excerpt != claim.get(
                    "resume_excerpt"
                ):
                    self.issue(
                        "INDUSTRY_RESUME.REVISION_PROVENANCE",
                        f"unchanged claim {claim_id!r} must exactly match its baseline excerpt",
                    )
                elif relationship == "STRENGTHENED" and baseline_excerpt == claim.get(
                    "resume_excerpt"
                ):
                    self.issue(
                        "INDUSTRY_RESUME.REVISION_PROVENANCE",
                        f"strengthened claim {claim_id!r} must differ from its baseline excerpt",
                    )
            elif relationship == "INTRODUCED" and any(
                value is not None
                for value in (baseline_source_id, baseline_hash, baseline_excerpt)
            ):
                self.issue(
                    "INDUSTRY_RESUME.REVISION_PROVENANCE",
                    f"introduced claim {claim_id!r} must not claim a baseline excerpt",
                )
            if claim.get("support_status") == "SUPPORTED" and relationship in {
                "INTRODUCED",
                "STRENGTHENED",
            }:
                current_source = (
                    self.sources.get(run.get("current_resume_source_id"))
                    if isinstance(run, dict)
                    else None
                )
                upstream_fact_ids = {
                    fact_id
                    for fact_id in fact_ids
                    if (
                        (fact := self.facts.get(fact_id)) is not None
                        and (source := self.sources.get(fact.get("source_id"))) is not None
                        and source.get("content_authority") is True
                        and source.get("candidate_evidence_allowed") is True
                        and source.get("source_type")
                        not in {"JOB_DESCRIPTION", "CURRENT_RESUME"}
                        and (
                            current_source is None
                            or not _sources_alias(source, current_source)
                        )
                    )
                }
                if upstream_fact_ids != set(fact_ids):
                    self.issue(
                        "INDUSTRY_RESUME.PROVENANCE_CIRCULAR",
                        f"introduced or strengthened claim {claim_id!r} must derive every candidate fact from non-aliased authoritative upstream evidence rather than the generated current resume",
                    )
            if claim.get("represents_requirement_as_met") and requirement_ids & true_gap_requirements:
                self.issue(
                    "INDUSTRY_RESUME.TRUE_GAP",
                    f"claim {claim_id!r} represents an open TRUE_GAP as met",
                )
            if claim.get("support_status") != "SUPPORTED":
                audits = self.analysis.get("audits", {})
                integrity = audits.get("integrity", {}) if isinstance(audits, dict) else {}
                gate = self.gates.get("GATE_8", {})
                if (
                    not isinstance(integrity, dict)
                    or claim_id not in integrity.get("unsupported_claim_ids", [])
                    or integrity.get("status") != "FAIL"
                    or gate.get("status") != "FAIL"
                    or gate.get("blocking") is not True
                    or not isinstance(run, dict)
                    or run.get("overall_status") != "FAIL"
                ):
                    self.issue(
                        "INDUSTRY_RESUME.CLAIM_STATUS_PROPAGATION",
                        f"non-supported current claim {claim_id!r} must be recorded by the integrity audit and propagate to blocking Gate 8 and overall FAIL",
                    )

    def _gate_status(self, gate_id: str) -> Any:
        return self.gates.get(gate_id, {}).get("status")

    def _validate_audits(self) -> None:
        audits = self.analysis.get("audits")
        run = self.analysis.get("run", {})
        if not isinstance(audits, dict):
            self.issue("INDUSTRY_RESUME.AUDIT_COMPLETENESS", "AI/ATS mode requires the complete audit bundle")
            return
        config = self.analysis.get("config", {})
        gates_config = config.get("gates", {}) if isinstance(config, dict) else {}
        for config_key, audit_fields in (
            ("ats_parse", ("ats_parse",)),
            ("ai_recruiter", ("ai_recruiter",)),
            ("recruiter_scan", ("human_recruiter", "top_third")),
            ("hiring_manager", ("hiring_manager",)),
            ("integrity", ("integrity",)),
        ):
            enabled = isinstance(gates_config, dict) and gates_config.get(config_key) is True
            for audit_field in audit_fields:
                audit_value = audits.get(audit_field)
                if enabled and not isinstance(audit_value, dict):
                    self.issue(
                        "INDUSTRY_RESUME.AUDIT_COMPLETENESS",
                        f"enabled {config_key} gate requires a structured {audit_field} audit",
                    )
                if not enabled and audit_value is not None:
                    self.issue(
                        "INDUSTRY_RESUME.AUDIT_CONFIG",
                        f"disabled {config_key} gate requires {audit_field}=null",
                    )
        current_id = run.get("current_resume_source_id") if isinstance(run, dict) else None
        current_hash = run.get("current_resume_hash") if isinstance(run, dict) else None

        for audit_field in (
            "human_recruiter",
            "top_third",
            "hiring_manager",
            "integrity",
        ):
            audit_value = audits.get(audit_field)
            if isinstance(audit_value, dict) and (
                audit_value.get("evaluated_resume_source_id") != current_id
                or audit_value.get("evaluated_resume_hash") != current_hash
            ):
                self.issue(
                    "INDUSTRY_RESUME.AUDIT_SOURCE_BOUNDARY",
                    f"{audit_field} audit is not bound to the exact current resume source ID/hash",
                )

        ats = audits.get("ats_parse")
        final_artifact = self.outputs.get("FINAL_RESUME", {})
        final_document_cycle = (
            isinstance(run, dict)
            and run.get("operation") in {"RELEASE", "SELF_DRIVING"}
            and run.get("overall_status") in {"PASS", "PASS_WITH_WARNINGS"}
            and final_artifact.get("format") in {"PDF", "DOCX", "TXT"}
        )
        if final_document_cycle and not isinstance(ats, dict):
            self.issue(
                "INDUSTRY_RESUME.ATS_EXECUTION",
                "successful final PDF/DOCX/TXT requires a structured ATS extraction audit",
            )
        if isinstance(ats, dict):
            if ats.get("resume_source_id") != current_id or ats.get("resume_hash") != current_hash:
                self.issue(
                    "INDUSTRY_RESUME.CURRENT_RESUME",
                    "ATS audit is not bound to the exact current resume",
                )
            if ats.get("ocr_used") is True:
                if (
                    ats.get("extraction_method") != "OCR"
                    or not isinstance(ats.get("ocr_reason"), str)
                    or not ats.get("ocr_reason")
                ):
                    self.issue(
                        "INDUSTRY_RESUME.ATS_EXECUTION",
                        "OCR use requires extraction_method OCR and a nonempty reason",
                    )
            elif ats.get("extraction_method") == "OCR" or ats.get("ocr_reason") is not None:
                self.issue(
                    "INDUSTRY_RESUME.ATS_EXECUTION",
                    "OCR metadata must be absent unless OCR was actually used",
                )
            if final_document_cycle and (
                ats.get("actual_extraction_performed") is not True
                or ats.get("logical_order_compared") is not True
            ):
                self.issue(
                    "INDUSTRY_RESUME.ATS_EXECUTION",
                    "successful final PDF/DOCX/TXT requires actual text extraction and logical-order comparison",
                )
            recovery = ats.get("recovery", {})
            mandatory_fields = (
                "candidate_name",
                "contact_information",
                "section_headings",
                "employers",
                "job_titles",
                "dates",
                "education",
                "skills",
            )
            hard_failure = (
                isinstance(recovery, dict)
                and any(recovery.get(field) != "RECOVERED" for field in mandatory_fields)
            ) or ats.get("chronology") == "FAIL" or ats.get("reading_order") == "FAIL" or bool(
                ats.get("critical_text_lost")
            )
            warning = ats.get("chronology") == "WARN" or ats.get("reading_order") == "WARN" or bool(
                ats.get("anomalies")
            )
            expected = "FAIL" if hard_failure else "PASS_WITH_WARNINGS" if warning else "PASS"
            if ats.get("status") != expected:
                self.issue(
                    "INDUSTRY_RESUME.ATS_STATUS",
                    f"ATS audit status must be {expected} for its recorded recovery/order findings",
                )
            if self._gate_status("GATE_4") != ats.get("status"):
                self.issue("INDUSTRY_RESUME.GATE_STATUS", "Gate 4 status must match the ATS audit")

        recruiter = audits.get("ai_recruiter")
        if isinstance(recruiter, dict):
            source_boundary_valid = not (
                recruiter.get("evaluated_resume_source_id") != current_id
                or recruiter.get("evaluated_resume_hash") != current_hash
                or recruiter.get("hidden_context_used") is not False
            )
            if not source_boundary_valid:
                self.issue(
                    "INDUSTRY_RESUME.RECRUITER_SOURCE_BOUNDARY",
                    "AI recruiter audit must use only the exact current resume as candidate evidence",
                )
            qualification_coverage_valid = (
                set(recruiter.get("qualification_requirement_ids", []))
                == set(self.requirements)
                and set(self.qualifications) == set(self.requirements)
            )
            if not qualification_coverage_valid:
                self.issue(
                    "INDUSTRY_RESUME.QUALIFICATION_COVERAGE",
                    "AI recruiter audit must enumerate every requirement",
                )
            evaluator_statuses = [
                item.get("status")
                for item in self.evaluator_runs.values()
                if item.get("gate_id") == "GATE_5"
            ]
            evaluator_succeeded = evaluator_statuses == ["SUCCEEDED"]
            if not evaluator_succeeded or not source_boundary_valid or not qualification_coverage_valid:
                expected_recruiter_status = "FAIL"
            elif any(
                result.get("classification") in {"PARTIAL", "NOT_FOUND"}
                for result in self.qualifications.values()
            ):
                expected_recruiter_status = "PASS_WITH_WARNINGS"
            else:
                expected_recruiter_status = "PASS"
            if recruiter.get("status") != expected_recruiter_status:
                self.issue(
                    "INDUSTRY_RESUME.AI_RECRUITER_STATUS",
                    f"successful Gate 5 status must be {expected_recruiter_status} from qualification classifications; FAIL is reserved for evaluator/source/coverage failure",
                )
            if self._gate_status("GATE_5") != recruiter.get("status"):
                self.issue("INDUSTRY_RESUME.GATE_STATUS", "Gate 5 status must match the AI recruiter audit")

        human = audits.get("human_recruiter")
        top_third = audits.get("top_third")
        if isinstance(human, dict) and isinstance(top_third, dict):
            expected_human = _status_from_rating(human.get("rating"))
            if human.get("rating") in {"STRONG", "ACCEPTABLE"} and len(
                human.get("top_capabilities", [])
            ) < 3:
                expected_human = "FAIL"
            if human.get("rating") == "STRONG" and (
                not human.get("target_role_recovered")
                or not human.get("seniority_recovered")
                or not human.get("target_connection_obvious")
                or human.get("wrong_identity_signal")
                or not human.get("relevant_terms_visible_early")
                or not human.get("easy_to_skim")
            ):
                expected_human = "FAIL"
            expected_top = _status_from_rating(top_third.get("rating"))
            if top_third.get("rating") in {"STRONG", "ACCEPTABLE"} and len(
                top_third.get("top_domains", [])
            ) < 5:
                expected_top = "FAIL"
            if top_third.get("rating") == "STRONG" and not top_third.get("target_role_represented"):
                expected_top = "FAIL"
            if human.get("status") != expected_human or top_third.get("status") != expected_top:
                self.issue(
                    "INDUSTRY_RESUME.RECRUITER_SCAN_STATUS",
                    "recruiter and top-third statuses must follow their recorded ratings/signals",
                )
            if self._gate_status("GATE_6") != _worst_status(human.get("status"), top_third.get("status")):
                self.issue(
                    "INDUSTRY_RESUME.GATE_STATUS",
                    "Gate 6 status must equal the worse of recruiter-scan and top-third results",
                )

        manager = audits.get("hiring_manager")
        if isinstance(manager, dict):
            dimension_records = _records(manager.get("dimension_results"))
            by_dimension: dict[str, dict[str, Any]] = {}
            duplicate_dimensions: set[str] = set()
            for dimension in dimension_records:
                name = dimension.get("dimension")
                if not isinstance(name, str):
                    continue
                if name in by_dimension:
                    duplicate_dimensions.add(name)
                else:
                    by_dimension[name] = dimension

            dimension_names = set(by_dimension)
            complete = (
                dimension_names == set(ROLE_DIMENSIONS)
                and not duplicate_dimensions
                and len(dimension_records) == len(ROLE_DIMENSIONS)
            )
            if not complete:
                self.issue(
                    "INDUSTRY_RESUME.HIRING_MANAGER_DIMENSIONS",
                    "hiring-manager review must contain each role-aware dimension exactly once",
                )

            target_context = manager.get("target_context")
            applicability_valid = complete
            applicable_ratings: list[str] = []
            for name in ROLE_DIMENSIONS:
                dimension = by_dimension.get(name)
                if dimension is None:
                    applicability_valid = False
                    continue
                applicability = dimension.get("applicability")
                rating = dimension.get("rating")
                if applicability == "APPLICABLE":
                    if rating not in {"STRONG", "ACCEPTABLE", "WEAK"}:
                        applicability_valid = False
                    else:
                        applicable_ratings.append(rating)
                elif applicability == "NOT_APPLICABLE":
                    if rating is not None:
                        applicability_valid = False
                    if target_context == "SCIENTIFIC_TECHNICAL":
                        applicability_valid = False
                    if target_context == "NON_RESEARCH" and name in ROLE_RELEVANT_DIMENSIONS:
                        applicability_valid = False
                else:
                    applicability_valid = False

            if not applicability_valid:
                self.issue(
                    "INDUSTRY_RESUME.HIRING_MANAGER_APPLICABILITY",
                    "scientific/technical targets require every dimension; non-research targets may omit only scientific-only dimensions and must retain role-relevant dimensions including claim credibility",
                )

            derived_rating = (
                "WEAK"
                if not applicability_valid or "WEAK" in applicable_ratings
                else "ACCEPTABLE"
                if "ACCEPTABLE" in applicable_ratings
                else "STRONG"
            )
            depth_rating = by_dimension.get("depth", {}).get("rating")
            ownership_rating = by_dimension.get("ownership", {}).get("rating")
            credibility_rating = by_dimension.get("claim_credibility", {}).get("rating")
            if (
                manager.get("rating") != derived_rating
                or manager.get("technical_depth") != depth_rating
                or manager.get("ownership_clear") is not (ownership_rating != "WEAK")
                or manager.get("claims_credible") is not (credibility_rating != "WEAK")
            ):
                self.issue(
                    "INDUSTRY_RESUME.HIRING_MANAGER_DIMENSIONS",
                    "top-level hiring-manager signals must match the worst applicable dimension and the depth, ownership, and claim-credibility results",
                )

            expected = _status_from_rating(derived_rating)
            if manager.get("generic_after_optimization") and expected == "PASS":
                expected = "PASS_WITH_WARNINGS"
            if manager.get("status") != expected:
                self.issue(
                    "INDUSTRY_RESUME.HIRING_MANAGER_STATUS",
                    f"hiring-manager audit status must be {expected} for its recorded findings",
                )
            if self._gate_status("GATE_7") != manager.get("status"):
                self.issue("INDUSTRY_RESUME.GATE_STATUS", "Gate 7 status must match the hiring-manager audit")

        integrity = audits.get("integrity")
        if isinstance(integrity, dict):
            hard_failure = any(
                (
                    integrity.get("unsupported_claim_ids"),
                    integrity.get("inflated_ownership_claim_ids"),
                    integrity.get("inflated_seniority_claim_ids"),
                    integrity.get("invented_metric_claim_ids"),
                    integrity.get("unsupported_direct_experience_claim_ids"),
                    integrity.get("semantic_drift_claim_ids"),
                    integrity.get("caveat_loss_claim_ids"),
                    integrity.get("keyword_stuffing") is True,
                )
            )
            warning = bool(
                integrity.get("jd_mimicry_concerns")
                or integrity.get("duplicated_concept_findings")
                or integrity.get("related_vs_direct_ambiguities")
            )
            expected = "FAIL" if hard_failure else "PASS_WITH_WARNINGS" if warning else "PASS"
            if integrity.get("status") != expected:
                self.issue(
                    "INDUSTRY_RESUME.INTEGRITY_STATUS",
                    f"integrity audit status must be {expected} for its recorded findings",
                )
            if self._gate_status("GATE_8") != integrity.get("status"):
                self.issue("INDUSTRY_RESUME.GATE_STATUS", "Gate 8 status must match the integrity audit")

    def _validate_evaluator_runs(self) -> None:
        config = self.analysis.get("config", {})
        run = self.analysis.get("run", {})
        gates_config = config.get("gates", {}) if isinstance(config, dict) else {}
        expected_gate_ids = {
            gate_id
            for gate_id in (
                "GATE_0",
                "GATE_2",
                "GATE_3",
                "GATE_4",
                "GATE_5",
                "GATE_6",
                "GATE_7",
                "GATE_8",
            )
            if isinstance(gates_config, dict)
            and gates_config.get(GATE_CONFIG[gate_id]) is True
        }
        by_gate: dict[str, list[dict[str, Any]]] = {}
        for evaluator in self.evaluator_runs.values():
            gate_id = evaluator.get("gate_id")
            if isinstance(gate_id, str):
                by_gate.setdefault(gate_id, []).append(evaluator)

            attempt_count = evaluator.get("attempt_count")
            retry_count = evaluator.get("retry_count")
            max_retries = config.get("max_evaluator_retries") if isinstance(config, dict) else None
            if (
                not isinstance(attempt_count, int)
                or not isinstance(retry_count, int)
                or attempt_count != retry_count + 1
                or (isinstance(max_retries, int) and retry_count > max_retries)
            ):
                self.issue(
                    "INDUSTRY_RESUME.EVALUATOR_RETRY",
                    "evaluator attempts must equal one initial call plus bounded retries",
                )

            repair_count = evaluator.get("schema_repair_count")
            if repair_count not in {0, 1} or evaluator.get(
                "schema_repair_attempted"
            ) is not (repair_count == 1):
                self.issue(
                    "INDUSTRY_RESUME.EVALUATOR_REPAIR",
                    "schema repair attempted must exactly match the single allowed repair count",
                )

            status = evaluator.get("status")
            failure_type = evaluator.get("failure_type")
            failure_reason = evaluator.get("failure_reason")
            if status == "SUCCEEDED":
                if failure_type != "NONE" or failure_reason is not None:
                    self.issue(
                        "INDUSTRY_RESUME.EVALUATOR_STATUS",
                        "successful evaluator runs cannot retain failure metadata",
                    )
            else:
                gate = self.gates.get(gate_id, {})
                retries_exhausted = isinstance(max_retries, int) and retry_count == max_retries
                structured_repair_exhausted = (
                    failure_type != "STRUCTURED_OUTPUT"
                    or (
                        evaluator.get("schema_repair_attempted") is True
                        and repair_count == 1
                    )
                )
                if (
                    failure_type == "NONE"
                    or not isinstance(failure_reason, str)
                    or not failure_reason
                    or evaluator.get("completed_artifacts_preserved") is not True
                    or not retries_exhausted
                    or not structured_repair_exhausted
                ):
                    self.issue(
                        "INDUSTRY_RESUME.EVALUATOR_EXHAUSTION",
                        "failed/incomplete evaluator runs must exhaust retries, preserve completed artifacts, and exhaust one structured repair when applicable",
                    )
                if (
                    gate.get("status") != "FAIL"
                    or gate.get("blocking") is not True
                    or not isinstance(run, dict)
                    or run.get("overall_status") != "FAIL"
                ):
                    self.issue(
                        "INDUSTRY_RESUME.EVALUATOR_PROPAGATION",
                        "evaluator failure or incomplete output must propagate to a blocking failed gate and overall FAIL",
                    )

        if set(by_gate) != expected_gate_ids or any(
            len(records) != 1 for records in by_gate.values()
        ):
            self.issue(
                "INDUSTRY_RESUME.EVALUATOR_COVERAGE",
                "each enabled model-backed gate (0, 2, and 3-8) requires exactly one evaluator-run record",
            )

    def _validate_gates_and_status(self) -> None:
        config = self.analysis.get("config", {})
        run = self.analysis.get("run", {})
        gates_config = config.get("gates", {}) if isinstance(config, dict) else {}
        if set(self.gates) != set(GATE_CONFIG):
            self.issue(
                "INDUSTRY_RESUME.GATE_COVERAGE",
                "AI/ATS mode requires one result for each Gate 0 through Gate 8",
            )
        for gate_id, config_key in GATE_CONFIG.items():
            gate = self.gates.get(gate_id)
            if gate is None or not isinstance(gates_config, dict):
                continue
            configured = gates_config.get(config_key)
            if gate.get("enabled") is not configured:
                self.issue(
                    "INDUSTRY_RESUME.GATE_CONFIG",
                    f"{gate_id} enabled flag does not match config.{config_key}",
                )
            if configured and gate.get("status") == "NOT_RUN":
                self.issue(
                    "INDUSTRY_RESUME.GATE_COMPLETENESS",
                    f"enabled {gate_id} cannot be NOT_RUN",
                )
            if not configured and gate.get("status") != "NOT_RUN":
                self.issue(
                    "INDUSTRY_RESUME.GATE_CONFIG",
                    f"disabled {gate_id} must be NOT_RUN",
                )
        if isinstance(config, dict) and config.get("ai_ats_mode") and not gates_config.get("integrity"):
            self.issue(
                "INDUSTRY_RESUME.GATE_CONFIG",
                "the integrity gate is mandatory whenever AI/ATS mode is enabled",
            )

        enabled_statuses = [
            gate.get("status")
            for gate in self.gates.values()
            if gate.get("enabled")
        ]
        expected = (
            "FAIL"
            if "FAIL" in enabled_statuses
            else "PASS_WITH_WARNINGS"
            if "PASS_WITH_WARNINGS" in enabled_statuses
            else "PASS"
        )
        if isinstance(run, dict) and run.get("overall_status") != expected:
            self.issue(
                "INDUSTRY_RESUME.STATUS_PROPAGATION",
                f"overall_status must be {expected} for the recorded enabled gate results",
            )
        for gate in self.gates.values():
            status = gate.get("status")
            blocking = gate.get("blocking")
            if status == "FAIL" and blocking is not True:
                self.issue(
                    "INDUSTRY_RESUME.STATUS_PROPAGATION",
                    f"failed {gate.get('gate_id')} must be marked blocking",
                )
            elif status != "FAIL" and blocking is not False:
                self.issue(
                    "INDUSTRY_RESUME.STATUS_PROPAGATION",
                    f"non-failed {gate.get('gate_id')} cannot be marked blocking",
                )

    def _validate_metrics(self) -> None:
        metrics = self.analysis.get("metrics")
        if not isinstance(metrics, dict):
            self.issue("INDUSTRY_RESUME.METRICS", "AI/ATS mode requires coverage metrics")
            return
        config = self.analysis.get("config", {})
        gates_config = config.get("gates", {}) if isinstance(config, dict) else {}
        qualification_enabled = (
            isinstance(gates_config, dict) and gates_config.get("ai_recruiter") is True
        )
        groups = {"required": [], "preferred": []}
        for requirement_id, requirement in self.requirements.items():
            priority = requirement.get("priority")
            if priority in groups:
                result = self.qualifications.get(requirement_id)
                if qualification_enabled and result is not None:
                    groups[priority].append(result.get("classification"))
        for priority, field in (("required", "required_qualifications"), ("preferred", "preferred_qualifications")):
            classifications = groups[priority]
            expected = {
                "met": classifications.count("MET"),
                "partial": classifications.count("PARTIAL"),
                "not_found": classifications.count("NOT_FOUND"),
                "total": len(classifications),
            }
            if metrics.get(field) != expected:
                self.issue(
                    "INDUSTRY_RESUME.METRICS",
                    f"{field} counts do not match qualification results",
                )

        maxima: list[int] = []
        for requirement_id in self.requirements:
            levels = [
                item.get("evidence_level")
                for item in self.evidence.values()
                if item.get("requirement_id") == requirement_id
                and isinstance(item.get("evidence_level"), int)
            ]
            maxima.append(max(levels, default=0))
        expected_strength = {
            "level_3_4": sum(level >= 3 for level in maxima),
            "level_2": sum(level == 2 for level in maxima),
            "level_0_1": sum(level <= 1 for level in maxima),
            "total": len(maxima),
        }
        if metrics.get("evidence_strength") != expected_strength:
            self.issue(
                "INDUSTRY_RESUME.METRICS",
                "evidence-strength counts do not match per-requirement evidence levels",
            )
        expected_missing = (
            sorted(
                requirement_id
                for requirement_id, requirement in self.requirements.items()
                if requirement.get("priority") == "required"
                and self.qualifications.get(requirement_id, {}).get("classification") != "MET"
            )
            if qualification_enabled
            else []
        )
        if sorted(metrics.get("critical_missing_requirement_ids", [])) != expected_missing:
            self.issue(
                "INDUSTRY_RESUME.METRICS",
                "critical missing IDs must equal required qualifications not classified MET",
            )
        if metrics.get("overall_match_percentage") is not None:
            self.issue(
                "INDUSTRY_RESUME.OPAQUE_SCORE",
                "overall match percentage is prohibited; use disaggregated counts",
            )

    def _validate_outputs(self) -> None:
        suffix_formats = {
            ".docx": "DOCX",
            ".pdf": "PDF",
            ".txt": "TXT",
            ".md": "MD",
            ".markdown": "MD",
            ".json": "JSON",
        }
        source_paths = set().union(*(_source_paths(source) for source in self.sources.values()))
        source_hashes = set().union(*(_source_hashes(source) for source in self.sources.values()))
        artifact_types_by_path: dict[str, list[str]] = {}
        for artifact_type, artifact in self.outputs.items():
            path = artifact.get("relative_path")
            if isinstance(path, str):
                pure = PurePosixPath(path)
                artifact_types_by_path.setdefault(pure.as_posix(), []).append(artifact_type)
                if not _is_safe_relative_path(path):
                    self.issue(
                        "INDUSTRY_RESUME.OUTPUT_PATH",
                        f"{artifact_type} must use a safe relative artifact path",
                    )
                expected_format = suffix_formats.get(pure.suffix.lower())
                if expected_format is not None and artifact.get("format") != expected_format:
                    self.issue(
                        "INDUSTRY_RESUME.OUTPUT_FORMAT",
                        f"{artifact_type} path suffix {pure.suffix.lower()!r} contradicts declared format {artifact.get('format')!r}",
                    )
                allowed_formats = OUTPUT_FORMATS_BY_ARTIFACT.get(artifact_type)
                if allowed_formats is not None and artifact.get("format") not in allowed_formats:
                    self.issue(
                        "INDUSTRY_RESUME.OUTPUT_FORMAT",
                        f"{artifact_type} must use one of these formats: {', '.join(sorted(allowed_formats))}",
                    )
                if artifact_type != "FINAL_RESUME" and (
                    path in source_paths or artifact.get("sha256") in source_hashes
                ):
                    self.issue(
                        "INDUSTRY_RESUME.OUTPUT_PATH",
                        f"{artifact_type} cannot alias registered primary or extracted source bytes/path",
                    )
        for path, artifact_types in artifact_types_by_path.items():
            if len(artifact_types) > 1:
                self.issue(
                    "INDUSTRY_RESUME.OUTPUT_PATH",
                    f"output path {path!r} is aliased by multiple artifact types",
                )
        run = self.analysis.get("run", {})
        if not isinstance(run, dict):
            return
        final_cycle = run.get("operation") in {"RELEASE", "SELF_DRIVING"}
        successful = run.get("overall_status") in {"PASS", "PASS_WITH_WARNINGS"}
        if final_cycle and successful:
            config = self.analysis.get("config", {})
            required_output_types = {"FINAL_RESUME"}
            if isinstance(config, dict) and config.get("save_markdown_audits") is True:
                required_output_types.add("MARKDOWN_AUDIT_PACKAGE")
            missing = required_output_types - set(self.outputs)
            if missing:
                self.issue(
                    "INDUSTRY_RESUME.OUTPUT_COMPLETENESS",
                    f"final successful cycle is missing outputs: {', '.join(sorted(missing))}",
                )
            for artifact_type in sorted(required_output_types & set(self.outputs)):
                artifact = self.outputs[artifact_type]
                if artifact.get("status") != "CREATED" or artifact.get("sha256") is None:
                    self.issue(
                        "INDUSTRY_RESUME.OUTPUT_COMPLETENESS",
                        f"final output {artifact_type} must be CREATED and hash-bound",
                    )
            final_resume = self.outputs.get("FINAL_RESUME")
            current_source = self.sources.get(run.get("current_resume_source_id"), {})
            if (
                final_resume is not None
                and (
                    final_resume.get("sha256") != run.get("current_resume_hash")
                    or final_resume.get("relative_path")
                    != current_source.get("relative_path")
                )
            ):
                self.issue(
                    "INDUSTRY_RESUME.OUTPUT_BINDING",
                    "final successful resume output path/hash must equal the exact current resume source",
                )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def build_audit_package(analysis: dict[str, Any]) -> str:
    """Render the canonical privacy-minimized Markdown audit from the sidecar."""

    def cell(value: Any) -> str:
        if value is None or value == []:
            return "—"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value) or "—"
        else:
            rendered = str(value)
        rendered = rendered.replace("\r", " ").replace("\n", " ")
        rendered = (
            rendered.replace("\\", "\\\\")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        for character in ("`", "!", "[", "]", "(", ")", "|"):
            rendered = rendered.replace(character, f"\\{character}")
        return rendered

    binding_payload = json.loads(json.dumps(analysis))
    for output in _records(binding_payload.get("outputs")):
        if output.get("artifact_type") == "MARKDOWN_AUDIT_PACKAGE":
            output["sha256"] = "<SELF_HASH_NORMALIZED>"
    binding_hash = hashlib.sha256(
        json.dumps(
            binding_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    run = analysis.get("run") if isinstance(analysis.get("run"), dict) else {}
    audits = analysis.get("audits") if isinstance(analysis.get("audits"), dict) else {}

    def audit_record(name: str) -> dict[str, Any]:
        value = audits.get(name)
        return value if isinstance(value, dict) else {}

    def append_key_value_section(
        title: str,
        record: dict[str, Any],
        fields: tuple[tuple[str, str], ...],
    ) -> None:
        lines.extend(["", f"### {title}", "", "| Field | Value |", "|---|---|"])
        for label, field in fields:
            lines.append(f"| {cell(label)} | {cell(record.get(field))} |")

    lines = [
        "# Industry Resume AI/ATS Audit Package",
        "",
        "Generated deterministically from the hash-bound structured sidecar. "
        "Private candidate excerpts remain in that protected sidecar and are not repeated here.",
        "",
        "## Route And Binding",
        "",
        f"- Workflow version: `{cell(analysis.get('workflow_version'))}`",
        f"- Run ID: `{cell(run.get('run_id'))}`",
        f"- Execution: `{cell(run.get('execution_policy'))}` / `{cell(run.get('operation'))}`",
        f"- Overall status: `{cell(run.get('overall_status'))}`",
        f"- Current resume source: `{cell(run.get('current_resume_source_id'))}`",
        f"- Current resume hash: `{cell(run.get('current_resume_hash'))}`",
        f"- Structured audit binding SHA-256: `{binding_hash}`",
        "",
        "## Job Description Analysis",
        "",
        "| Requirement | Priority | Category | Screenable | Source | Source location | Concepts | Exact terms |",
        "|---|---|---|---:|---|---|---|---|",
    ]
    for item in sorted(
        _records(analysis.get("requirements")), key=lambda record: str(record.get("id"))
    ):
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    item.get("id"),
                    item.get("priority"),
                    item.get("category"),
                    item.get("screenable"),
                    item.get("source_id"),
                    item.get("source_location"),
                    item.get("concepts"),
                    item.get("exact_terms"),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Eligibility Results",
            "",
            "| Requirement | Classification | Evidence IDs | True gap |",
            "|---|---|---|---:|",
        ]
    )
    for item in sorted(
        _records(analysis.get("eligibility_results")),
        key=lambda record: str(record.get("requirement_id")),
    ):
        lines.append(
            f"| {cell(item.get('requirement_id'))} | {cell(item.get('classification'))} | "
            f"{cell(item.get('evidence_item_ids'))} | {cell(item.get('true_gap'))} |"
        )

    lines.extend(
        [
            "",
            "## Requirement Evidence Matrix",
            "",
            "| Requirement | Evidence | Candidate facts | Source | Source location binding | Excerpt binding | Status | Level | Resume visibility | Alignment | Action | Confidence |",
            "|---|---|---|---|---|---|---|---:|---|---|---|---|",
        ]
    )
    for item in sorted(
        _records(analysis.get("evidence_items")),
        key=lambda record: (str(record.get("requirement_id")), str(record.get("id"))),
    ):
        excerpt_binding = (
            "NONE"
            if item.get("status") == "absent"
            else "HASH_BOUND_SIDECAR_EXCERPT"
        )
        source_location_binding = (
            "PROTECTED_SIDECAR_VALUE"
            if item.get("source_location") is not None
            else "NONE"
        )
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    item.get("requirement_id"),
                    item.get("id"),
                    item.get("candidate_fact_ids"),
                    item.get("source_id"),
                    source_location_binding,
                    excerpt_binding,
                    item.get("status"),
                    item.get("evidence_level"),
                    item.get("resume_visibility"),
                    item.get("relationship_to_requirement"),
                    item.get("recommended_action"),
                    item.get("confidence"),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Terminology And Revision Plan",
            "",
            "| Alignment | Requirement | Relationship | Evidence IDs | Current term binding | Proposed wording binding | Approved for revision |",
            "|---|---|---|---|---|---|---:|",
        ]
    )
    for item in sorted(
        _records(analysis.get("semantic_alignments")),
        key=lambda record: str(record.get("alignment_id")),
    ):
        current_binding = (
            "PROTECTED_SIDECAR_VALUE" if item.get("candidate_term") is not None else "NONE"
        )
        proposed_binding = (
            "PROTECTED_SIDECAR_VALUE" if item.get("industry_wording") is not None else "NONE"
        )
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    item.get("alignment_id"),
                    item.get("requirement_id"),
                    item.get("relationship"),
                    item.get("evidence_item_ids"),
                    current_binding,
                    proposed_binding,
                    item.get("approved_for_revision"),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Qualification Results",
            "",
            "| Requirement | Classification | Evidence IDs | Confidence |",
            "|---|---|---|---|",
        ]
    )
    for item in sorted(
        _records(analysis.get("qualification_results")),
        key=lambda record: str(record.get("requirement_id")),
    ):
        lines.append(
            f"| {cell(item.get('requirement_id'))} | {cell(item.get('classification'))} | "
            f"{cell(item.get('evidence_item_ids'))} | {cell(item.get('confidence'))} |"
        )

    metrics = analysis.get("metrics") if isinstance(analysis.get("metrics"), dict) else {}
    lines.extend(
        [
            "",
            "## Evidence Coverage",
            "",
            "| Surface | Met / Level 3-4 | Partial / Level 2 | Not found / Level 0-1 | Total |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for label, field in (
        ("Required qualifications", "required_qualifications"),
        ("Preferred qualifications", "preferred_qualifications"),
    ):
        counts = metrics.get(field) if isinstance(metrics.get(field), dict) else {}
        lines.append(
            f"| {label} | {cell(counts.get('met'))} | {cell(counts.get('partial'))} | "
            f"{cell(counts.get('not_found'))} | {cell(counts.get('total'))} |"
        )
    strengths = (
        metrics.get("evidence_strength")
        if isinstance(metrics.get("evidence_strength"), dict)
        else {}
    )
    lines.append(
        f"| Evidence strength | {cell(strengths.get('level_3_4'))} | "
        f"{cell(strengths.get('level_2'))} | {cell(strengths.get('level_0_1'))} | "
        f"{cell(strengths.get('total'))} |"
    )
    lines.extend(
        [
            "",
            f"- Critical missing requirement IDs: `{cell(metrics.get('critical_missing_requirement_ids'))}`",
            "- Opaque overall match percentage: prohibited",
        ]
    )

    lines.extend(
        [
            "",
            "## Gap Report",
            "",
            "| Gap | Requirement | Category | Resolution | Evidence IDs | Action |",
            "|---|---|---|---|---|---|",
        ]
    )
    for item in sorted(
        _records(analysis.get("gaps")), key=lambda record: str(record.get("gap_id"))
    ):
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    item.get("gap_id"),
                    item.get("requirement_id"),
                    item.get("category"),
                    item.get("resolution_status"),
                    item.get("evidence_item_ids"),
                    item.get("recommended_action"),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Gate Results",
            "",
            "| Gate | Name | Enabled | Status | Blocking | Finding count |",
            "|---|---|---:|---|---:|---|",
        ]
    )
    for item in sorted(
        _records(analysis.get("gate_results")), key=lambda record: str(record.get("gate_id"))
    ):
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    item.get("gate_id"),
                    GATE_DISPLAY_NAMES.get(str(item.get("gate_id")), "UNKNOWN"),
                    item.get("enabled"),
                    item.get("status"),
                    item.get("blocking"),
                    len(item.get("findings", []))
                    if isinstance(item.get("findings"), list)
                    else 0,
                )
            )
            + " |"
        )

    lines.extend(["", "## Exact Candidate Audits"])
    ats = audit_record("ats_parse")
    ats_display = dict(ats)
    ats_display["ocr_reason"] = (
        "PROTECTED_SIDECAR_VALUE" if ats.get("ocr_reason") is not None else None
    )
    append_key_value_section(
        "Gate 4 — ATS Extraction",
        ats_display,
        (
            ("Status", "status"),
            ("Resume source", "resume_source_id"),
            ("Resume hash", "resume_hash"),
            ("Actual extraction performed", "actual_extraction_performed"),
            ("Logical order compared", "logical_order_compared"),
            ("Extraction method", "extraction_method"),
            ("OCR used", "ocr_used"),
            ("OCR reason", "ocr_reason"),
            ("Chronology", "chronology"),
            ("Reading order", "reading_order"),
        ),
    )
    lines.extend(
        [
            f"| Critical text loss count | {cell(len(ats.get('critical_text_lost', [])) if isinstance(ats.get('critical_text_lost'), list) else 0)} |",
            f"| Anomaly count | {cell(len(ats.get('anomalies', [])) if isinstance(ats.get('anomalies'), list) else 0)} |",
            "",
            "#### ATS Field Recovery",
            "",
            "| Field | Recovery |",
            "|---|---|",
        ]
    )
    recovery = ats.get("recovery") if isinstance(ats.get("recovery"), dict) else {}
    for field in sorted(recovery):
        lines.append(f"| {cell(field)} | {cell(recovery.get(field))} |")

    append_key_value_section(
        "Gate 5 — AI Recruiter Qualification",
        audit_record("ai_recruiter"),
        (
            ("Status", "status"),
            ("Evaluated resume source", "evaluated_resume_source_id"),
            ("Evaluated resume hash", "evaluated_resume_hash"),
            ("Hidden context used", "hidden_context_used"),
            ("Qualification requirement IDs", "qualification_requirement_ids"),
        ),
    )
    human_recruiter = audit_record("human_recruiter")
    human_recruiter_display = dict(human_recruiter)
    human_recruiter_display["top_capabilities"] = (
        f"{len(human_recruiter.get('top_capabilities', []))} protected values"
        if isinstance(human_recruiter.get("top_capabilities"), list)
        else "—"
    )
    append_key_value_section(
        "Gate 6 — Human Recruiter Scan",
        human_recruiter_display,
        (
            ("Status", "status"),
            ("Evaluated resume source", "evaluated_resume_source_id"),
            ("Evaluated resume hash", "evaluated_resume_hash"),
            ("Rating", "rating"),
            ("Target role recovered", "target_role_recovered"),
            ("Seniority recovered", "seniority_recovered"),
            ("Top capabilities", "top_capabilities"),
            ("Target connection obvious", "target_connection_obvious"),
            ("Wrong identity signal", "wrong_identity_signal"),
            ("Relevant terms visible early", "relevant_terms_visible_early"),
            ("Easy to skim", "easy_to_skim"),
        ),
    )
    top_third = audit_record("top_third")
    top_third_display = dict(top_third)
    top_third_display["top_domains"] = (
        f"{len(top_third.get('top_domains', []))} protected values"
        if isinstance(top_third.get("top_domains"), list)
        else "—"
    )
    append_key_value_section(
        "Gate 6 — Top-Third Scan",
        top_third_display,
        (
            ("Status", "status"),
            ("Evaluated resume source", "evaluated_resume_source_id"),
            ("Evaluated resume hash", "evaluated_resume_hash"),
            ("Rating", "rating"),
            ("Target role represented", "target_role_represented"),
            ("Top domains", "top_domains"),
        ),
    )
    lines.append(
        "| Scientific identity | PROTECTED_SIDECAR_VALUE |"
        if top_third.get("scientific_identity") is not None
        else "| Scientific identity | — |"
    )

    hiring_manager = audit_record("hiring_manager")
    append_key_value_section(
        "Gate 7 — Hiring Manager Review",
        hiring_manager,
        (
            ("Status", "status"),
            ("Evaluated resume source", "evaluated_resume_source_id"),
            ("Evaluated resume hash", "evaluated_resume_hash"),
            ("Rating", "rating"),
            ("Target context", "target_context"),
            ("Technical depth", "technical_depth"),
            ("Ownership clear", "ownership_clear"),
            ("Claims credible", "claims_credible"),
            ("Generic after optimization", "generic_after_optimization"),
        ),
    )
    lines.extend(
        [
            "",
            "#### Hiring Manager Dimensions",
            "",
            "| Dimension | Applicability | Rating | Evidence binding |",
            "|---|---|---|---|",
        ]
    )
    for item in sorted(
        _records(hiring_manager.get("dimension_results")),
        key=lambda record: str(record.get("dimension")),
    ):
        evidence_binding = (
            "PROTECTED_SIDECAR_VALUE" if item.get("evidence") is not None else "NONE"
        )
        lines.append(
            f"| {cell(item.get('dimension'))} | {cell(item.get('applicability'))} | "
            f"{cell(item.get('rating'))} | {evidence_binding} |"
        )

    integrity = audit_record("integrity")
    append_key_value_section(
        "Gate 8 — Integrity Review",
        integrity,
        (
            ("Status", "status"),
            ("Evaluated resume source", "evaluated_resume_source_id"),
            ("Evaluated resume hash", "evaluated_resume_hash"),
            ("Unsupported claim IDs", "unsupported_claim_ids"),
            ("Inflated ownership claim IDs", "inflated_ownership_claim_ids"),
            ("Inflated seniority claim IDs", "inflated_seniority_claim_ids"),
            ("Invented metric claim IDs", "invented_metric_claim_ids"),
            ("Unsupported direct-experience claim IDs", "unsupported_direct_experience_claim_ids"),
            ("Semantic drift claim IDs", "semantic_drift_claim_ids"),
            ("Caveat-loss claim IDs", "caveat_loss_claim_ids"),
            ("Keyword stuffing", "keyword_stuffing"),
        ),
    )
    for label, field in (
        ("JD mimicry concern count", "jd_mimicry_concerns"),
        ("Duplicated-concept finding count", "duplicated_concept_findings"),
        ("Related-vs-direct ambiguity count", "related_vs_direct_ambiguities"),
    ):
        value = integrity.get(field)
        lines.append(f"| {label} | {cell(len(value) if isinstance(value, list) else 0)} |")

    lines.extend(
        [
            "",
            "## Claim Provenance",
            "",
            "| Claim | Revision relationship | Requirements | Candidate facts | Evidence IDs | Support | Represents met | Baseline source |",
            "|---|---|---|---|---|---|---:|---|",
        ]
    )
    for item in sorted(
        _records(analysis.get("claim_provenance")),
        key=lambda record: str(record.get("resume_claim_id")),
    ):
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    item.get("resume_claim_id"),
                    item.get("revision_relationship"),
                    item.get("requirement_ids"),
                    item.get("candidate_fact_ids"),
                    item.get("evidence_item_ids"),
                    item.get("support_status"),
                    item.get("represents_requirement_as_met"),
                    item.get("baseline_resume_source_id"),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Authorized Removals",
            "",
            "| Removal | Requirements | Baseline source | Baseline hash | Authorization verified | Reason binding |",
            "|---|---|---|---|---:|---|",
        ]
    )
    for item in sorted(
        _records(analysis.get("removed_claims")),
        key=lambda record: str(record.get("removal_id")),
    ):
        reason_binding = (
            "PROTECTED_SIDECAR_VALUE" if item.get("reason") is not None else "NONE"
        )
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    item.get("removal_id"),
                    item.get("requirement_ids"),
                    item.get("baseline_resume_source_id"),
                    item.get("baseline_resume_hash"),
                    item.get("authorization_verified"),
                    reason_binding,
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Evaluator Runs",
            "",
            "| Evaluator run | Gate | Status | Attempts | Retries | Failure type |",
            "|---|---|---|---:|---:|---|",
        ]
    )
    for item in sorted(
        _records(analysis.get("evaluator_runs")),
        key=lambda record: str(record.get("evaluator_run_id")),
    ):
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    item.get("evaluator_run_id"),
                    item.get("gate_id"),
                    item.get("status"),
                    item.get("attempt_count"),
                    item.get("retry_count"),
                    item.get("failure_type"),
                )
            )
            + " |"
        )

    config = analysis.get("config") if isinstance(analysis.get("config"), dict) else {}
    lines.extend(
        [
            "",
            "## Revision And Artifact Record",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Revision cycle | {cell(run.get('revision_cycle'))} |",
            f"| Maximum revision cycles | {cell(config.get('max_revision_cycles'))} |",
            f"| Revisions applied | {cell(run.get('revisions_applied'))} |",
            f"| Authorization verified | {cell(run.get('authorization_verified'))} |",
            "",
            "### Output Artifacts",
            "",
            "| Artifact | Path | Format | SHA-256 | Status |",
            "|---|---|---|---|---|",
        ]
    )
    for item in sorted(
        _records(analysis.get("outputs")),
        key=lambda record: str(record.get("artifact_type")),
    ):
        displayed_hash = (
            "<SELF_HASH_NORMALIZED>"
            if item.get("artifact_type") == "MARKDOWN_AUDIT_PACKAGE"
            else item.get("sha256")
        )
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    item.get("artifact_type"),
                    item.get("relative_path"),
                    item.get("format"),
                    displayed_hash,
                    item.get("status"),
                )
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def validate_bundle(analysis: dict[str, Any], bundle_root: Path) -> list[Issue]:
    """Verify on-disk artifacts and bind recorded excerpts to their source text."""

    issues: list[Issue] = []
    try:
        resolved_root = bundle_root.resolve(strict=True)
    except (OSError, RuntimeError):
        return [
            Issue(
                "INDUSTRY_RESUME.BUNDLE_ROOT",
                "ERROR",
                None,
                "bundle root does not exist or cannot be resolved",
            )
        ]
    if not resolved_root.is_dir():
        return [
            Issue(
                "INDUSTRY_RESUME.BUNDLE_ROOT",
                "ERROR",
                None,
                "bundle root must be a directory",
            )
        ]

    sources = {
        source.get("source_id"): source
        for source in _records(analysis.get("sources"))
        if isinstance(source.get("source_id"), str)
    }
    run = analysis.get("run") if isinstance(analysis.get("run"), dict) else {}
    records: list[tuple[str, str, Any, Any, tuple[str, str]]] = []
    for source_id, source in sources.items():
        records.append(
            (
                "source",
                source_id,
                source.get("relative_path"),
                source.get("sha256"),
                ("source", source_id),
            )
        )
        extracted_path = source.get("extracted_text_relative_path")
        extracted_hash = source.get("extracted_text_sha256")
        if (extracted_path is None) != (extracted_hash is None):
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_EXTRACTED_TEXT",
                    "ERROR",
                    None,
                    f"source {source_id!r} must provide both extracted-text path and hash",
                )
            )
        elif extracted_path is not None:
            records.append(
                (
                    "source extracted text",
                    source_id,
                    extracted_path,
                    extracted_hash,
                    ("extracted", source_id),
                )
            )
    for output in _records(analysis.get("outputs")):
        if output.get("status") == "CREATED":
            artifact_type = str(output.get("artifact_type", "UNKNOWN"))
            records.append(
                (
                    "output",
                    artifact_type,
                    output.get("relative_path"),
                    output.get("sha256"),
                    ("output", artifact_type),
                )
            )

    verified_paths: dict[tuple[str, str], Path] = {}
    verified_file_identities: dict[tuple[int, int], list[tuple[str, str]]] = {}
    allowed_current_output_pair = frozenset(
        {
            ("source", str(run.get("current_resume_source_id"))),
            ("output", "FINAL_RESUME"),
        }
    )
    for record_kind, identifier, relative_path, expected_hash, record_key in records:
        if not _is_safe_relative_path(relative_path):
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_PATH",
                    "ERROR",
                    None,
                    f"{record_kind} {identifier!r} does not use a safe relative bundle path",
                )
            )
            continue
        pure = PurePosixPath(relative_path)
        candidate = resolved_root.joinpath(*pure.parts)
        try:
            resolved_candidate = candidate.resolve(strict=True)
        except (FileNotFoundError, OSError, RuntimeError):
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_FILE",
                    "ERROR",
                    None,
                    f"{record_kind} {identifier!r} is missing from the bundle",
                )
            )
            continue
        if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_PATH",
                    "ERROR",
                    None,
                    f"{record_kind} {identifier!r} resolves outside the bundle root",
                )
            )
            continue
        if not resolved_candidate.is_file():
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_FILE",
                    "ERROR",
                    None,
                    f"{record_kind} {identifier!r} is not a regular bundle file",
                )
            )
            continue
        try:
            stat_result = resolved_candidate.stat()
        except OSError:
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_FILE",
                    "ERROR",
                    None,
                    f"{record_kind} {identifier!r} could not be inspected in the bundle",
                )
            )
            continue
        identity = (stat_result.st_dev, stat_result.st_ino)
        existing_keys = verified_file_identities.get(identity, [])
        disallowed_alias = any(
            existing_key != record_key
            and frozenset({existing_key, record_key}) != allowed_current_output_pair
            for existing_key in existing_keys
        )
        if disallowed_alias:
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_PATH",
                    "ERROR",
                    None,
                    f"{record_kind} {identifier!r} resolves to a bundle file already used by another source or output record",
                )
            )
            continue
        verified_file_identities.setdefault(identity, []).append(record_key)
        try:
            actual_hash = _sha256_file(resolved_candidate)
        except OSError:
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_FILE",
                    "ERROR",
                    None,
                    f"{record_kind} {identifier!r} could not be read from the bundle",
                )
            )
            continue
        if actual_hash != expected_hash:
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_HASH",
                    "ERROR",
                    None,
                    f"{record_kind} {identifier!r} hash does not match its bundle file",
                )
            )
            continue
        verified_paths[record_key] = resolved_candidate

    referenced_source_ids = {
        item.get("source_id")
        for item in _records(analysis.get("requirements"))
        if isinstance(item.get("source_id"), str)
    }
    referenced_source_ids.update(
        item.get("source_id")
        for item in _records(analysis.get("evidence_items"))
        if item.get("status") != "absent" and isinstance(item.get("source_id"), str)
    )
    referenced_source_ids.update(
        item.get("source_id")
        for item in _records(analysis.get("candidate_facts"))
        if isinstance(item.get("source_id"), str)
    )
    referenced_source_ids.update(
        item.get("resume_source_id")
        for item in _records(analysis.get("claim_provenance"))
        if isinstance(item.get("resume_source_id"), str)
    )
    referenced_source_ids.update(
        item.get("baseline_resume_source_id")
        for item in _records(analysis.get("claim_provenance"))
        if isinstance(item.get("baseline_resume_source_id"), str)
    )
    referenced_source_ids.update(
        item.get("baseline_resume_source_id")
        for item in _records(analysis.get("removed_claims"))
        if isinstance(item.get("baseline_resume_source_id"), str)
    )
    config = analysis.get("config") if isinstance(analysis.get("config"), dict) else {}
    if run.get("revisions_applied") is True and config.get("ai_ats_mode") is True:
        referenced_source_ids.update(
            source_id
            for source_id, source in sources.items()
            if source.get("source_type") == "BASELINE_RESUME"
            and source.get("content_authority") is True
        )
        current_resume_source_id = run.get("current_resume_source_id")
        if isinstance(current_resume_source_id, str):
            referenced_source_ids.add(current_resume_source_id)

    source_texts: dict[str, str] = {}
    text_suffixes = {".txt", ".md", ".markdown"}
    for source_id in sorted(referenced_source_ids):
        source = sources.get(source_id)
        if source is None:
            continue
        source_path = verified_paths.get(("source", source_id))
        relative_path = source.get("relative_path")
        direct_text = (
            source_path is not None
            and isinstance(relative_path, str)
            and PurePosixPath(relative_path).suffix.lower() in text_suffixes
        )
        text_path = source_path if direct_text else verified_paths.get(("extracted", source_id))
        if text_path is None:
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_EXTRACTED_TEXT",
                    "ERROR",
                    None,
                    f"referenced non-text source {source_id!r} needs verified extracted text",
                )
            )
            continue
        try:
            source_texts[source_id] = text_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_EXTRACTED_TEXT",
                    "ERROR",
                    None,
                    f"text for source {source_id!r} could not be read as UTF-8",
                )
            )

    for requirement in _records(analysis.get("requirements")):
        requirement_id = requirement.get("id")
        source_text = source_texts.get(requirement.get("source_id"))
        excerpt = requirement.get("source_text")
        if source_text is not None and isinstance(excerpt, str) and excerpt not in source_text:
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_REQUIREMENT",
                    "ERROR",
                    requirement_id if isinstance(requirement_id, str) else None,
                    f"requirement {requirement_id!r} source_text is absent from its bound source",
                )
            )

    for evidence in _records(analysis.get("evidence_items")):
        if evidence.get("status") == "absent":
            continue
        evidence_id = evidence.get("id")
        source_text = source_texts.get(evidence.get("source_id"))
        excerpt = evidence.get("source_excerpt")
        if source_text is not None and isinstance(excerpt, str) and excerpt not in source_text:
            requirement_id = evidence.get("requirement_id")
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_EVIDENCE",
                    "ERROR",
                    requirement_id if isinstance(requirement_id, str) else None,
                    f"evidence {evidence_id!r} excerpt is absent from its bound source",
                )
            )

    for fact in _records(analysis.get("candidate_facts")):
        fact_id = fact.get("fact_id")
        source_text = source_texts.get(fact.get("source_id"))
        statement = fact.get("statement")
        if source_text is not None and isinstance(statement, str) and statement not in source_text:
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_CANDIDATE_FACT",
                    "ERROR",
                    None,
                    f"candidate fact {fact_id!r} statement is absent from its authoritative source",
                )
            )

    for claim in _records(analysis.get("claim_provenance")):
        claim_id = claim.get("resume_claim_id")
        source_text = source_texts.get(claim.get("resume_source_id"))
        excerpt = claim.get("resume_excerpt")
        if source_text is not None and isinstance(excerpt, str) and excerpt not in source_text:
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_CLAIM",
                    "ERROR",
                    None,
                    f"claim {claim_id!r} excerpt is absent from its bound resume source",
                )
            )
        relationship = claim.get("revision_relationship")
        if relationship in {"UNCHANGED", "STRENGTHENED"}:
            baseline_text = source_texts.get(claim.get("baseline_resume_source_id"))
            baseline_excerpt = claim.get("baseline_resume_excerpt")
            if (
                baseline_text is not None
                and isinstance(baseline_excerpt, str)
                and baseline_excerpt not in baseline_text
            ):
                issues.append(
                    Issue(
                        "INDUSTRY_RESUME.BUNDLE_CLAIM_BASELINE",
                        "ERROR",
                        None,
                        f"claim {claim_id!r} baseline excerpt is absent from its bound baseline resume",
                    )
                )

    for removal in _records(analysis.get("removed_claims")):
        removal_id = removal.get("removal_id")
        baseline_text = source_texts.get(removal.get("baseline_resume_source_id"))
        baseline_excerpt = removal.get("baseline_excerpt")
        if (
            baseline_text is not None
            and isinstance(baseline_excerpt, str)
            and baseline_excerpt not in baseline_text
        ):
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_CLAIM_BASELINE",
                    "ERROR",
                    None,
                    f"removed claim {removal_id!r} excerpt is absent from its bound baseline resume",
                )
            )

    if run.get("revisions_applied") is True and config.get("ai_ats_mode") is True:
        baseline_ids = [
            source_id
            for source_id, source in sources.items()
            if source.get("source_type") == "BASELINE_RESUME"
            and source.get("content_authority") is True
        ]
        current_id = run.get("current_resume_source_id")
        if len(baseline_ids) == 1 and isinstance(current_id, str):
            baseline_text = source_texts.get(baseline_ids[0])
            current_text = source_texts.get(current_id)
            if baseline_text is not None and current_text is not None:
                def normalize_material_line(raw_line: str) -> str:
                    line = " ".join(raw_line.strip().split())
                    return re.sub(r"^(?:[-*+\u2022]\s+|#{1,6}\s+)", "", line)

                def anchored_material_lines(text: str) -> list[tuple[str, str]]:
                    known_section_headings = {
                        "additional information",
                        "awards",
                        "certifications",
                        "core competencies",
                        "education",
                        "employment history",
                        "experience",
                        "expertise",
                        "honors",
                        "languages",
                        "leadership",
                        "licenses",
                        "objective",
                        "patents",
                        "presentations",
                        "professional experience",
                        "professional profile",
                        "professional summary",
                        "profile",
                        "projects",
                        "publications",
                        "research experience",
                        "selected projects",
                        "skills",
                        "summary",
                        "technical skills",
                        "training",
                        "volunteer experience",
                        "work experience",
                    }

                    def is_bullet(raw_line: str) -> bool:
                        return re.match(r"^\s*[-*+\u2022]\s+", raw_line) is not None

                    def bullet_indent(raw_line: str) -> int | None:
                        match = re.match(r"^([ \t]*)[-*+\u2022]\s+", raw_line)
                        if match is None:
                            return None
                        return len(match.group(1).expandtabs(4))

                    def is_section_heading(raw_line: str, normalized: str) -> bool:
                        canonical = normalized.rstrip(":").casefold()
                        return (
                            re.match(r"^\s*#{1,6}\s+", raw_line) is not None
                            or canonical in known_section_headings
                            or (
                                normalized.endswith(":")
                                and len(normalized) <= 80
                            )
                            or (
                                normalized.isupper()
                                and 1 <= len(normalized.split()) <= 8
                            )
                        )

                    records: list[tuple[str, str]] = []
                    blocks = [
                        [
                            raw_line
                            for raw_line in raw_block.splitlines()
                            if raw_line.strip()
                        ]
                        for raw_block in re.split(r"(?:\r?\n)\s*(?:\r?\n)", text)
                    ]
                    blocks = [raw_lines for raw_lines in blocks if raw_lines]
                    active_section = "__ROOT__"
                    active_anchor = active_section
                    pending_header: list[str] = []
                    bullet_anchors: dict[int, str] = {}
                    for block_index, raw_lines in enumerate(blocks):
                        if not raw_lines:
                            continue
                        normalized = [normalize_material_line(line) for line in raw_lines]
                        first_is_bullet = is_bullet(raw_lines[0])
                        if (
                            not first_is_bullet
                            and is_section_heading(raw_lines[0], normalized[0])
                        ):
                            active_section = normalized[0].rstrip(":").casefold()
                            active_anchor = active_section
                            pending_header = []
                            bullet_anchors = {}
                            records.append(("__STRUCTURE__", normalized[0]))
                            start = 1
                        else:
                            start = 0
                        for index in range(start, len(raw_lines)):
                            line = normalized[index]
                            current_is_bullet = is_bullet(raw_lines[index])
                            next_raw_line = (
                                raw_lines[index + 1]
                                if index + 1 < len(raw_lines)
                                else (
                                    blocks[block_index + 1][0]
                                    if block_index + 1 < len(blocks)
                                    else None
                                )
                            )
                            next_is_bullet = (
                                next_raw_line is not None
                                and is_bullet(next_raw_line)
                            )
                            if current_is_bullet:
                                indent = bullet_indent(raw_lines[index])
                                assert indent is not None
                                for level in [
                                    level for level in bullet_anchors if level >= indent
                                ]:
                                    del bullet_anchors[level]
                                parent_levels = [
                                    level for level in bullet_anchors if level < indent
                                ]
                                parent_anchor = (
                                    bullet_anchors[max(parent_levels)]
                                    if parent_levels
                                    else active_anchor
                                )
                                records.append((parent_anchor, line))
                                next_indent = (
                                    bullet_indent(next_raw_line)
                                    if next_raw_line is not None
                                    else None
                                )
                                if next_indent is not None and next_indent > indent:
                                    bullet_anchors[indent] = (
                                        parent_anchor + "\x1f" + line.casefold()
                                    )
                                pending_header = []
                            else:
                                bullet_anchors = {}
                                records.append((active_section, line))
                                pending_header.append(line.casefold())
                            if pending_header and next_is_bullet:
                                active_anchor = (
                                    active_section
                                    + "\x1f"
                                    + "\x1e".join(pending_header)
                                )
                    return records

                def material_lines(text: str) -> list[str]:
                    return [line for _anchor, line in anchored_material_lines(text)]

                baseline_lines = anchored_material_lines(baseline_text)
                current_lines = anchored_material_lines(current_text)
                added_records: Counter[tuple[str, str]] = Counter()
                deleted_records: Counter[tuple[str, str]] = Counter()
                matcher = difflib.SequenceMatcher(
                    None, baseline_lines, current_lines, autojunk=False
                )
                for tag, before_start, before_end, after_start, after_end in matcher.get_opcodes():
                    if tag in {"replace", "delete"}:
                        deleted_records.update(baseline_lines[before_start:before_end])
                    if tag in {"replace", "insert"}:
                        added_records.update(current_lines[after_start:after_end])
                reordered_within_anchor = added_records & deleted_records
                added_records.subtract(reordered_within_anchor)
                deleted_records.subtract(reordered_within_anchor)
                added_lines: Counter[str] = Counter()
                deleted_lines: Counter[str] = Counter()
                for (_anchor, line), count in (+added_records).items():
                    added_lines[line] += count
                for (_anchor, line), count in (+deleted_records).items():
                    deleted_lines[line] += count

                claim_lines: dict[str, Counter[str]] = {}
                baseline_claim_lines: dict[str, Counter[str]] = {}
                relationships: dict[str, Any] = {}
                for claim in _records(analysis.get("claim_provenance")):
                    claim_id = claim.get("resume_claim_id")
                    excerpt = claim.get("resume_excerpt")
                    if not isinstance(claim_id, str) or not isinstance(excerpt, str):
                        continue
                    claim_lines[claim_id] = Counter(material_lines(excerpt))
                    relationships[claim_id] = claim.get("revision_relationship")
                    baseline_excerpt = claim.get("baseline_resume_excerpt")
                    baseline_claim_lines[claim_id] = (
                        Counter(material_lines(baseline_excerpt))
                        if isinstance(baseline_excerpt, str)
                        else Counter()
                    )

                claim_line_usage: Counter[tuple[str, str]] = Counter()
                used_claims: Counter[str] = Counter()
                for changed_line, occurrence_count in added_lines.items():
                    for _occurrence in range(occurrence_count):
                        covering_claims = sorted(
                            claim_id
                            for claim_id, lines in claim_lines.items()
                            if relationships.get(claim_id) in {"INTRODUCED", "STRENGTHENED"}
                            and claim_line_usage[(claim_id, changed_line)]
                            < lines[changed_line]
                        )
                        if len(covering_claims) == 1:
                            claim_id = covering_claims[0]
                            claim_line_usage[(claim_id, changed_line)] += 1
                            used_claims[claim_id] += 1
                            continue
                        line_fingerprint = hashlib.sha256(
                            changed_line.encode("utf-8")
                        ).hexdigest()[:12]
                        issues.append(
                            Issue(
                                "INDUSTRY_RESUME.CLAIM_COVERAGE",
                                "ERROR",
                                None,
                                "each added or changed current-resume line must map to exactly one claim record; "
                                f"found {len(covering_claims)} for line fingerprint {line_fingerprint}",
                            )
                        )
                for claim_id, relationship in relationships.items():
                    if relationship not in {"INTRODUCED", "STRENGTHENED"}:
                        continue
                    current_material_count = sum(claim_lines.get(claim_id, Counter()).values())
                    if current_material_count != 1:
                        issues.append(
                            Issue(
                                "INDUSTRY_RESUME.CLAIM_COVERAGE",
                                "ERROR",
                                None,
                                f"introduced or strengthened claim {claim_id!r} must bind exactly one material current-resume line",
                            )
                        )
                    if used_claims[claim_id] != 1:
                        issues.append(
                            Issue(
                                "INDUSTRY_RESUME.CLAIM_COVERAGE",
                                "ERROR",
                                None,
                                f"introduced or strengthened claim {claim_id!r} must cover exactly one added or changed current-resume line; found {used_claims[claim_id]}",
                            )
                        )
                    if (
                        relationship == "STRENGTHENED"
                        and sum(baseline_claim_lines.get(claim_id, Counter()).values()) != 1
                    ):
                        issues.append(
                            Issue(
                                "INDUSTRY_RESUME.CLAIM_COVERAGE",
                                "ERROR",
                                None,
                                f"strengthened claim {claim_id!r} must bind exactly one material baseline-resume line",
                            )
                        )

                deleted_coverage: Counter[str] = Counter()
                for claim_id, relationship in relationships.items():
                    if relationship == "STRENGTHENED" and used_claims[claim_id]:
                        deleted_coverage.update(baseline_claim_lines.get(claim_id, Counter()))
                for removal in _records(analysis.get("removed_claims")):
                    excerpt = removal.get("baseline_excerpt")
                    if isinstance(excerpt, str):
                        removal_lines = material_lines(excerpt)
                        if len(removal_lines) != 1:
                            issues.append(
                                Issue(
                                    "INDUSTRY_RESUME.CLAIM_COVERAGE",
                                    "ERROR",
                                    None,
                                    f"authorized removal {removal.get('removal_id')!r} must bind exactly one material baseline-resume line",
                                )
                            )
                        deleted_coverage.update(removal_lines)
                for deleted_line in sorted(set(deleted_lines) | set(deleted_coverage)):
                    if deleted_coverage[deleted_line] != deleted_lines[deleted_line]:
                        line_fingerprint = hashlib.sha256(
                            deleted_line.encode("utf-8")
                        ).hexdigest()[:12]
                        issues.append(
                            Issue(
                                "INDUSTRY_RESUME.CLAIM_COVERAGE",
                                "ERROR",
                                None,
                                "each removed or replaced baseline line must map exactly once to a strengthened or authorized-removal record; "
                                f"coverage {deleted_coverage[deleted_line]} vs {deleted_lines[deleted_line]} for line fingerprint {line_fingerprint}",
                            )
                        )

    audit_path = verified_paths.get(("output", "MARKDOWN_AUDIT_PACKAGE"))
    if audit_path is not None:
        try:
            audit_text = audit_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            issues.append(
                Issue(
                    "INDUSTRY_RESUME.BUNDLE_AUDIT_PACKAGE",
                    "ERROR",
                    None,
                    "MARKDOWN_AUDIT_PACKAGE could not be read as UTF-8 Markdown",
                )
            )
        else:
            if audit_text != build_audit_package(analysis):
                issues.append(
                    Issue(
                        "INDUSTRY_RESUME.BUNDLE_AUDIT_PACKAGE",
                        "ERROR",
                        None,
                        "MARKDOWN_AUDIT_PACKAGE must exactly equal the deterministic privacy-minimized rendering of the structured sidecar",
                    )
                )
            sections = {
                name: _markdown_section(audit_text, pattern)
                for name, pattern in AUDIT_SECTION_PATTERNS.items()
            }
            missing_sections = [
                name for name, content in sections.items() if not content
            ]
            if missing_sections:
                issues.append(
                    Issue(
                        "INDUSTRY_RESUME.BUNDLE_AUDIT_PACKAGE",
                        "ERROR",
                        None,
                        "MARKDOWN_AUDIT_PACKAGE is missing required section headings: "
                        + ", ".join(missing_sections),
                    )
                )
            jd_section = sections.get("job-description analysis") or ""
            matrix_section = sections.get("requirement-to-evidence matrix") or ""
            gate_section = sections.get("gate results") or ""
            missing_tokens: list[str] = []
            requirements = _records(analysis.get("requirements"))
            evidence_items = _records(analysis.get("evidence_items"))
            for requirement in requirements:
                requirement_id = requirement.get("id")
                if not isinstance(requirement_id, str):
                    continue
                if not _has_contract_token(jd_section, requirement_id, "A-Za-z0-9._-"):
                    missing_tokens.append(f"{requirement_id} (job-description section)")
                matrix_lines = [
                    line
                    for line in matrix_section.splitlines()
                    if _has_contract_token(line, requirement_id, "A-Za-z0-9._-")
                ]
                if not matrix_lines:
                    missing_tokens.append(f"{requirement_id} (evidence-matrix row)")
                    continue
                matrix_row = "\n".join(matrix_lines)
                expected_evidence_ids = sorted(
                    item.get("id")
                    for item in evidence_items
                    if item.get("requirement_id") == requirement_id
                    and isinstance(item.get("id"), str)
                )
                if expected_evidence_ids:
                    missing_tokens.extend(
                        f"{requirement_id}/{evidence_id} (evidence-matrix binding)"
                        for evidence_id in expected_evidence_ids
                        if not _has_contract_token(
                            matrix_row, evidence_id, "A-Za-z0-9._-"
                        )
                    )
                elif re.search(
                    r"(?i)\b(?:no\s+evidence|absent|not\s+found)\b", matrix_row
                ) is None:
                    missing_tokens.append(
                        f"{requirement_id} (explicit no-evidence matrix result)"
                    )
            priorities = {
                requirement.get("priority")
                for requirement in requirements
                if requirement.get("priority") in {"required", "preferred"}
            }
            missing_tokens.extend(
                f"{priority} (job-description classification)"
                for priority in sorted(priorities)
                if re.search(rf"(?i)\b{priority}\b", jd_section) is None
            )
            for gate in _records(analysis.get("gate_results")):
                gate_id = gate.get("gate_id")
                if not isinstance(gate_id, str):
                    continue
                gate_number = gate_id.removeprefix("GATE_")
                gate_label = re.compile(
                    rf"(?i)(?<![A-Za-z0-9_])(?:{re.escape(gate_id)}|Gate\s+{re.escape(gate_number)})(?![A-Za-z0-9_])"
                )
                gate_lines = [
                    line for line in gate_section.splitlines() if gate_label.search(line)
                ]
                if not gate_lines:
                    missing_tokens.append(f"{gate_id} (gate-results row)")
                    continue
                gate_row = "\n".join(gate_lines)
                expected_label = GATE_AUDIT_LABEL_PATTERNS.get(gate_id)
                if expected_label is not None and expected_label.search(gate_row) is None:
                    missing_tokens.append(f"{gate_id} (descriptive gate label)")
            gap_surfaces = audit_text
            for gap in _records(analysis.get("gaps")):
                requirement_id = gap.get("requirement_id")
                category = gap.get("category")
                if not isinstance(requirement_id, str) or not isinstance(category, str):
                    continue
                bound_gap_line = any(
                    _has_contract_token(line, requirement_id, "A-Za-z0-9._-")
                    and _has_contract_token(line, category, "A-Z0-9_")
                    for line in gap_surfaces.splitlines()
                )
                if not bound_gap_line:
                    missing_tokens.append(f"{requirement_id}/{category} (gap binding)")
            if missing_tokens:
                issues.append(
                    Issue(
                        "INDUSTRY_RESUME.BUNDLE_AUDIT_PACKAGE",
                        "ERROR",
                        None,
                        "MARKDOWN_AUDIT_PACKAGE is missing required contract IDs/classes: "
                        + ", ".join(missing_tokens),
                    )
                )
    return issues


def build_dashboard(analysis: dict[str, Any]) -> str:
    """Return a privacy-minimized dashboard containing statuses, IDs, counts, and actions."""

    run = analysis.get("run") if isinstance(analysis.get("run"), dict) else {}
    metrics = analysis.get("metrics") if isinstance(analysis.get("metrics"), dict) else {}
    allowed_statuses = {"PASS", "PASS_WITH_WARNINGS", "FAIL", "NOT_RUN"}
    allowed_actions = {
        "keep",
        "clarify",
        "strengthen_wording",
        "move_higher",
        "add_if_true",
        "leave_as_gap",
    }

    def safe_identifier(value: Any) -> str | None:
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]*", value):
            return value
        return None

    def safe_count(value: Any) -> int:
        return value if isinstance(value, int) and value >= 0 else 0

    gates = {
        item.get("gate_id"): item.get("status")
        for item in _records(analysis.get("gate_results"))
        if item.get("gate_id") in GATE_CONFIG and item.get("status") in allowed_statuses
    }
    overall_status = run.get("overall_status")
    if overall_status not in allowed_statuses:
        overall_status = "NOT_RUN"
    lines = [
        "# Industry Resume Audit Summary",
        "",
        f"Overall status: {overall_status}",
        "",
        "## Gate Status",
    ]
    for gate_id in sorted(gates):
        lines.append(f"- {gate_id}: {gates[gate_id]}")
    for label, field in (
        ("Required Qualifications", "required_qualifications"),
        ("Preferred Qualifications", "preferred_qualifications"),
    ):
        counts = metrics.get(field) if isinstance(metrics.get(field), dict) else {}
        lines.extend(
            [
                "",
                f"## {label}",
                f"- MET: {safe_count(counts.get('met'))} / {safe_count(counts.get('total'))}",
                f"- PARTIAL: {safe_count(counts.get('partial'))} / {safe_count(counts.get('total'))}",
                f"- NOT FOUND: {safe_count(counts.get('not_found'))} / {safe_count(counts.get('total'))}",
            ]
        )

    strength = metrics.get("evidence_strength")
    if not isinstance(strength, dict):
        strength = {}
    lines.extend(
        [
            "",
            "## Evidence Strength",
            f"- Level 3-4: {safe_count(strength.get('level_3_4'))} / {safe_count(strength.get('total'))}",
            f"- Level 2: {safe_count(strength.get('level_2'))} / {safe_count(strength.get('total'))}",
            f"- Level 0-1: {safe_count(strength.get('level_0_1'))} / {safe_count(strength.get('total'))}",
        ]
    )

    missing = [
        identifier
        for value in metrics.get("critical_missing_requirement_ids", [])
        if (identifier := safe_identifier(value)) is not None
    ] if isinstance(metrics.get("critical_missing_requirement_ids"), list) else []
    lines.extend(
        [
            "",
            "## Critical Missing Evidence",
            "- " + (", ".join(missing) if missing else "None"),
        ]
    )

    open_gaps: dict[str, list[tuple[str, str, str]]] = {
        "TRUE_GAP": [],
        "RESUME_GAP": [],
        "POSITIONING_GAP": [],
    }
    evidence_by_id = {
        item.get("id"): item
        for item in _records(analysis.get("evidence_items"))
        if safe_identifier(item.get("id")) is not None
    }
    sources_by_id = {
        item.get("source_id"): item
        for item in _records(analysis.get("sources"))
        if safe_identifier(item.get("source_id")) is not None
    }
    requirements = {
        item.get("id"): item
        for item in _records(analysis.get("requirements"))
        if safe_identifier(item.get("id")) is not None
    }
    improvements: list[tuple[int, str, str, str]] = []
    priority_rank = {"required": 0, "preferred": 1, "contextual": 2}
    for gap in _records(analysis.get("gaps")):
        gap_id = safe_identifier(gap.get("gap_id"))
        requirement_id = safe_identifier(gap.get("requirement_id"))
        category = gap.get("category")
        action = gap.get("recommended_action")
        if gap_id is None or requirement_id is None or action not in allowed_actions:
            continue
        if category in open_gaps and gap.get("resolution_status") == "OPEN":
            open_gaps[category].append((gap_id, requirement_id, action))
        if category not in {"RESUME_GAP", "POSITIONING_GAP"}:
            continue
        bound_evidence = [
            evidence_by_id[evidence_id]
            for evidence_id in gap.get("evidence_item_ids", [])
            if evidence_id in evidence_by_id
        ]
        supported = any(
            item.get("relationship_to_requirement") == "DIRECT"
            and isinstance(item.get("evidence_level"), int)
            and item.get("evidence_level") >= 2
            and sources_by_id.get(item.get("source_id"), {}).get(
                "candidate_evidence_allowed"
            )
            is True
            and sources_by_id.get(item.get("source_id"), {}).get("source_type")
            != "JOB_DESCRIPTION"
            and item.get("source_hash")
            == sources_by_id.get(item.get("source_id"), {}).get("sha256")
            for item in bound_evidence
        )
        if supported:
            priority = requirements.get(requirement_id, {}).get("priority")
            improvements.append(
                (priority_rank.get(priority, 3), gap_id, requirement_id, action)
            )

    lines.extend(["", "## Remaining Gaps"])
    for category in ("TRUE_GAP", "RESUME_GAP", "POSITIONING_GAP"):
        records = sorted(open_gaps[category])
        lines.append(f"- {category}: {len(records)}")
        lines.extend(
            f"  - {gap_id} / {requirement_id}: {action}"
            for gap_id, requirement_id, action in records
        )

    lines.extend(["", "## Highest-Priority Supported Improvements"])
    if improvements:
        lines.extend(
            f"- {gap_id} / {requirement_id}: {action}"
            for _, gap_id, requirement_id, action in sorted(improvements)[:5]
        )
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


class _MachineReadableArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        issue = Issue("INPUT.ARGUMENT", "ERROR", None, message)
        raise SystemExit(_emit([issue], input_error=True, check="invocation"))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = _MachineReadableArgumentParser(
        description="Validate an Industry Resume AI/ATS analysis sidecar"
    )
    parser.add_argument("--analysis", type=Path, required=True, help="industry-resume-analysis.json")
    parser.add_argument("--schema", type=Path, help="override the bundled JSON Schema")
    parser.add_argument(
        "--bundle-root",
        type=Path,
        help=(
            "verify source and CREATED-output files under this bundle root; required "
            "for successful AI/ATS RELEASE and SELF_DRIVING cycles"
        ),
    )
    parser.add_argument(
        "--dashboard",
        nargs="?",
        const="-",
        metavar="PATH",
        help="include a privacy-minimized dashboard in stdout, or write it to PATH",
    )
    return parser.parse_args(argv)


def _emit(
    issues: Iterable[Issue],
    *,
    input_error: bool = False,
    check: str = "analysis",
    dashboard: str | None = None,
    dashboard_written: bool = False,
) -> int:
    issue_list = list(issues)
    errors = sum(issue.severity == "ERROR" for issue in issue_list)
    warnings = sum(issue.severity == "WARNING" for issue in issue_list)
    result = "FAIL" if errors else "PASS"
    payload: dict[str, Any] = {
        "check": check,
        "result": result,
        "error_count": errors,
        "warning_count": warnings,
        "issues": [asdict(issue) for issue in issue_list],
        "dashboard_written": dashboard_written,
    }
    if dashboard is not None:
        payload["dashboard"] = dashboard
    print(json.dumps(payload, sort_keys=True))
    print(
        f"Industry Resume {check}: {result} ({errors} error{'s' if errors != 1 else ''}, "
        f"{warnings} warning{'s' if warnings != 1 else ''})",
        file=sys.stderr,
    )
    if input_error:
        return 2
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    schema_path = args.schema or (
        Path(__file__).resolve().parent.parent
        / "schemas"
        / "industry-resume-analysis.schema.json"
    )
    loaded: dict[str, Any] = {}
    input_issues: list[Issue] = []
    for label, path in (("analysis", args.analysis), ("schema", schema_path)):
        try:
            loaded[label] = _load_json(path)
        except FileNotFoundError:
            input_issues.append(
                Issue("INPUT.FILE", "ERROR", None, f"{label} file not found")
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            input_issues.append(
                Issue("INPUT.JSON", "ERROR", None, f"cannot read {label} JSON: {exc}")
            )
    if input_issues:
        return _emit(input_issues, input_error=True)

    analysis = loaded.get("analysis")
    schema = loaded.get("schema")
    if not isinstance(analysis, dict) or not isinstance(schema, dict):
        return _emit(
            [Issue("INPUT.JSON", "ERROR", None, "analysis and schema roots must be objects")],
            input_error=True,
        )

    try:
        issues = IndustryResumeValidator(analysis, schema).run()
        if args.bundle_root is not None:
            issues.extend(validate_bundle(analysis, args.bundle_root))
        else:
            run = analysis.get("run") if isinstance(analysis.get("run"), dict) else {}
            config = (
                analysis.get("config") if isinstance(analysis.get("config"), dict) else {}
            )
            if (
                config.get("ai_ats_mode") is True
                and run.get("operation") in {"RELEASE", "SELF_DRIVING"}
                and run.get("overall_status") in {"PASS", "PASS_WITH_WARNINGS"}
            ):
                issues.append(
                    Issue(
                        "INDUSTRY_RESUME.BUNDLE_ROOT_REQUIRED",
                        "ERROR",
                        None,
                        "successful final AI/ATS cycles require --bundle-root verification",
                    )
                )
        dashboard = build_dashboard(analysis) if args.dashboard is not None else None
    except Exception:  # Fail closed without leaking malformed candidate content.
        issues = [
            Issue(
                "INDUSTRY_RESUME.VALIDATOR",
                "ERROR",
                None,
                "validation could not safely process the supplied analysis",
            )
        ]
        dashboard = None
    dashboard_written = False
    if args.dashboard not in {None, "-"}:
        try:
            Path(args.dashboard).write_text(dashboard or "", encoding="utf-8")
            dashboard_written = True
            dashboard = None
        except (OSError, UnicodeError) as exc:
            return _emit(
                [Issue("INPUT.DASHBOARD", "ERROR", None, f"cannot write dashboard: {exc}")],
                input_error=True,
            )
    return _emit(issues, dashboard=dashboard, dashboard_written=dashboard_written)


if __name__ == "__main__":
    raise SystemExit(main())
