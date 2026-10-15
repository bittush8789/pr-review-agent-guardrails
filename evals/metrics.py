"""Evaluation metric calculation module for review agent quality assessment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from app.schemas.review_finding import ReviewFinding


@dataclass
class MetricSummary:
    """Summary of precision, recall, F1, and error rates."""

    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0
    invalid_comments: int = 0  # Comments on unchanged lines or non-existent files
    total_expected: int = 0
    total_predicted: int = 0

    @property
    def precision(self) -> float:
        total_positive_preds = self.true_positives + self.false_positives
        if total_positive_preds == 0:
            return 1.0 if self.total_expected == 0 else 0.0
        return self.true_positives / total_positive_preds

    @property
    def recall(self) -> float:
        if self.total_expected == 0:
            return 1.0
        return self.true_positives / (self.true_positives + self.false_negatives)

    @property
    def f1_score(self) -> float:
        p = self.precision
        r = self.recall
        if p + r == 0:
            return 0.0
        return (2.0 * p * r) / (p + r)

    @property
    def false_positive_rate(self) -> float:
        total_negatives = self.false_positives + self.true_negatives
        if total_negatives == 0:
            return 0.0
        return self.false_positives / total_negatives

    @property
    def invalid_comment_rate(self) -> float:
        if self.total_predicted == 0:
            return 0.0
        return self.invalid_comments / self.total_predicted

    def to_dict(self) -> dict[str, Any]:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "true_negatives": self.true_negatives,
            "invalid_comments": self.invalid_comments,
            "total_expected": self.total_expected,
            "total_predicted": self.total_predicted,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "invalid_comment_rate": round(self.invalid_comment_rate, 4),
        }


def is_matching_finding(predicted: ReviewFinding, expected: dict[str, Any], line_tolerance: int = 2) -> bool:
    """Evaluate whether a predicted finding matches an expected ground-truth finding.

    Criteria:
    1. File path must match exactly.
    2. Line number must be within line_tolerance window.
    3. Category must match.
    4. Severity must match.
    5. Title keyword (if specified) must be present in predicted title.
    """
    if predicted.file != expected.get("file"):
        return False

    if abs(predicted.line - int(expected.get("line", -999))) > line_tolerance:
        return False

    if predicted.category.value.lower() != str(expected.get("category", "")).lower():
        return False

    if predicted.severity.value.lower() != str(expected.get("severity", "")).lower():
        return False

    keyword = expected.get("title_keyword")
    if keyword and keyword.lower() not in predicted.title.lower():
        return False

    return True


def evaluate_sample_predictions(
    predicted_findings: Sequence[ReviewFinding],
    expected_findings: Sequence[dict[str, Any]],
    valid_changed_lines: dict[str, set[int]],
    is_negative_sample: bool = False,
    line_tolerance: int = 2,
) -> MetricSummary:
    """Calculate metric tallies for a single PR sample."""
    summary = MetricSummary()
    summary.total_expected = len(expected_findings)
    summary.total_predicted = len(predicted_findings)

    # Check for invalid comments (guardrail violation metric)
    for p in predicted_findings:
        if p.file not in valid_changed_lines or p.line not in valid_changed_lines[p.file]:
            summary.invalid_comments += 1

    matched_expected_indices: set[int] = set()

    for p in predicted_findings:
        matched = False
        for idx, exp in enumerate(expected_findings):
            if idx in matched_expected_indices:
                continue
            if is_matching_finding(p, exp, line_tolerance=line_tolerance):
                matched = True
                matched_expected_indices.add(idx)
                summary.true_positives += 1
                break
        if not matched:
            summary.false_positives += 1

    summary.false_negatives = len(expected_findings) - len(matched_expected_indices)

    if is_negative_sample and len(predicted_findings) == 0:
        summary.true_negatives = 1

    return summary


def aggregate_metrics(metrics_list: Sequence[MetricSummary]) -> MetricSummary:
    """Aggregate a sequence of sample MetricSummaries into a single comprehensive metric summary."""
    aggregated = MetricSummary()
    for m in metrics_list:
        aggregated.true_positives += m.true_positives
        aggregated.false_positives += m.false_positives
        aggregated.false_negatives += m.false_negatives
        aggregated.true_negatives += m.true_negatives
        aggregated.invalid_comments += m.invalid_comments
        aggregated.total_expected += m.total_expected
        aggregated.total_predicted += m.total_predicted
    return aggregated
