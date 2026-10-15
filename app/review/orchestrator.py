"""Central review orchestrator implementing the 15-step review pipeline with guardrails."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.config.settings import Settings
from app.github.client import GitHubClient
from app.github.diff_parser import DiffParser, ParsedDiff
from app.github.pull_request import PullRequestService, PullRequestMetadata
from app.github.review_publisher import ReviewPublisher, PublishedComment, StalePullRequestError
from app.guardrails.comment_limiter import CommentLimiter
from app.guardrails.diff_line_validator import DiffLineValidator
from app.guardrails.duplicate_filter import DuplicateFilter
from app.guardrails.schema_validator import SchemaValidator
from app.providers.base import AIReviewProvider, ProviderAPIError
from app.providers.gemini_provider import GeminiProvider
from app.review.finding_merger import FindingMerger
from app.review.prompt_builder import PromptBuilder
from app.review.tracing import traceable
from app.rules.rule_registry import DeterministicRuleRegistry
from app.schemas.review_finding import ReviewFinding

logger = logging.getLogger("pr_review_agent.review.orchestrator")


@dataclass
class ReviewExecutionResult:
    """Sanitized summary of orchestrator execution results."""

    repo: str
    pr_number: int
    head_sha: str
    status: str  # "success", "partial_failure_gemini_skipped", "aborted_stale_pr", "failed"
    deterministic_findings_count: int = 0
    ai_raw_findings_count: int = 0
    ai_schema_valid_count: int = 0
    ai_diff_valid_count: int = 0
    total_candidates_count: int = 0
    final_published_count: int = 0
    published_comments: list[PublishedComment] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "pr_number": self.pr_number,
            "head_sha": self.head_sha,
            "status": self.status,
            "metrics": {
                "deterministic_findings": self.deterministic_findings_count,
                "ai_raw_findings": self.ai_raw_findings_count,
                "ai_schema_valid": self.ai_schema_valid_count,
                "ai_diff_valid": self.ai_diff_valid_count,
                "total_candidates": self.total_candidates_count,
                "final_published": self.final_published_count,
            },
            "published_comments": [
                {"file": c.file, "line": c.line, "title": c.title, "dry_run": c.is_dry_run}
                for c in self.published_comments
            ],
            "error_message": self.error_message,
        }


class ReviewOrchestrator:
    """Coordinates the end-to-end pull request review lifecycle."""

    def __init__(
        self,
        settings: Settings,
        github_client: Optional[GitHubClient] = None,
        ai_provider: Optional[AIReviewProvider] = None,
        rule_registry: Optional[DeterministicRuleRegistry] = None,
    ):
        self.settings = settings
        self.github_client = github_client or GitHubClient(
            token=settings.github_token,
            base_url=settings.github_api_url,
            timeout=settings.request_timeout_seconds,
        )
        self.pr_service = PullRequestService(self.github_client)
        self.diff_parser = DiffParser()
        self.rule_registry = rule_registry or DeterministicRuleRegistry()
        self.prompt_builder = PromptBuilder()
        self.schema_validator = SchemaValidator()
        self.diff_line_validator = DiffLineValidator()
        self.duplicate_filter = DuplicateFilter()
        self.comment_limiter = CommentLimiter(
            max_comments=settings.max_comments_per_pr,
            min_confidence=settings.confidence_threshold,
        )
        self.review_publisher = ReviewPublisher(
            client=self.github_client,
            pr_service=self.pr_service,
            dry_run=settings.dry_run,
        )

        # AI Provider setup (Gemini)
        if ai_provider is not None:
            self.ai_provider: Optional[AIReviewProvider] = ai_provider
        elif settings.gemini_api_key:
            self.ai_provider = GeminiProvider(
                api_key=settings.gemini_api_key,
                model_name=settings.gemini_model,
                timeout_seconds=settings.request_timeout_seconds,
            )
        else:
            logger.warning("GEMINI_API_KEY is not configured. Running in deterministic-only mode.")
            self.ai_provider = None

        self.finding_merger = FindingMerger()

    @traceable(name="pr_review_orchestrator", run_type="chain")
    def run(self) -> ReviewExecutionResult:
        """Execute the 15-step review workflow in strict sequence."""
        repo = self.settings.github_repository
        pr_number = self.settings.pull_request_number

        logger.info("Step 1 & 2: Validated configuration for %s#%d", repo, pr_number)

        # Step 3 & 4: Retrieve PR metadata and record head SHA
        try:
            pr_meta = self.pr_service.get_pull_request(repo, pr_number)
            head_sha = pr_meta.head_sha
            logger.info("Step 3 & 4: Retrieved PR #%d (head SHA: %s)", pr_number, head_sha[:8])
        except Exception as exc:
            logger.error("Failed to retrieve PR metadata: %s", exc)
            return ReviewExecutionResult(
                repo=repo,
                pr_number=pr_number,
                head_sha="unknown",
                status="failed",
                error_message=f"Failed to fetch PR metadata: {exc}",
            )

        # Step 5: Fetch files and parse unified diffs to identify eligible changed lines
        logger.info("Step 5: Fetching files and parsing diffs...")
        changed_files = self.pr_service.get_changed_files(repo, pr_number)
        parsed_diff = self.diff_parser.parse_patches(changed_files)

        total_changed_lines = sum(len(lines) for lines in parsed_diff.valid_changed_lines.values())
        logger.info(
            "Parsed diff: %d files with %d total added/modified lines.",
            len(parsed_diff.valid_changed_lines),
            total_changed_lines,
        )

        # Step 6: Execute deterministic secret and Terraform checks
        logger.info("Step 6: Executing deterministic security checks...")
        deterministic_findings = self.rule_registry.run_all_checks(parsed_diff)

        # Step 7 & 8: Request AI findings with redacted, minimal context
        ai_raw_findings: list[ReviewFinding] = []
        gemini_skipped = False
        gemini_error: Optional[str] = None

        if self.ai_provider is not None:
            logger.info("Step 7 & 8: Preparing prompt and requesting Gemini review...")
            user_prompt = self.prompt_builder.build_user_prompt(
                pr_title=pr_meta.title,
                pr_body=pr_meta.body,
                parsed_diff=parsed_diff,
            )

            try:
                raw_response = self.ai_provider.generate_review(
                    system_instruction=self.prompt_builder.SYSTEM_INSTRUCTION,
                    user_prompt=user_prompt,
                )
                # Step 9: Validate AI response against schema
                logger.info("Step 9: Validating Gemini response against JSON schema...")
                ai_raw_findings = self.schema_validator.validate_raw_response(raw_response)
            except ProviderAPIError as p_err:
                gemini_skipped = True
                gemini_error = f"Gemini API error: {p_err}"
                logger.warning("Gemini review skipped due to API error: %s. Continuing with deterministic checks.", p_err)
            except Exception as u_err:
                gemini_skipped = True
                gemini_error = f"Unexpected Gemini error: {u_err}"
                logger.warning("Unexpected error during Gemini analysis: %s. Continuing with deterministic checks.", u_err)
        else:
            gemini_skipped = True
            logger.info("Gemini provider not configured; skipping AI review step.")

        # Step 10: Validate file paths and changed-line positions for AI findings
        logger.info("Step 10: Validating AI finding file paths and line positions...")
        valid_ai_findings, rejected_ai = self.diff_line_validator.validate_findings(
            ai_raw_findings, parsed_diff
        )

        # Step 11: Merge deterministic and AI findings
        logger.info("Step 11: Merging deterministic and validated AI findings...")
        merged_candidates = self.finding_merger.merge(
            deterministic_findings=deterministic_findings,
            ai_findings=valid_ai_findings,
        )

        # Step 12: Remove duplicates and apply comment limit
        logger.info("Step 12: Deduplicating and applying comment limits...")
        deduplicated = self.duplicate_filter.deduplicate(merged_candidates)
        final_findings = self.comment_limiter.limit_findings(deduplicated)

        # Step 13 & 14: Recheck current PR revision and publish valid inline comments
        logger.info("Step 13 & 14: Verifying revision freshness and publishing review comments...")
        published_records: list[PublishedComment] = []
        try:
            published_records = self.review_publisher.publish_findings(
                repo=repo,
                pr_number=pr_number,
                head_sha=head_sha,
                findings=final_findings,
            )
        except StalePullRequestError as stale_err:
            logger.error("Stale PR revision detected! %s", stale_err)
            return ReviewExecutionResult(
                repo=repo,
                pr_number=pr_number,
                head_sha=head_sha,
                status="aborted_stale_pr",
                deterministic_findings_count=len(deterministic_findings),
                ai_raw_findings_count=len(ai_raw_findings),
                ai_schema_valid_count=len(ai_raw_findings),
                ai_diff_valid_count=len(valid_ai_findings),
                total_candidates_count=len(merged_candidates),
                final_published_count=0,
                published_comments=[],
                error_message=str(stale_err),
            )
        except Exception as pub_err:
            logger.error("Error during comment publishing: %s", pub_err)
            return ReviewExecutionResult(
                repo=repo,
                pr_number=pr_number,
                head_sha=head_sha,
                status="failed",
                deterministic_findings_count=len(deterministic_findings),
                ai_raw_findings_count=len(ai_raw_findings),
                ai_schema_valid_count=len(ai_raw_findings),
                ai_diff_valid_count=len(valid_ai_findings),
                total_candidates_count=len(merged_candidates),
                final_published_count=0,
                published_comments=[],
                error_message=f"Publication failure: {pub_err}",
            )

        # Step 15: Record sanitized execution results
        status = "partial_failure_gemini_skipped" if gemini_skipped and gemini_error else "success"
        result = ReviewExecutionResult(
            repo=repo,
            pr_number=pr_number,
            head_sha=head_sha,
            status=status,
            deterministic_findings_count=len(deterministic_findings),
            ai_raw_findings_count=len(ai_raw_findings),
            ai_schema_valid_count=len(ai_raw_findings),
            ai_diff_valid_count=len(valid_ai_findings),
            total_candidates_count=len(merged_candidates),
            final_published_count=len(published_records),
            published_comments=published_records,
            error_message=gemini_error,
        )

        logger.info(
            "Review execution finished with status '%s'. Published comments: %d.",
            result.status,
            result.final_published_count,
        )
        return result
