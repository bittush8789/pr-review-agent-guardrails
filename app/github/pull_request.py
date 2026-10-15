"""Pull Request service for retrieving PR metadata, diffs, and head revision SHAs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.github.client import GitHubClient, GitHubAPIError

logger = logging.getLogger("pr_review_agent.github.pull_request")


@dataclass(frozen=True)
class PullRequestMetadata:
    """Metadata describing a pull request."""

    number: int
    title: str
    body: Optional[str]
    head_sha: str
    base_sha: str
    state: str
    is_draft: bool
    repo_full_name: str


@dataclass(frozen=True)
class FilePatch:
    """Represents a changed file within a pull request."""

    filename: str
    status: str  # "added", "modified", "deleted", "renamed"
    additions: int
    deletions: int
    patch: Optional[str] = None
    previous_filename: Optional[str] = None

    @property
    def has_patch(self) -> bool:
        """Indicates whether a unified diff patch is present."""
        return bool(self.patch and self.patch.strip())


class PullRequestService:
    """Service to interact with GitHub Pull Request REST endpoints."""

    def __init__(self, client: GitHubClient):
        self.client = client

    def get_pull_request(self, repo: str, pr_number: int) -> PullRequestMetadata:
        """Fetch PR metadata including title, state, and head SHA.

        Args:
            repo: Repository in 'owner/repo' format.
            pr_number: Pull request number.

        Returns:
            PullRequestMetadata object.

        Raises:
            GitHubAPIError: If the pull request cannot be fetched.
        """
        endpoint = f"/repos/{repo}/pulls/{pr_number}"
        logger.debug("Fetching PR metadata from %s", endpoint)
        data = self.client.get(endpoint)

        return PullRequestMetadata(
            number=data["number"],
            title=data.get("title", ""),
            body=data.get("body"),
            head_sha=data["head"]["sha"],
            base_sha=data["base"]["sha"],
            state=data.get("state", "open"),
            is_draft=data.get("draft", False),
            repo_full_name=repo,
        )

    def get_head_sha(self, repo: str, pr_number: int) -> str:
        """Retrieve current head SHA directly from PR metadata.

        Args:
            repo: Repository in 'owner/repo' format.
            pr_number: Pull request number.

        Returns:
            Current 40-character commit SHA string.
        """
        pr = self.get_pull_request(repo, pr_number)
        return pr.head_sha

    def get_changed_files(self, repo: str, pr_number: int) -> list[FilePatch]:
        """Fetch all changed files and patches for the PR with pagination.

        Args:
            repo: Repository in 'owner/repo' format.
            pr_number: Pull request number.

        Returns:
            List of FilePatch objects representing changed files.
        """
        files: list[FilePatch] = []
        page = 1
        per_page = 100

        while True:
            endpoint = f"/repos/{repo}/pulls/{pr_number}/files"
            params = {"page": page, "per_page": per_page}
            logger.debug("Fetching PR files page %d for %s#%d", page, repo, pr_number)

            batch = self.client.get(endpoint, params=params)
            if not isinstance(batch, list) or not batch:
                break

            for item in batch:
                patch_obj = FilePatch(
                    filename=item["filename"],
                    status=item.get("status", "modified"),
                    additions=item.get("additions", 0),
                    deletions=item.get("deletions", 0),
                    patch=item.get("patch"),
                    previous_filename=item.get("previous_filename"),
                )
                files.append(patch_obj)

            if len(batch) < per_page:
                break

            page += 1

        logger.info("Retrieved %d changed files for %s#%d", len(files), repo, pr_number)
        return files
