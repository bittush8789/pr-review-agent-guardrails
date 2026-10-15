"""Deterministic dependency and supply chain vulnerability scanner.

Scans changed lines in dependency specification files (requirements.txt, package.json,
pyproject.toml, Pipfile, go.mod) for:
- Wildcard or unpinned package versions (supply chain risk)
- Insecure HTTP package download URLs (MitM tampering)
- Known vulnerable package versions with published CVEs
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.schemas.review_finding import ReviewFinding, ReviewCategory, SeverityLevel

logger = logging.getLogger("pr_review_agent.rules.dependency_scanner")


def parse_version_tuple(v_str: str) -> tuple[int, ...]:
    """Extract numeric components from a version string (e.g. '2.25.1' -> (2, 25, 1))."""
    digits = re.findall(r"\d+", v_str)
    return tuple(int(d) for d in digits[:3]) if digits else (0,)


@dataclass(frozen=True)
class KnownVulnerability:
    """Known vulnerable library and minimum safe version."""

    package: str
    min_safe_version: str
    min_safe_tuple: tuple[int, ...]
    cve_id: str
    description: str
    severity: SeverityLevel
    ecosystem: str  # "python" or "npm"


# Curated database of critical and high CVEs in popular packages
KNOWN_VULNERABILITIES: list[KnownVulnerability] = [
    KnownVulnerability(
        package="requests",
        min_safe_version="2.31.0",
        min_safe_tuple=(2, 31, 0),
        cve_id="CVE-2023-32681",
        description="Information disclosure: Sensitive Authorization headers leaked to unintended hosts on redirect.",
        severity=SeverityLevel.HIGH,
        ecosystem="python",
    ),
    KnownVulnerability(
        package="urllib3",
        min_safe_version="2.0.7",
        min_safe_tuple=(2, 0, 7),
        cve_id="CVE-2023-45803",
        description="Request body stripping & sensitive header leak on HTTP redirect.",
        severity=SeverityLevel.HIGH,
        ecosystem="python",
    ),
    KnownVulnerability(
        package="pyyaml",
        min_safe_version="5.4",
        min_safe_tuple=(5, 4, 0),
        cve_id="CVE-2020-14343",
        description="Arbitrary code execution through untrusted YAML deserialization in FullLoader.",
        severity=SeverityLevel.CRITICAL,
        ecosystem="python",
    ),
    KnownVulnerability(
        package="flask",
        min_safe_version="2.2.5",
        min_safe_tuple=(2, 2, 5),
        cve_id="CVE-2023-30861",
        description="High-severity session cookie security flaw leading to session disclosure.",
        severity=SeverityLevel.HIGH,
        ecosystem="python",
    ),
    KnownVulnerability(
        package="jinja2",
        min_safe_version="3.1.3",
        min_safe_tuple=(3, 1, 3),
        cve_id="CVE-2024-22195",
        description="Cross-site scripting (XSS) vulnerability via xmlattr filter with keys containing spaces.",
        severity=SeverityLevel.MEDIUM,
        ecosystem="python",
    ),
    KnownVulnerability(
        package="cryptography",
        min_safe_version="42.0.4",
        min_safe_tuple=(42, 0, 4),
        cve_id="CVE-2024-26130",
        description="Memory corruption via NULL pointer dereference in PKCS#12 decoding routines.",
        severity=SeverityLevel.HIGH,
        ecosystem="python",
    ),
    KnownVulnerability(
        package="paramiko",
        min_safe_version="2.10.1",
        min_safe_tuple=(2, 10, 1),
        cve_id="CVE-2022-24302",
        description="Race condition in authorization allowing unauthorized key persistence.",
        severity=SeverityLevel.HIGH,
        ecosystem="python",
    ),
    KnownVulnerability(
        package="lodash",
        min_safe_version="4.17.21",
        min_safe_tuple=(4, 17, 21),
        cve_id="CVE-2021-23337",
        description="Prototype pollution vulnerability enabling command injection via template.",
        severity=SeverityLevel.CRITICAL,
        ecosystem="npm",
    ),
    KnownVulnerability(
        package="axios",
        min_safe_version="1.6.0",
        min_safe_tuple=(1, 6, 0),
        cve_id="CVE-2023-45857",
        description="Cross-origin request header leak exposing sensitive authentication tokens.",
        severity=SeverityLevel.HIGH,
        ecosystem="npm",
    ),
    KnownVulnerability(
        package="jsonwebtoken",
        min_safe_version="9.0.0",
        min_safe_tuple=(9, 0, 0),
        cve_id="CVE-2022-23529",
        description="Insecure verification allowing algorithm confusion and remote code execution.",
        severity=SeverityLevel.CRITICAL,
        ecosystem="npm",
    ),
    KnownVulnerability(
        package="express",
        min_safe_version="4.19.2",
        min_safe_tuple=(4, 19, 2),
        cve_id="CVE-2024-29041",
        description="Open redirect vulnerability in express router allowlisting.",
        severity=SeverityLevel.MEDIUM,
        ecosystem="npm",
    ),
]


class DependencyScanner:
    """Scans dependency manifests in pull request diffs for supply chain vulnerabilities."""

    MANIFEST_EXTENSIONS = (
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "pipfile",
        "package.json",
        "go.mod",
    )

    def is_dependency_manifest(self, filename: str) -> bool:
        """Return True if the file is a recognized dependency specification file."""
        lower = filename.lower()
        if lower.endswith(self.MANIFEST_EXTENSIONS):
            return True
        if "requirements" in lower and lower.endswith(".txt"):
            return True
        return False

    def scan_diff_lines(self, added_lines: dict[tuple[str, int], str]) -> list[ReviewFinding]:
        """Scan added diff lines within dependency files.

        Args:
            added_lines: Mapping of (filename, line_number) -> text_content.

        Returns:
            List of ReviewFinding objects.
        """
        findings: list[ReviewFinding] = []

        for (filename, line_num), content in added_lines.items():
            if not self.is_dependency_manifest(filename):
                continue

            stripped = content.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue

            # 1. Check for insecure HTTP download URLs
            http_match = re.search(r"""(?:https?://[^\s'"]+)""", stripped, re.IGNORECASE)
            if http_match and http_match.group(0).lower().startswith("http://"):
                secure_fix = stripped.replace("http://", "https://")
                findings.append(
                    ReviewFinding(
                        file=filename,
                        line=line_num,
                        severity=SeverityLevel.HIGH,
                        category=ReviewCategory.SECURITY,
                        title="Insecure HTTP dependency download URL",
                        suggestion=(
                            "Dependency source URL uses unencrypted `http://`. "
                            "This exposes your build to Man-in-the-Middle (MitM) code tampering and supply chain poisoning. "
                            "Always use encrypted `https://` or SSH repository URLs."
                        ),
                        confidence=0.95,
                        source="deterministic:dependency_scanner:DEP_INSECURE_HTTP_URL",
                        rule_id="DEP_INSECURE_HTTP_URL",
                        suggested_code=secure_fix,
                    )
                )

            # 2. Check for Wildcard or unpinned dependencies
            # e.g., "lodash": "*" or "express": "latest" or flask=*
            if self._is_wildcard_unpinned(filename, stripped):
                fix_suggestion = self._suggest_pinned_version(stripped)
                findings.append(
                    ReviewFinding(
                        file=filename,
                        line=line_num,
                        severity=SeverityLevel.HIGH,
                        category=ReviewCategory.MAINTAINABILITY,
                        title="Unpinned / Wildcard dependency version detected",
                        suggestion=(
                            "Dependency version is unpinned or uses a wildcard (`*` or `latest`). "
                            "This leaves the project vulnerable to supply chain attacks (dependency confusion, "
                            "compromised releases) and unpredictable build breakage. Pin to a specific version."
                        ),
                        confidence=0.90,
                        source="deterministic:dependency_scanner:DEP_UNPINNED_WILDCARD",
                        rule_id="DEP_UNPINNED_WILDCARD",
                        suggested_code=fix_suggestion,
                    )
                )

            # 3. Check for Known Vulnerabilities (CVEs)
            cve_finding = self._check_known_cve(filename, line_num, stripped)
            if cve_finding:
                findings.append(cve_finding)

        logger.debug("DependencyScanner found %d findings.", len(findings))
        return findings

    def _is_wildcard_unpinned(self, filename: str, line: str) -> bool:
        """Detect wildcard or completely unpinned package lines."""
        lower_file = filename.lower()

        # Node package.json: e.g. "lodash": "*" or "lodash": "latest"
        if "package.json" in lower_file:
            if re.search(r""""[^"]+"\s*:\s*["'](?:\*|latest)["']""", line):
                return True

        # Python requirements.txt: e.g. "requests=*" or "requests==*"
        if "requirements" in lower_file or "pipfile" in lower_file:
            if re.search(r"""^[a-zA-Z0-9_\-\.]+\s*==?\s*\*""", line):
                return True

        return False

    def _suggest_pinned_version(self, line: str) -> Optional[str]:
        """Generate a replacement suggestion for wildcard versions."""
        if "*" in line:
            return line.replace("*", "1.0.0")
        if "latest" in line:
            return line.replace("latest", "^1.0.0")
        return None

    def _check_known_cve(self, filename: str, line_num: int, line: str) -> Optional[ReviewFinding]:
        """Detect if line specifies a known vulnerable library version."""
        lower_file = filename.lower()
        is_npm = "package.json" in lower_file
        is_python = "requirements" in lower_file or "pyproject.toml" in lower_file or "pipfile" in lower_file

        for vuln in KNOWN_VULNERABILITIES:
            if is_npm and vuln.ecosystem != "npm":
                continue
            if is_python and vuln.ecosystem != "python":
                continue

            # Look for package name in the line
            pkg_pattern = rf"""(?:\b{re.escape(vuln.package)}\b)"""
            if not re.search(pkg_pattern, line, re.IGNORECASE):
                continue

            # Extract version
            # E.g. requests==2.25.1 or "lodash": "^4.17.15" or "lodash": "4.17.15"
            ver_match = re.search(r"""(?:==|<=|<|~=|\^|:)\s*["']?v?([0-9]+(?:\.[0-9]+)*)["']?""", line)
            if not ver_match:
                continue

            ver_str = ver_match.group(1)
            parsed_tuple = parse_version_tuple(ver_str)

            # Check if installed version is strictly less than the minimum safe version
            if parsed_tuple < vuln.min_safe_tuple:
                # Generate suggested replacement line
                suggested_fix = None
                if is_python:
                    suggested_fix = re.sub(
                        rf"""{re.escape(vuln.package)}\s*(?:==|<=|<|~=)[^\s#]+""",
                        f"{vuln.package}>={vuln.min_safe_version}",
                        line,
                    )
                elif is_npm:
                    suggested_fix = re.sub(
                        rf"""("{re.escape(vuln.package)}"\s*:\s*)"[^"]+""",
                        rf'\g<1>"^{vuln.min_safe_version}"',
                        line,
                    )

                return ReviewFinding(
                    file=filename,
                    line=line_num,
                    severity=vuln.severity,
                    category=ReviewCategory.SECURITY,
                    title=f"Known vulnerable dependency: {vuln.package} < {vuln.min_safe_version} ({vuln.cve_id})",
                    suggestion=(
                        f"Detected `{vuln.package}=={ver_str}` which is vulnerable to **{vuln.cve_id}**.\n\n"
                        f"**Impact:** {vuln.description}\n\n"
                        f"**Remediation:** Upgrade `{vuln.package}` to version `{vuln.min_safe_version}` or higher."
                    ),
                    confidence=0.96,
                    source=f"deterministic:dependency_scanner:{vuln.cve_id}",
                    rule_id=vuln.cve_id,
                    suggested_code=suggested_fix if suggested_fix != line else None,
                )

        return None
