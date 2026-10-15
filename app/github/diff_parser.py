"""Unified diff parser for identifying changed line positions and patch hunks."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.github.pull_request import FilePatch

logger = logging.getLogger("pr_review_agent.github.diff_parser")


@dataclass(frozen=True)
class DiffHunk:
    """Represents a single parsed diff hunk."""

    old_start: int
    old_length: int
    new_start: int
    new_length: int
    header: str
    lines: list[str]


@dataclass
class ParsedDiff:
    """Contains all parsed line mappings and change metadata for a set of file patches."""

    # Maps filename -> set of valid line numbers in the *new* file (right side)
    valid_changed_lines: dict[str, set[int]] = field(default_factory=dict)

    # Maps (filename, line_number) -> text content of the added/modified line
    added_lines_content: dict[tuple[str, int], str] = field(default_factory=dict)

    # Maps filename -> list of hunks
    file_hunks: dict[str, list[DiffHunk]] = field(default_factory=dict)

    # Maps filename -> raw patch string
    raw_patches: dict[str, str] = field(default_factory=dict)

    def is_line_changed(self, filename: str, line: int) -> bool:
        """Verify whether a given line number in a file was modified or added in this PR."""
        return line in self.valid_changed_lines.get(filename, set())

    def get_line_content(self, filename: str, line: int) -> Optional[str]:
        """Retrieve the text content of a changed line if available."""
        return self.added_lines_content.get((filename, line))


class DiffParser:
    """Parser for unified diff patches provided by GitHub API."""

    HUNK_HEADER_PATTERN = re.compile(
        r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$"
    )

    def parse_patches(self, file_patches: list[FilePatch]) -> ParsedDiff:
        """Parse a collection of FilePatch objects into a structured ParsedDiff.

        Args:
            file_patches: List of FilePatch items from the PR.

        Returns:
            ParsedDiff containing line-level mappings.
        """
        result = ParsedDiff()

        for file_patch in file_patches:
            filename = file_patch.filename
            if not file_patch.has_patch or file_patch.status == "deleted":
                # Deleted files or files without patches (e.g. binaries) have no valid right-side lines
                result.valid_changed_lines[filename] = set()
                continue

            result.raw_patches[filename] = file_patch.patch or ""
            changed_lines, content_map, hunks = self._parse_single_patch(
                filename, file_patch.patch or ""
            )
            result.valid_changed_lines[filename] = changed_lines
            result.added_lines_content.update(content_map)
            result.file_hunks[filename] = hunks

        return result

    def _parse_single_patch(
        self, filename: str, patch_text: str
    ) -> tuple[set[int], dict[tuple[str, int], str], list[DiffHunk]]:
        """Parse a single file's unified diff text.

        Returns:
            Tuple of (valid_changed_lines_set, added_content_dict, hunk_list)
        """
        changed_lines: set[int] = set()
        content_map: dict[tuple[str, int], str] = {}
        hunks: list[DiffHunk] = []

        lines = patch_text.splitlines()
        current_hunk_lines: list[str] = []
        current_hunk_meta: Optional[tuple[int, int, int, int, str]] = None
        new_line_cursor = 0

        for line in lines:
            header_match = self.HUNK_HEADER_PATTERN.match(line)
            if header_match:
                # Flush previous hunk if any
                if current_hunk_meta is not None:
                    old_s, old_l, new_s, new_l, hdr = current_hunk_meta
                    hunks.append(
                        DiffHunk(
                            old_start=old_s,
                            old_length=old_l,
                            new_start=new_s,
                            new_length=new_l,
                            header=hdr,
                            lines=list(current_hunk_lines),
                        )
                    )
                    current_hunk_lines.clear()

                old_start = int(header_match.group(1))
                old_len = int(header_match.group(2)) if header_match.group(2) else 1
                new_start = int(header_match.group(3))
                new_len = int(header_match.group(4)) if header_match.group(4) else 1
                header_extra = header_match.group(5)

                current_hunk_meta = (old_start, old_len, new_start, new_len, header_extra)
                new_line_cursor = new_start
                continue

            if current_hunk_meta is None:
                continue

            current_hunk_lines.append(line)

            if line.startswith("+") and not line.startswith("+++"):
                # Line was added or modified in the target PR revision
                changed_lines.add(new_line_cursor)
                content_map[(filename, new_line_cursor)] = line[1:]
                new_line_cursor += 1
            elif line.startswith("-") and not line.startswith("---"):
                # Line was deleted from old revision; does not advance new line cursor
                pass
            elif line.startswith(" "):
                # Context line present in both revisions
                new_line_cursor += 1
            elif line.startswith(r"\ No newline at end of file"):
                # Metadata line; does not advance line cursor
                pass
            else:
                # Fallback for unexpected diff characters
                new_line_cursor += 1

        # Flush final hunk
        if current_hunk_meta is not None:
            old_s, old_l, new_s, new_l, hdr = current_hunk_meta
            hunks.append(
                DiffHunk(
                    old_start=old_s,
                    old_length=old_l,
                    new_start=new_s,
                    new_length=new_l,
                    header=hdr,
                    lines=current_hunk_lines,
                )
            )

        return changed_lines, content_map, hunks
