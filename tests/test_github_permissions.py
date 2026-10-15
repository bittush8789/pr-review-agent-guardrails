"""Unit tests verifying GitHub least-privilege configurations and architectural restrictions."""

from pathlib import Path
import pytest
from app.github.client import GitHubClient
from app.github.review_publisher import ReviewPublisher


def test_workflow_least_privilege_permissions():
    """Verify that the GitHub Actions workflow grants only read/comment permissions."""
    workflow_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "pr-review.yml"
    assert workflow_path.exists(), "pr-review.yml workflow file missing."

    content = workflow_path.read_text(encoding="utf-8")

    # Assert allowed permissions are present
    assert "contents: read" in content
    assert "pull-requests: write" in content

    # Assert dangerous write/admin permissions are strictly absent
    forbidden_permissions = [
        "contents: write",
        "actions: write",
        "administration: write",
        "security-events: write",
        "packages: write",
        "deployments: write",
        "pull_request_target",  # Must not use privileged checkout of untrusted PR code
    ]
    for perm in forbidden_permissions:
        assert perm not in content, f"Workflow contains forbidden permission or trigger: '{perm}'"


def test_github_client_lacks_merging_capabilities():
    """Verify that GitHubClient does not expose methods to merge, close, or push commits."""
    client_methods = [m for m in dir(GitHubClient) if not m.startswith("_")]
    dangerous_actions = ["merge", "approve", "push", "close_pr", "delete_branch", "create_commit"]
    for action in dangerous_actions:
        assert not any(action in m.lower() for m in client_methods), (
            f"GitHubClient must not expose merging or code-writing method: '{action}'"
        )


def test_review_publisher_lacks_code_modification_capabilities():
    """Verify that ReviewPublisher cannot alter repository code or merge PRs."""
    pub_methods = [m for m in dir(ReviewPublisher) if not m.startswith("_")]
    dangerous_actions = ["merge", "commit", "push", "approve"]
    for action in dangerous_actions:
        assert not any(action in m.lower() for m in pub_methods), (
            f"ReviewPublisher must not expose code-altering method: '{action}'"
        )
