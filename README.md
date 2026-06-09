# PR Review Bot — AI-Powered Code Review

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Model: Free](https://img.shields.io/badge/model-free-green.svg)](https://openrouter.ai)

AI-powered pull request review bot. Uses free models on OpenRouter — $0 per review.

## What It Does

Every time a PR is opened or updated, the bot:

1. **Fetches the PR diff** and changed files via GitHub CLI
2. **Builds a prompt** focused on logic errors, security, cross-file regressions, and convention violations
3. **Calls a free LLM** (NVIDIA Nemotron 3 Super 120B) via OpenRouter
4. **Posts the review** as a PR comment with confidence scoring

## Quick Start

### As a GitHub Action (Recommended)

Add `.github/workflows/pr-review.yml` to your repo:

```yaml
name: AI Code Review
on:
  pull_request:
    types: [opened, reopened, ready_for_review]

jobs:
  review:
    runs-on: ubuntu-latest
    if: github.event.pull_request.draft == false
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install requests
      - env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
        run: |
          curl -sL https://raw.githubusercontent.com/itsTimWhite/pr-review-bot/main/scripts/review.py -o /tmp/review.py
          python3 /tmp/review.py --repo ${{ github.repository }} --pr ${{ github.event.pull_request.number }}
```

Then add an `OPENROUTER_API_KEY` secret to your repo (get one free at [openrouter.ai](https://openrouter.ai)).

### As a CLI (One-Off)

```bash
python3 review.py --repo owner/repo --pr 123
```

### As a CLI

```bash
# Review next unreviewed PR
python3 scripts/review.py review --repo owner/repo

# Review specific PR
python3 scripts/review.py review --repo owner/repo --pr 123

# Dry run (print review without posting)
python3 scripts/review.py review --repo owner/repo --pr 123 --dry-run

# JSON output (for agents/piping)
python3 scripts/review.py review --repo owner/repo --pr 123 --dry-run --json

# List unreviewed PRs
python3 scripts/review.py queue --repo owner/repo

# Post an existing review file
python3 scripts/review.py post --repo owner/repo --pr 123 --file review.md
```

### As a Cron Job

```bash
# Review next unreviewed PR every 15 minutes
*/15 * * * * python3 scripts/review.py review --repo owner/repo
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key (free tier works) |
| `GITHUB_TOKEN` | Yes | GitHub token with `pull-requests:write` |
| `OPENROUTER_MODEL` | No | Model (default: `nvidia/nemotron-3-super-120b-a12b:free`) |
| `MAX_DIFF_BYTES` | No | Skip PRs larger than this (default: 500000) |

### REVIEW.md — Custom Review Criteria

Create a `REVIEW.md` in your repo root:

```markdown
Prioritize:
- Authorization regressions across admin and customer paths
- Idempotency in webhook handlers
- Missing transaction boundaries on billing writes

Deprioritize:
- Formatting and import order
- Naming-only comments without runtime risk
```

### AGENTS.md — Project Context

The bot reads your `AGENTS.md` (if present) to understand project conventions, tech stack, and hard invariants.

## Models

| Model | Cost | Notes |
|-------|------|-------|
| `nvidia/nemotron-3-super-120b-a12b:free` | Free | 120B params, best quality free model |
| `qwen/qwen3-coder:free` | Free | Fast, good for code |
| `google/gemini-2.5-flash:free` | Free | Fast, Google |
| `anthropic/claude-sonnet-4` | Paid | Best code review quality |
| `openai/gpt-4o` | Paid | Good all-rounder |

## Architecture

```
PR Event (webhook/cron)
  │
  ├── gh pr list → find unreviewed PRs
  ├── gh pr diff → get changes
  │
  ├── Build prompt (priority-ordered)
  │   ├── System: conventions, invariants, priority order
  │   └── User: PR title, description, files, diff
  │
  ├── OpenRouter API → LLM review
  │
  ├── Quality filter → skip if no actionable findings
  │
  └── gh pr comment → post review with confidence score
```

## License

MIT — see [LICENSE](LICENSE)
