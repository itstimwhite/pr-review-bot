# PR Review Bot — AI-Powered Code Review

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Model: Free](https://img.shields.io/badge/model-free-green.svg)](https://openrouter.ai)

AI-powered pull request review bot that incorporates best practices from [Greptile](https://www.greptile.com/), [CodeRabbit](https://coderabbit.ai/), [Anthropic Code Review](https://www.anthropic.com/engineering/multi-agent-research-system), and [PR-Agent](https://github.com/The-PR-Agent/pr-agent).

**Uses free models on OpenRouter — $0 per review.**

## What It Does

Every time a PR is opened or updated, the bot:

1. **Fetches the PR diff** and changed files via GitHub CLI
2. **Queries GBrain** (optional) for codebase context on the changed areas
3. **Builds a research-backed prompt** focused on logic errors, security, cross-file regressions, and convention violations
4. **Calls a free LLM** (NVIDIA Nemotron 3 Super 120B) via OpenRouter
5. **Posts the review** as a PR comment with confidence scoring

## Key Design Principles

Based on analyzing 3.4M+ PR reviews:

- **48% of real bugs are logic errors** — the prompt prioritizes logic over style
- **Cross-file analysis is #1 value** — explicitly checks callers/callees of changed functions
- **Independence matters** — separate from code generation (never reviews its own code)
- **Confidence scoring (1-5)** — enables triage, high-confidence PRs merge 3.6x faster
- **Quality filtering** — skips reviews with no actionable findings (reduces noise)

## Quick Start

### As a GitHub Action (Recommended)

Add `.github/workflows/pr-review.yml` to your repo:

```yaml
name: PR Review
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
      - uses: itstimwhite/pr-review-bot@v1
        with:
          openrouter-api-key: ${{ secrets.OPENROUTER_API_KEY }}
```

### As a Cron Job (Local)

```bash
pip install pr-review-bot
export OPENROUTER_API_KEY=sk-or-...
export GITHUB_TOKEN=ghp_...
pr-review-bot --repo owner/repo
```

### As a CLI (One-Off)

```bash
pr-review-bot --pr-url https://github.com/owner/repo/pull/123
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key (free tier works) |
| `GITHUB_TOKEN` | Yes | GitHub token with `pull-requests:write` |
| `REPO_PATH` | No | Local repo path (default: cwd) |
| `MODEL` | No | OpenRouter model (default: `nvidia/nemotron-3-super-120b-a12b:free`) |
| `MAX_DIFF_BYTES` | No | Skip PRs larger than this (default: 500000) |
| `GBRAIN_ENABLED` | No | Enable GBrain context (default: false) |

### REVIEW.md — Custom Review Criteria

Create a `REVIEW.md` in your repo root to customize what the bot looks for:

```markdown
# Review Criteria

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

Default model is `nvidia/nemotron-3-super-120b-a12b:free` — a 120B parameter model, free on OpenRouter.

Other free options:
- `nvidia/nemotron-3-super-120b-a12b:free` (120B, best quality)
- `qwen/qwen3-coder:free` (fast, good for code)
- `google/gemini-2.5-flash:free` (fast, Google)

Paid options for higher quality:
- `anthropic/claude-sonnet-4` (best code review quality)
- `openai/gpt-4o` (good all-rounder)

## Architecture

```
PR Event (webhook/cron)
  │
  ├── gh pr list → find unreviewed PRs
  ├── gh pr diff → get changes
  ├── gbrain search → codebase context (optional)
  │
  ├── Build prompt (research-backed)
  │   ├── System: conventions, invariants, priority order
  │   ├── User: PR title, description, files, diff
  │   └── Context: GBrain results, REVIEW.md, linked issues
  │
  ├── OpenRouter API → LLM review
  │
  ├── Quality filter → skip if no actionable findings
  │
  └── gh pr comment → post review with confidence score
```

## Research Sources

- [Greptile: AI Code Review Best Practices](https://www.greptile.com/blog/ai-code-review) — 3.4M+ PR analysis
- [Anthropic: Multi-Agent Code Review](https://thenewstack.io/anthropic-launches-a-multi-agent-code-review-tool-for-claude-code/) — March 2026
- [CodeRabbit Changelog](https://docs.coderabbit.ai/changelog) — feature evolution
- [PR-Agent](https://github.com/The-PR-Agent/pr-agent) — open source PR review
- [Augment Code: Open Source AI Code Review Tools](https://www.augmentcode.com/tools/open-source-ai-code-review-tools-worth-trying) — benchmark testing

## License

MIT — see [LICENSE](LICENSE)
