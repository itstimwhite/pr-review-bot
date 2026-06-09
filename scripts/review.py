#!/usr/bin/env python3
"""PR Review Bot — AI-powered code review using free models on OpenRouter.

Incorporates best practices from Greptile, CodeRabbit, Anthropic Code Review, and PR-Agent.

Usage:
    python review.py                          # Review next unreviewed PR
    python review.py --pr 123                 # Review specific PR
    python review.py --repo owner/repo --pr 123 --token ghp_xxx

Environment variables:
    OPENROUTER_API_KEY  — OpenRouter API key (required)
    GITHUB_TOKEN        — GitHub token with pull-requests:write (required)
    OPENROUTER_MODEL    — Model to use (default: nvidia/nemotron-3-super-120b-a12b:free)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────────────────

DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
MAX_DIFF_BYTES = 500_000
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """\
You are an independent senior code reviewer. You were NOT involved in writing this code — \
you are a fresh pair of eyes.

## Review Priority
1. Logic bugs (48% of real issues) — race conditions, null dereferences, off-by-one, incorrect conditionals
2. Security — hardcoded secrets, SQL injection, XSS, auth bypass
3. Cross-file regressions — does this change break callers in other files?
4. Convention violations — check AGENTS.md if present
5. Missing tests — untested code paths, missing edge cases
6. Performance — N+1 queries, large bundles, blocking async paths

## DO NOT comment on
- Style preferences that don't violate conventions
- Variable naming (unless misleading)
- Minor formatting or import order
- Things that are technically correct but "could be better"

## Output Format
Return EXACTLY this structure:

## Review Summary
**Verdict**: Approve / Changes Requested / Comment
**Confidence**: 1-5 (1=mostly style, 5=critical bugs found)

### Critical Issues (blockers — must fix before merge)
- path/to/file.ts:123 — What's wrong, why it matters, suggested fix.
(If none, write "None.")

### Warnings (should fix)
- path/to/file.ts:456 — Description and fix.
(If none, write "None.")

### Suggestions (nice to have)
- Non-blocking improvement ideas.
(If none, write "None.")

### What Looks Good
- Highlights of what the PR does well.

Be specific. Reference exact line numbers. If the PR is clean, say so clearly — don't invent issues.\
"""


# ── Helpers ──────────────────────────────────────────────────────────────────


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"
    except Exception as exc:
        return 1, f"{type(exc).__name__}: {exc}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log(msg: str) -> None:
    print(f"[{now_iso()}] {msg}", flush=True)


# ── GitHub ───────────────────────────────────────────────────────────────────


def gh_list_prs(repo: str, token: str) -> list[dict]:
    rc, out = run([
        "gh", "pr", "list", "--repo", repo,
        "--state", "open", "--limit", "100",
        "--json", "number,title,isDraft,updatedAt,body,labels",
    ])
    if rc != 0:
        log(f"ERROR: gh pr list failed: {out[:200]}")
        return []
    return json.loads(out)


def gh_get_diff(repo: str, pr_number: int) -> str:
    rc, out = run(["gh", "pr", "diff", str(pr_number), "--repo", repo], timeout=60)
    if rc != 0:
        log(f"ERROR: gh pr diff failed: {out[:200]}")
        return ""
    return out


def gh_post_comment(repo: str, pr_number: int, body: str) -> bool:
    # Write comment to file to avoid shell escaping issues
    comment_path = Path("/tmp/pr_review_comment.md")
    comment_path.write_text(body)
    rc, out = run([
        "gh", "pr", "comment", str(pr_number), "--repo", repo,
        "--body-file", str(comment_path),
    ], timeout=30)
    if rc != 0:
        log(f"ERROR: gh pr comment failed: {out[:200]}")
        return False
    return True


# ── OpenRouter ───────────────────────────────────────────────────────────────


def call_openrouter(system_prompt: str, user_prompt: str, model: str) -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        log("ERROR: OPENROUTER_API_KEY not set")
        return None

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/itsTimWhite/pr-review-bot",
            "X-Title": "PR Review Bot",
        },
        method="POST",
    )

    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8", errors="replace").strip()
            data = json.loads(raw)
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code == 429:
                log(f"Rate limited: {body[:100]}")
                return None
            if attempt == 0:
                time.sleep(5)
                continue
            log(f"HTTP {exc.code}: {body[:200]}")
            return None
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            if attempt == 0:
                time.sleep(5)
                continue
            log(f"Error: {exc}")
            return None
    return None


# ── Review Logic ─────────────────────────────────────────────────────────────


def is_dependabot(pr: dict) -> bool:
    title = pr.get("title", "")
    labels = [l.get("name", "") for l in pr.get("labels", [])]
    indicators = ("deps:", "deps-dev:", "chore(deps):", "ci(deps):", "build(deps):")
    return any(title.startswith(i) for i in indicators) or "dependencies" in " ".join(labels)


def extract_confidence(text: str) -> int:
    m = re.search(r"\*\*Confidence\*\*\s*:\s*(\d+)", text)
    if m:
        return min(5, max(1, int(m.group(1))))
    return 3


def has_actionable_findings(text: str) -> bool:
    for header in ["### Critical Issues", "### Warnings"]:
        if header in text:
            section = text.split(header)[1].split("###")[0]
            content = [l.strip() for l in section.split("\n")
                       if l.strip() and l.strip() not in ("None.", "None")]
            if len(content) > 1 or (len(content) == 1 and len(content[0]) > 20):
                return True
    return False


def review_pr(repo: str, pr_number: int | None, model: str) -> int:
    token = os.environ.get("GITHUB_TOKEN", "")

    if pr_number:
        # Review specific PR
        log(f"Reviewing PR #{pr_number} in {repo}")
        rc, out = run([
            "gh", "pr", "view", str(pr_number), "--repo", repo,
            "--json", "number,title,body,updatedAt,isDraft",
        ])
        if rc != 0:
            log(f"ERROR: PR #{pr_number} not found")
            return 1
        pr = json.loads(out)
        if pr.get("isDraft"):
            log(f"PR #{pr_number} is a draft, skipping")
            return 0
    else:
        # Find next unreviewed PR
        log(f"Scanning {repo} for unreviewed PRs...")
        prs = gh_list_prs(repo, token)
        if not prs:
            log("No open PRs found")
            return 0

        pr = None
        for p in prs:
            if p.get("isDraft") or is_dependabot(p):
                continue
            pr = p
            break

        if not pr:
            log("All PRs are reviewed or are drafts/dependabot")
            return 0

        pr_number = pr["number"]
        log(f"Reviewing PR #{pr_number}: {pr['title']}")

    # Get diff
    diff = gh_get_diff(repo, pr_number)
    if not diff:
        log("ERROR: Empty diff")
        return 1

    if len(diff) > MAX_DIFF_BYTES:
        log(f"Diff too large ({len(diff)} bytes), skipping")
        return 0

    # Extract changed files
    changed_files = []
    for line in diff.splitlines():
        m = re.match(r"^diff --git a/(.*) b/", line)
        if m:
            changed_files.append(m.group(1))

    # Build user prompt
    file_list = "\n".join(f"  - {f}" for f in changed_files)
    diff_kb = len(diff) / 1024

    user_prompt = (
        f"## PR #{pr_number}: {pr.get('title', '')}\n\n"
        f"### Description\n{pr.get('body', '') or '_No description_'}\n\n"
        f"### Files changed ({len(changed_files)})\n{file_list}\n\n"
        f"### Diff ({diff_kb:.0f} KB)\n```diff\n{diff[:30000]}\n```"
    )

    # Call model
    log("Calling OpenRouter...")
    review_text = call_openrouter(SYSTEM_PROMPT, user_prompt, model)
    if review_text is None:
        log("ERROR: No response from model")
        return 1

    # Quality filter
    if not has_actionable_findings(review_text):
        log("Quality filter: no actionable findings, skipping")
        return 0

    # Post review
    confidence = extract_confidence(review_text)
    comment = (
        f"## AI Code Review (confidence: {confidence}/5)\n\n"
        f"{review_text}\n\n"
        f"---\n"
        f"*Automated review — please verify all suggestions before applying.*"
    )

    if gh_post_comment(repo, pr_number, comment):
        log(f"Review posted on PR #{pr_number} (confidence {confidence}/5)")
        return 0
    else:
        log("ERROR: Failed to post review")
        return 1


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="PR Review Bot — AI-powered code review")
    parser.add_argument("--repo", required=True, help="GitHub repo (owner/repo)")
    parser.add_argument("--pr", type=int, help="PR number (auto-detect if omitted)")
    parser.add_argument("--model", default=os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL),
                        help="OpenRouter model")
    parser.add_argument("--max-diff-bytes", type=int, default=MAX_DIFF_BYTES,
                        help="Skip PRs with diffs larger than this")
    args = parser.parse_args()

    return review_pr(args.repo, args.pr, args.model)


if __name__ == "__main__":
    raise SystemExit(main())
