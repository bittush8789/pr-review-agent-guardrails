"""Unit tests for review orchestrator with mocked external integrations."""

import json
from unittest.mock import MagicMock, patch
import pytest

from app.config.settings import Settings
from app.github.pull_request import PullRequestMetadata, FilePatch
from app.github.review_publisher import StalePullRequestError
from app.providers.base import AIReviewProvider, ProviderAPIError
from app.review.orchestrator import ReviewOrchestrator


@pytest.fixture
def mock_settings():
    return Settings(
        github_token="ghp_test123456789012345678901234567890",
        gemini_api_key="AIzaSyTestKey00000000000000000000000",
        gemini_model="gemini-3.8-flash",
        github_repository="test-org/test-repo",
        pull_request_number=42,
        max_comments_per_pr=5,
        confidence_threshold=0.70,
        dry_run=True,
    )


class MockAIProvider(AIReviewProvider):
    def __init__(self, response_text: str = '{"findings": []}', should_fail: bool = False):
        self.response_text = response_text
        self.should_fail = should_fail
        self.call_count = 0

    def generate_review(self, system_instruction: str, user_prompt: str) -> str:
        self.call_count += 1
        if self.should_fail:
            raise ProviderAPIError("Simulated Gemini API timeout or rate limit.")
        return self.response_text


def test_orchestrator_successful_flow(mock_settings):
    ai_response = json.dumps({
        "findings": [
            {
                "file": "src/logic.py",
                "line": 12,
                "severity": "high",
                "category": "correctness",
                "title": "Off-by-one error",
                "suggestion": "Adjust loop bounds to include upper limit.",
                "confidence": 0.92,
            }
        ]
    })
    mock_provider = MockAIProvider(response_text=ai_response)

    orchestrator = ReviewOrchestrator(
        settings=mock_settings,
        ai_provider=mock_provider,
    )

    # Mock PR service responses
    orchestrator.pr_service.get_pull_request = MagicMock(return_value=PullRequestMetadata(
        number=42,
        title="Feature: update logic",
        body="Updates index bounds",
        head_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        base_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        state="open",
        is_draft=False,
        repo_full_name="test-org/test-repo",
    ))

    # Mock changed files diff
    patch_content = (
        "@@ -10,6 +10,8 @@ def process():\n"
        " context line\n"
        "+    # Added line 15\n"
        "+    return index <= total\n"
    )
    orchestrator.pr_service.get_changed_files = MagicMock(return_value=[
        FilePatch(
            filename="src/logic.py",
            status="modified",
            additions=2,
            deletions=0,
            patch=patch_content,
        )
    ])

    result = orchestrator.run()
    assert result.status == "success"
    assert result.deterministic_findings_count == 0
    assert result.ai_diff_valid_count == 1
    assert result.final_published_count == 1
    assert result.published_comments[0].file == "src/logic.py"
    assert result.published_comments[0].line == 12


def test_orchestrator_partial_failure_gemini_error(mock_settings):
    """When Gemini fails, deterministic findings should still proceed and be published."""
    failing_provider = MockAIProvider(should_fail=True)

    orchestrator = ReviewOrchestrator(
        settings=mock_settings,
        ai_provider=failing_provider,
    )

    orchestrator.pr_service.get_pull_request = MagicMock(return_value=PullRequestMetadata(
        number=42,
        title="Fix credentials",
        body="Updating keys",
        head_sha="cccccccccccccccccccccccccccccccccccccccc",
        base_sha="dddddddddddddddddddddddddddddddddddddddd",
        state="open",
        is_draft=False,
        repo_full_name="test-org/test-repo",
    ))

    # Diff containing a deterministic secret
    secret_patch = (
        "@@ -1,3 +1,4 @@\n"
        " import os\n"
        "+aws_key = 'AKIA1111222233334444'\n"
    )
    orchestrator.pr_service.get_changed_files = MagicMock(return_value=[
        FilePatch(
            filename="src/config.py",
            status="modified",
            additions=1,
            deletions=0,
            patch=secret_patch,
        )
    ])

    result = orchestrator.run()
    assert result.status == "partial_failure_gemini_skipped"
    assert result.deterministic_findings_count == 1
    assert result.final_published_count == 1
    assert "AKIA1111222233334444" not in result.published_comments[0].title


def test_orchestrator_aborts_on_stale_pr(mock_settings):
    """If head SHA changes before comment publication, publication must safely abort."""
    mock_provider = MockAIProvider()
    orchestrator = ReviewOrchestrator(
        settings=mock_settings,
        ai_provider=mock_provider,
    )

    # Initial head SHA
    orchestrator.pr_service.get_pull_request = MagicMock(return_value=PullRequestMetadata(
        number=42,
        title="Refactor",
        body=None,
        head_sha="1111111111111111111111111111111111111111",
        base_sha="0000000000000000000000000000000000000000",
        state="open",
        is_draft=False,
        repo_full_name="test-org/test-repo",
    ))

    orchestrator.pr_service.get_changed_files = MagicMock(return_value=[
        FilePatch(
            filename="src/auth.py",
            status="modified",
            additions=1,
            deletions=0,
            patch="@@ -1,2 +1,3 @@\n+db_password = 'ValidPassword123!'\n",
        )
    ])

    # Recheck will report a newer commit has been pushed
    orchestrator.pr_service.get_head_sha = MagicMock(
        return_value="9999999999999999999999999999999999999999"
    )

    result = orchestrator.run()
    assert result.status == "aborted_stale_pr"
    assert result.final_published_count == 0
    assert "PR head revision has changed" in result.error_message
