"""Review publisher with stale PR detection and inline comment delivery."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.github.client import GitHubClient, GitHubAPIError
from app.github.pull_request import PullRequestService
from app.schemas.review_finding import ReviewFinding

logger = logging.getLogger("pr_review_agent.github.review_publisher")


class StalePullRequestError(RuntimeError):
    """Raised when the PR head SHA has changed since analysis started."""
    pass


@dataclass(frozen=True)
class PublishedComment:
    """Record of a published or simulated inline comment."""

    file: str
    line: int
    title: str
    comment_id: Optional[int]
    is_dry_run: bool


class ReviewPublisher:
    """Publishes validated review findings to GitHub Pull Requests."""

    def __init__(
        self,
        client: GitHubClient,
        pr_service: PullRequestService,
        dry_run: bool = False,
    ):
        self.client = client
        self.pr_service = pr_service
        self.dry_run = dry_run

    def verify_revision_freshness(self, repo: str, pr_number: int, expected_head_sha: str) -> bool:
        """Verify that the PR head SHA matches the revision analyzed.

        Args:
            repo: Repository in 'owner/repo' format.
            pr_number: Pull request number.
            expected_head_sha: The SHA recorded at start of analysis.

        Returns:
            True if fresh, raises StalePullRequestError otherwise.

        Raises:
            StalePullRequestError: If head SHA has changed.
        """
        current_sha = self.pr_service.get_head_sha(repo, pr_number)
        if current_sha != expected_head_sha:
            raise StalePullRequestError(
                f"PR head revision has changed during analysis! Expected {expected_head_sha[:8]}, "
                f"found {current_sha[:8]}. Aborting publication to avoid posting on stale code."
            )
        return True

    def publish_findings(
        self,
        repo: str,
        pr_number: int,
        head_sha: str,
        findings: list[ReviewFinding],
    ) -> list[PublishedComment]:
        """Publish a list of validated findings as inline review comments.

        Args:
            repo: Repository in 'owner/repo' format.
            pr_number: Pull request number.
            head_sha: Expected head commit SHA.
            findings: List of validated findings (already filtered and limited).

        Returns:
            List of PublishedComment instances.

        Raises:
            StalePullRequestError: If PR revision changed before publishing.
        """
        if not findings:
            logger.info("No findings to publish for %s#%d.", repo, pr_number)
            return []

        # Stale PR guardrail check
        self.verify_revision_freshness(repo, pr_number, head_sha)

        published: list[PublishedComment] = []
        endpoint = f"/repos/{repo}/pulls/{pr_number}/comments"

        for finding in findings:
            markdown_body = finding.format_markdown_comment()

            if self.dry_run:
                logger.info(
                    "[DRY RUN] Would publish comment on %s#%d at %s:%d: %s",
                    repo,
                    pr_number,
                    finding.file,
                    finding.line,
                    finding.title,
                )
                published.append(
                    PublishedComment(
                        file=finding.file,
                        line=finding.line,
                        title=finding.title,
                        comment_id=None,
                        is_dry_run=True,
                    )
                )
                continue

            payload = {
                "body": markdown_body,
                "commit_id": head_sha,
                "path": finding.file,
                "line": finding.line,
                "side": "RIGHT",
            }

            try:
                logger.info("Publishing inline comment on %s:%d...", finding.file, finding.line)
                res = self.client.post(endpoint, json_data=payload)
                comment_id = res.get("id")
                published.append(
                    PublishedComment(
                        file=finding.file,
                        line=finding.line,
                        title=finding.title,
                        comment_id=comment_id,
                        is_dry_run=False,
                    )
                )
            except GitHubAPIError as err:
                # If GitHub returns 422 (e.g. line position not part of PR diff anymore), log safely
                logger.error(
                    "Failed to publish inline comment on %s:%d (%s): %s",
                    finding.file,
                    finding.line,
                    finding.title,
                    err,
                )

        logger.info(
            "Successfully processed %d/%d review comments for %s#%d.",
            len(published),
            len(findings),
            repo,
            pr_number,
        )
        return published

    def publish_executive_summary(
        self,
        repo: str,
        pr_number: int,
        summary_markdown: str,
    ) -> Optional[int]:
        """Publish a top-level executive summary comment to the PR conversation thread.

        Args:
            repo: Repository in 'owner/repo' format.
            pr_number: Pull request number.
            summary_markdown: Formatted markdown content.

        Returns:
            Comment ID if published, None if dry-run or on failure.
        """
        if self.dry_run:
            logger.info(
                "[DRY RUN] Would publish executive summary to PR #%d on %s:\n%s...",
                pr_number,
                repo,
                summary_markdown[:250].replace("\n", " "),
            )
            return None

        endpoint = f"/repos/{repo}/issues/{pr_number}/comments"
        payload = {"body": summary_markdown}

        try:
            logger.info("Publishing PR Executive Summary to conversation thread for %s#%d...", repo, pr_number)
            res = self.client.post(endpoint, json_data=payload)
            comment_id = res.get("id")
            logger.info("Published PR Executive Summary (comment id: %s) for %s#%d.", comment_id, repo, pr_number)
            return comment_id
        except GitHubAPIError as err:
            logger.error("Failed to post PR Executive Summary to %s#%d: %s", repo, pr_number, err)
            return None
