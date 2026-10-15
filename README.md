# 🛡️ GitHub PR-Review Agent with Guardrails

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Security Guardrails](https://img.shields.io/badge/guardrails-active-orange.svg)](#-features)

A security-focused automated code review agent for GitHub Pull Requests. It combines **deterministic security scanning** with **Google Gemini AI analysis**, protected by strict guardrails against prompt injection, off-diff comments, and alert fatigue.

---

## ⚡ Features

- **Deterministic Security**: Scans for leaked secrets (AWS, GitHub, Slack tokens), insecure Terraform configs (`0.0.0.0/0`, public S3), and vulnerable dependencies (known CVEs in `requirements.txt`, `package.json`).
- **AI Code Review**: Leverages Google Gemini for deep logic and bug inspection with structured JSON outputs.
- **One-Click Suggestions**: Posts GitHub-native ```suggestion blocks for 1-click fixes directly on PR lines.
- **Strict Guardrails**: Zero comments on unchanged lines, max comment caps (default: 5), deduplication, and prompt-injection isolation.
- **PR Complexity**: Auto-categorizes review scope (`XS` to `XL`) and estimates human review effort.

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone https://github.com/bittush8789/pr-review-agent-guardrails.git
cd pr-review-agent-guardrails
pip install -r requirements.txt
```

### 2. Configuration
Copy `.env.example` to `.env` and fill in your keys:
```ini
GITHUB_TOKEN=ghp_your_github_token
GITHUB_REPOSITORY=owner/repo
PULL_REQUEST_NUMBER=1
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Run
```bash
# Run local interactive demo
python examples/run_demo.py

# Or review a live PR
python -m app.main
```

---

## 🤖 GitHub Actions

To run on every pull request automatically, add your Gemini API key under **Repo Settings > Secrets > Actions** as `GEMINI_API_KEY`. The workflow in [`.github/workflows/pr-review.yml`](.github/workflows/pr-review.yml) handles the rest.

---

## 🧪 Testing

```bash
pytest
```

---

## 📁 Project Structure

```text
├── .github/workflows/      # Automated PR review GitHub Actions workflow
├── app/
│   ├── config/             # Settings & sensitive data redaction
│   ├── github/             # GitHub REST API client & diff parser
│   ├── guardrails/         # Schema, line-boundary & injection defense
│   ├── providers/          # Google Gemini AI integration
│   ├── review/             # Review orchestrator & executive summary
│   ├── rules/              # Secret, Terraform & dependency scanners
│   └── schemas/            # JSON schemas & 1-click suggested changes
├── evals/                  # Benchmark datasets & evaluation metrics
├── examples/               # Standalone interactive demo (run_demo.py)
├── tests/                  # Unit and integration test suite (60 tests)
└── requirements.txt        # Project dependencies
```

---

## 📄 License

[Apache 2.0](LICENSE)
