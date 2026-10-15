"""Comment limiter enforcing maximum inline comments and confidence thresholds."""

from __future__ import annotations

import logging
from typing import Sequence

from app.schemas.review_finding import ReviewFinding

logger = logging.getLogger("pr_review_agent.guardrails.comment_limiter")


class CommentLimiter:
    """Enforces strict upper bounds on review comments and filters low-confidence items."""

    def __init__(self, max_comments: int = 5, min_confidence: float = 0.70):
        if max_comments < 1:
            raise ValueError(f"max_comments must be >= 1, got {max_comments}")
        if not (0.0 <= min_confidence <= 1.0):
            raise ValueError(f"min_confidence must be between 0.0 and 1.0, got {min_confidence}")

        self.max_comments = max_comments
        self.min_confidence = min_confidence

    def limit_findings(self, findings: Sequence[ReviewFinding]) -> list[ReviewFinding]:
        """Filter by confidence and truncate to the highest-priority findings.

        Args:
            findings: Sequence of candidate findings.

        Returns:
            List of at most `max_comments` findings.
        """
        if not findings:
            return []

        # Filter out findings below confidence threshold
        confident_findings = [
            f for f in findings if f.confidence >= self.min_confidence
        ]

        if len(confident_findings) < len(findings):
            logger.info(
                "Filtered out %d findings below confidence threshold %.2f.",
                len(findings) - len(confident_findings),
                self.min_confidence,
            )

        # Prioritize:
        # 1. Severity rank (critical > high > medium > low)
        # 2. Confidence (higher first)
        # 3. Source (deterministic checks over purely generative findings)
        def sorting_key(f: ReviewFinding):
            is_deterministic = 1 if f.source.startswith("deterministic") else 0
            return (
                f.severity.rank,
                f.confidence,
                is_deterministic,
            )

        sorted_findings = sorted(confident_findings, key=sorting_key, reverse=True)
        limited = sorted_findings[: self.max_comments]

        logger.info(
            "Comment limiter applied: retained %d/%d findings (limit: %d).",
            len(limited),
            len(findings),
            self.max_comments,
        )
        return limited
