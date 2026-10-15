"""Application CLI entry point for the GitHub PR-Review Agent with Guardrails."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Optional

from app.config.settings import Settings, load_settings, setup_logging, ConfigurationError
from app.review.orchestrator import ReviewOrchestrator, ReviewExecutionResult

logger = logging.getLogger("pr_review_agent.main")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command line options, allowing CLI overrides of environment variables."""
    parser = argparse.ArgumentParser(
        description="GitHub PR-Review Agent with Guardrails: Automated Pull Request security reviewer.",
    )
    parser.add_argument(
        "--repo",
        dest="github_repository",
        help="GitHub repository in 'owner/repo' format.",
    )
    parser.add_argument(
        "--pr",
        dest="pull_request_number",
        type=int,
        help="Target pull request number.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Execute analysis without posting inline comments to GitHub.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """Execute review agent CLI pipeline.

    Returns:
        0 on success, 1 on configuration or runtime error, 2 on stale PR abortion.
    """
    args = parse_args(argv)

    # Allow CLI arguments to override environment variables
    env_overrides = dict(os.environ)
    if args.github_repository:
        env_overrides["GITHUB_REPOSITORY"] = args.github_repository
    if args.pull_request_number:
        env_overrides["PULL_REQUEST_NUMBER"] = str(args.pull_request_number)
    if args.dry_run is not None:
        env_overrides["DRY_RUN"] = "true" if args.dry_run else "false"
    if args.log_level:
        env_overrides["LOG_LEVEL"] = args.log_level

    try:
        settings = load_settings(env_overrides)
    except ConfigurationError as config_err:
        # Avoid logging filter dependency if setup hasn't run yet
        print(f"CONFIGURATION ERROR: {config_err}", file=sys.stderr)
        return 1

    setup_logging(settings.log_level)
    logger.info("Starting GitHub PR-Review Agent with Guardrails...")
    logger.info("Target: %s#%d (dry_run=%s)", settings.github_repository, settings.pull_request_number, settings.dry_run)

    try:
        orchestrator = ReviewOrchestrator(settings)
        result: ReviewExecutionResult = orchestrator.run()

        # Emit JSON summary to stdout
        output_summary = json.dumps(result.to_dict(), indent=2)
        print(output_summary)

        if result.status == "failed":
            logger.error("Review orchestration failed: %s", result.error_message)
            return 1
        elif result.status == "aborted_stale_pr":
            logger.warning("Review publication aborted due to stale PR head SHA.")
            return 2

        logger.info("Review completed successfully.")
        return 0

    except Exception as exc:
        logger.exception("Fatal unhandled error in review agent: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
