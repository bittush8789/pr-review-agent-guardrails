"""Evaluation runner evaluating review agent accuracy against labelled PR dataset."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Optional

from app.github.diff_parser import DiffParser
from app.github.pull_request import FilePatch
from app.guardrails.diff_line_validator import DiffLineValidator
from app.guardrails.schema_validator import SchemaValidator
from app.providers.base import AIReviewProvider
from app.providers.gemini_provider import GeminiProvider
from app.review.prompt_builder import PromptBuilder
from app.rules.rule_registry import DeterministicRuleRegistry
from app.schemas.review_finding import ReviewFinding
from evals.metrics import (
    MetricSummary,
    evaluate_sample_predictions,
    aggregate_metrics,
)

logger = logging.getLogger("evals.evaluator")


class EvaluationRunner:
    """Executes evaluation benchmarks against labelled PR datasets."""

    def __init__(
        self,
        dataset_path: Path,
        ai_provider: Optional[AIReviewProvider] = None,
        line_tolerance: int = 2,
    ):
        self.dataset_path = dataset_path
        self.ai_provider = ai_provider
        self.line_tolerance = line_tolerance

        self.diff_parser = DiffParser()
        self.rule_registry = DeterministicRuleRegistry()
        self.schema_validator = SchemaValidator()
        self.diff_line_validator = DiffLineValidator()
        self.prompt_builder = PromptBuilder()

    def load_dataset(self) -> list[dict[str, Any]]:
        """Load labelled dataset from JSON file."""
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Labelled dataset file not found at: {self.dataset_path}")
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    def evaluate(self, run_ai: bool = False) -> dict[str, Any]:
        """Run evaluation benchmark across all dataset samples.

        Args:
            run_ai: Whether to invoke the AI provider for generative findings in addition to deterministic rules.

        Returns:
            Dictionary containing individual sample results and aggregated metrics.
        """
        samples = self.load_dataset()
        deterministic_metrics_list: list[MetricSummary] = []
        combined_metrics_list: list[MetricSummary] = []
        sample_results: list[dict[str, Any]] = []

        for sample in samples:
            sample_id = sample["id"]
            expected = sample.get("expected_findings", [])
            is_neg = not sample.get("expected_to_flag", False)

            # Convert file dicts to FilePatch objects
            patches = [
                FilePatch(
                    filename=f["filename"],
                    status=f.get("status", "modified"),
                    additions=1,
                    deletions=0,
                    patch=f.get("patch"),
                )
                for f in sample.get("files", [])
            ]

            parsed_diff = self.diff_parser.parse_patches(patches)

            # 1. Evaluate Deterministic Rules Alone
            det_findings = self.rule_registry.run_all_checks(parsed_diff)
            det_metrics = evaluate_sample_predictions(
                predicted_findings=det_findings,
                expected_findings=expected,
                valid_changed_lines=parsed_diff.valid_changed_lines,
                is_negative_sample=is_neg,
                line_tolerance=self.line_tolerance,
            )
            deterministic_metrics_list.append(det_metrics)

            # 2. Evaluate Combined (Deterministic + AI) if requested
            ai_valid_findings: list[ReviewFinding] = []
            if run_ai and self.ai_provider is not None:
                user_prompt = self.prompt_builder.build_user_prompt(
                    pr_title=sample.get("title", ""),
                    pr_body=sample.get("description", ""),
                    parsed_diff=parsed_diff,
                )
                try:
                    raw_response = self.ai_provider.generate_review(
                        system_instruction=self.prompt_builder.SYSTEM_INSTRUCTION,
                        user_prompt=user_prompt,
                    )
                    raw_ai_findings = self.schema_validator.validate_raw_response(raw_response)
                    ai_valid_findings, _ = self.diff_line_validator.validate_findings(
                        raw_ai_findings, parsed_diff
                    )
                except Exception as exc:
                    logger.warning("Sample %s AI review failed: %s", sample_id, exc)

            combined_findings = list(det_findings) + ai_valid_findings
            comb_metrics = evaluate_sample_predictions(
                predicted_findings=combined_findings,
                expected_findings=expected,
                valid_changed_lines=parsed_diff.valid_changed_lines,
                is_negative_sample=is_neg,
                line_tolerance=self.line_tolerance,
            )
            combined_metrics_list.append(comb_metrics)

            sample_results.append({
                "id": sample_id,
                "title": sample.get("title"),
                "expected_count": len(expected),
                "deterministic_predicted": len(det_findings),
                "combined_predicted": len(combined_findings),
                "deterministic_metrics": det_metrics.to_dict(),
                "combined_metrics": comb_metrics.to_dict(),
            })

        overall_det = aggregate_metrics(deterministic_metrics_list)
        overall_comb = aggregate_metrics(combined_metrics_list)

        return {
            "total_samples": len(samples),
            "deterministic_summary": overall_det.to_dict(),
            "combined_summary": overall_comb.to_dict(),
            "sample_details": sample_results,
        }


def format_report_table(results: dict[str, Any]) -> str:
    """Format evaluation benchmark metrics into readable Markdown tables."""
    det = results["deterministic_summary"]
    comb = results["combined_summary"]

    lines = [
        "# Evaluation Benchmark Results",
        f"Total Samples Evaluated: {results['total_samples']}\n",
        "## Overall Performance Summary\n",
        "| Metric | Deterministic Rules Only | Combined (Rules + AI) |",
        "| :--- | :--- | :--- |",
        f"| **Precision** | {det['precision']:.2%} | {comb['precision']:.2%} |",
        f"| **Recall** | {det['recall']:.2%} | {comb['recall']:.2%} |",
        f"| **F1 Score** | {det['f1_score']:.2%} | {comb['f1_score']:.2%} |",
        f"| **False Positive Rate** | {det['false_positive_rate']:.2%} | {comb['false_positive_rate']:.2%} |",
        f"| **Invalid Comment Rate** | {det['invalid_comment_rate']:.2%} | {comb['invalid_comment_rate']:.2%} |",
        f"| **True Positives** | {det['true_positives']} | {comb['true_positives']} |",
        f"| **False Positives** | {det['false_positives']} | {comb['false_positives']} |",
        f"| **False Negatives** | {det['false_negatives']} | {comb['false_negatives']} |",
        f"| **Total Expected** | {det['total_expected']} | {comb['total_expected']} |",
        f"| **Total Predicted** | {det['total_predicted']} | {comb['total_predicted']} |",
        "\n## Sample-Level Details\n",
        "| Sample ID | Expected | Det Pred | Comb Pred | Det F1 | Comb F1 |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ]

    for s in results["sample_details"]:
        d_f1 = s["deterministic_metrics"]["f1_score"]
        c_f1 = s["combined_metrics"]["f1_score"]
        lines.append(
            f"| {s['id']} | {s['expected_count']} | {s['deterministic_predicted']} | "
            f"{s['combined_predicted']} | {d_f1:.2f} | {c_f1:.2f} |"
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run review agent evaluation benchmark.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).parent / "datasets" / "labelled_prs.json",
        help="Path to labelled PRs JSON dataset.",
    )
    parser.add_argument(
        "--run-ai",
        action="store_true",
        help="Include Gemini AI provider evaluation (requires GEMINI_API_KEY).",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional path to save JSON results.",
    )
    args = parser.parse_args()

    runner = EvaluationRunner(dataset_path=args.dataset)
    results = runner.evaluate(run_ai=args.run_ai)
    report = format_report_table(results)
    print(report)

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved raw JSON metrics to {args.output_json}")


if __name__ == "__main__":
    main()
