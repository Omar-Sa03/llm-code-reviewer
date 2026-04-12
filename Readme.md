# LLM Code Reviewer

An automated code review tool that runs on every pull request. It reads the diff, sends each changed chunk to a language model, and posts inline comments directly on the PR with issues it finds — security problems, bugs, performance concerns, and style notes.

It is designed to be dropped into any GitHub repository with minimal setup.

---

## How it works

When a pull request is opened or updated, a GitHub Actions workflow fetches the diff, splits it into chunks by file and hunk, and sends each chunk to a Hugging Face hosted model. The model returns a list of issues in a structured format. Those issues are filtered by confidence score and severity, then posted as inline review comments on the relevant lines. A summary comment is posted at the end of every run.

---

## Quick start

### 1. Add the secret

In your repository, go to Settings > Secrets and variables > Actions and add a secret named `HF_TOKEN` with your Hugging Face API token. You can get one from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).

### 2. Add the workflow file

Create `.github/workflows/review.yml` in your repository:

```yaml
name: LLM Code Review

on:
  pull_request:
    types: [opened, synchronize]
    paths-ignore:
      - "*.md"
      - "docs/**"

jobs:
  review:
    runs-on: ubuntu-latest

    permissions:
      pull-requests: write
      contents: read

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Run LLM Reviewer
        uses: Omar-Sa03/llm-code-reviewer@v1
        with:
          hf_token: ${{ secrets.HF_TOKEN }}
```

---

## Configuration

All inputs are optional except `hf_token`.

| Input | Default | Description |
|---|---|---|
| `hf_token` | required | Your Hugging Face API token. Always pass this via a secret. |
| `model` | `Qwen/Qwen2.5-Coder-32B-Instruct` | Any chat model available through the Hugging Face Inference API. |
| `max_comments` | `8` | Maximum number of comments posted across the entire PR. |
| `max_comments_per_file` | `3` | Maximum number of comments posted on any single file. |

Example with all options:

```yaml
- name: Run LLM Reviewer
  uses: Omar-Sa03/llm-code-reviewer@v1
  with:
    hf_token: ${{ secrets.HF_TOKEN }}
    model: Qwen/Qwen2.5-Coder-32B-Instruct
    max_comments: "10"
    max_comments_per_file: "4"
```

---

## Comment types

Each issue is tagged with a severity level and a category.

**Severity levels**

- Error — likely to cause a failure, data loss, or a security vulnerability. High confidence threshold required before posting.
- Warning — something that could cause problems in certain conditions or makes the code fragile.
- Suggestion — a style, readability, or minor quality note.

**Categories**

- `security` — authentication issues, injection vulnerabilities, hardcoded secrets, insecure defaults
- `bug` — logic errors, off-by-one errors, unhandled edge cases, incorrect return values
- `performance` — unnecessary work in loops, missing indexes, repeated computation
- `logic` — control flow that does not match intent, unreachable code, incorrect conditions
- `style` — naming, formatting, and readability improvements

Each comment includes a confidence score. Issues below the threshold for their severity level are discarded and never posted.

---

## Files that are skipped

The reviewer automatically ignores generated and vendored files that are not worth reviewing:

- Lock files (`package-lock.json`, `yarn.lock`)
- Compiled or minified output (`dist/`, `build/`, `*.min.js`, `*.min.css`)
- Database migrations
- Snapshot files (`*.snap`)
- Any file matching `*.generated.*`

---

## Choosing a model

The default model is `Qwen/Qwen2.5-Coder-32B-Instruct`, which performs well on code review tasks and is available through Hugging Face's inference routing. You can swap it for any other chat model on the platform by setting the `model` input.

Keep in mind that larger models produce better results but take longer to respond. For most repositories the default is a reasonable balance.

---

## Requirements

- A Hugging Face account with API access
- GitHub Actions enabled on your repository
- The workflow job must have `pull-requests: write` and `contents: read` permissions

No other infrastructure is needed. The reviewer runs entirely within the GitHub Actions runner.

---

## Running locally

You can run the reviewer outside of GitHub Actions for testing. Copy `.env.example` to `.env` and fill in the values:

```
GITHUB_TOKEN=your_github_token
GITHUB_REPOSITORY=owner/repo
PR_NUMBER=42
PR_SHA=abc123
HF_TOKEN=your_hf_token
MODEL_NAME=Qwen/Qwen2.5-Coder-32B-Instruct
MAX_COMMENTS_TOTAL=8
MAX_COMMENTS_PER_FILE=3
```

Then run:

```bash
pip install -r requirements.txt
python -m reviewer.main
```

---

## Running tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

The test suite covers the diff parser, confidence filter, prompt builder, JSON response parser, and a full end-to-end pipeline run with all external HTTP calls mocked.

---
