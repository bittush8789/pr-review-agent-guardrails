"""Data models and JSON schemas for review findings."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Literal, Optional


class SeverityLevel(str, Enum):
    """Normalized severity levels in descending order of urgency."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        """Numeric rank for sorting: critical (4) > high (3) > medium (2) > low (1)."""
        ranks = {
            SeverityLevel.CRITICAL: 4,
            SeverityLevel.HIGH: 3,
            SeverityLevel.MEDIUM: 2,
            SeverityLevel.LOW: 1,
        }
        return ranks[self]


class ReviewCategory(str, Enum):
    """Allowed review finding categories."""
    SECURITY = "security"
    TESTING = "testing"
    CORRECTNESS = "correctness"
    INFRASTRUCTURE = "infrastructure"
    MAINTAINABILITY = "maintainability"


SINGLE_FINDING_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["file", "line", "severity", "category", "title", "suggestion", "confidence"],
    "properties": {
        "file": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500,
            "description": "Relative path to the changed file in the repository.",
        },
        "line": {
            "type": "integer",
            "minimum": 1,
            "description": "Target line number in the new version of the file.",
        },
        "severity": {
            "type": "string",
            "enum": ["critical", "high", "medium", "low"],
            "description": "Severity assessment of the issue.",
        },
        "category": {
            "type": "string",
            "enum": ["security", "testing", "correctness", "infrastructure", "maintainability"],
            "description": "Category classifying the nature of the issue.",
        },
        "title": {
            "type": "string",
            "minLength": 3,
            "maxLength": 200,
            "description": "Concise summary of the finding.",
        },
        "suggestion": {
            "type": "string",
            "minLength": 5,
            "maxLength": 2000,
            "description": "Actionable guidance or code example explaining how to resolve the issue.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Model confidence score between 0.0 and 1.0.",
        },
    },
    "additionalProperties": False,
}

REVIEW_FINDINGS_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ReviewFindingsBatch",
    "type": "object",
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": SINGLE_FINDING_JSON_SCHEMA,
            "description": "List of validated review findings.",
        }
    },
    "additionalProperties": False,
}


@dataclass
class ReviewFinding:
    """Represents a validated, actionable code review finding."""

    file: str
    line: int
    severity: SeverityLevel
    category: ReviewCategory
    title: str
    suggestion: str
    confidence: float
    source: str = "ai"  # "deterministic:secret_scanner", "deterministic:terraform_risk", "gemini"
    rule_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert finding to standard dictionary format matching schema."""
        return {
            "file": self.file,
            "line": self.line,
            "severity": self.severity.value,
            "category": self.category.value,
            "title": self.title,
            "suggestion": self.suggestion,
            "confidence": round(self.confidence, 4),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: str = "ai", rule_id: Optional[str] = None) -> ReviewFinding:
        """Construct finding instance from validated dictionary."""
        return cls(
            file=str(data["file"]).strip(),
            line=int(data["line"]),
            severity=SeverityLevel(str(data["severity"]).lower()),
            category=ReviewCategory(str(data["category"]).lower()),
            title=str(data["title"]).strip(),
            suggestion=str(data["suggestion"]).strip(),
            confidence=float(data["confidence"]),
            source=source,
            rule_id=rule_id,
        )

    def format_markdown_comment(self) -> str:
        """Format the finding as a clear, professional GitHub inline review comment."""
        severity_icons = {
            SeverityLevel.CRITICAL: "🚨 **CRITICAL**",
            SeverityLevel.HIGH: "⚠️ **HIGH**",
            SeverityLevel.MEDIUM: "🔍 **MEDIUM**",
            SeverityLevel.LOW: "ℹ️ **LOW**",
        }
        badge = severity_icons.get(self.severity, "**NOTICE**")
        source_note = f" *(Identified by {self.source})*" if self.source != "gemini" else ""

        return (
            f"### {badge}: {self.title}{source_note}\n\n"
            f"**Category:** `{self.category.value}` | **Confidence:** `{self.confidence:.0%}`\n\n"
            f"{self.suggestion}\n\n"
            f"---\n"
            f"*Automated review by GitHub PR-Review Agent with Guardrails. "
            f"Please verify before merging.*"
        )
