"""Severity utilities and metrics calculations for review findings."""

from __future__ import annotations

from typing import Sequence
from app.schemas.review_finding import ReviewFinding, SeverityLevel


class SeverityComparator:
    """Helper for ordering and comparing severity levels."""

    @staticmethod
    def is_at_least(severity: SeverityLevel, minimum: SeverityLevel) -> bool:
        """Check if a severity meets or exceeds a minimum threshold."""
        return severity.rank >= minimum.rank

    @staticmethod
    def max_severity(severities: Sequence[SeverityLevel]) -> SeverityLevel:
        """Return the highest severity among the given sequence."""
        if not severities:
            return SeverityLevel.LOW
        return max(severities, key=lambda s: s.rank)


def calculate_severity_metrics(findings: Sequence[ReviewFinding]) -> dict[str, int]:
    """Calculate the distribution of findings across severity levels.

    Args:
        findings: Sequence of ReviewFinding instances.

    Returns:
        Mapping of severity names to finding counts.
    """
    counts = {
        SeverityLevel.CRITICAL.value: 0,
        SeverityLevel.HIGH.value: 0,
        SeverityLevel.MEDIUM.value: 0,
        SeverityLevel.LOW.value: 0,
    }
    for f in findings:
        counts[f.severity.value] += 1
    return counts
