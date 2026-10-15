"""Deduplication filter for merging overlapping or duplicate findings."""

from __future__ import annotations

import logging
from typing import Sequence

from app.schemas.review_finding import ReviewFinding

logger = logging.getLogger("pr_review_agent.guardrails.duplicate_filter")


class DuplicateFilter:
    """Removes duplicate or substantially overlapping review findings."""

    @staticmethod
    def _titles_overlap(title1: str, title2: str) -> bool:
        """Check if two finding titles share significant token overlap."""
        tokens1 = set(title1.lower().split())
        tokens2 = set(title2.lower().split())
        if not tokens1 or not tokens2:
            return False
        intersection = tokens1 & tokens2
        overlap_ratio = len(intersection) / min(len(tokens1), len(tokens2))
        return overlap_ratio >= 0.60

    def deduplicate(self, findings: Sequence[ReviewFinding]) -> list[ReviewFinding]:
        """Filter out duplicates, prioritizing deterministic checks and higher severity.

        Args:
            findings: Input sequence of findings.

        Returns:
            Deduplicated list of ReviewFinding objects.
        """
        if not findings:
            return []

        # Sort so that higher severity, higher confidence, and deterministic findings come first
        def priority_key(f: ReviewFinding):
            is_deterministic = 1 if f.source.startswith("deterministic") else 0
            return (
                f.severity.rank,
                is_deterministic,
                f.confidence,
            )

        sorted_candidates = sorted(findings, key=priority_key, reverse=True)
        unique_findings: list[ReviewFinding] = []

        for candidate in sorted_candidates:
            is_duplicate = False
            for existing in unique_findings:
                if candidate.file != existing.file:
                    continue

                # Same file and exact same line: clear duplicate
                if candidate.line == existing.line:
                    is_duplicate = True
                    break

                # Adjacent line (within 1 line) with same category and overlapping title
                if abs(candidate.line - existing.line) <= 1:
                    if candidate.category == existing.category:
                        if self._titles_overlap(candidate.title, existing.title):
                            is_duplicate = True
                            break

            if not is_duplicate:
                unique_findings.append(candidate)
            else:
                logger.debug(
                    "Filtered duplicate finding on %s:%d: '%s'",
                    candidate.file,
                    candidate.line,
                    candidate.title,
                )

        logger.info(
            "Deduplication complete: %d findings retained from %d candidates.",
            len(unique_findings),
            len(findings),
        )
        return unique_findings
