#!/usr/bin/env python3
"""
Eval harness for the LLM Code Reviewer.

Runs a set of annotated diff fixtures through the real model and reports
precision, recall, and F1 score per issue category and overall.

Usage:
    # Set credentials
    export HF_TOKEN=your_token

    # Run against the default (v2) prompt
    python evals/run_eval.py

    # Compare prompts
    python evals/run_eval.py --prompt-version v1
    python evals/run_eval.py --prompt-version v2

    # Write results to a file
    python evals/run_eval.py --output evals/results/v2_baseline.json

Exit code:
    0 if precision >= --min-precision threshold
    1 if below threshold (useful for CI drift detection)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from reviewer.config import load_config
from reviewer.llm_client import review_chunk

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RESULTS_DIR  = Path(__file__).parent / "results"


# ── Fixture loading ────────────────────────────────────────────────────────

def load_fixtures() -> list[dict]:
    """Load all .jsonl fixture files from the fixtures directory."""
    fixtures = []
    for fpath in sorted(FIXTURES_DIR.glob("*.jsonl")):
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if line:
                    fixtures.append(json.loads(line))
    return fixtures


# ── Scoring ────────────────────────────────────────────────────────────────

def _issue_matches(predicted: dict, expected: dict) -> bool:
    """
    A predicted issue matches an expected one if:
      - same category (exact)
      - line within ±2 of expected line (model may be off by context lines)
    """
    category_match = predicted.get("category") == expected.get("category")
    line_match = abs(int(predicted.get("line", 0)) - int(expected.get("line", 0))) <= 2
    return category_match and line_match


def score_fixture(predicted: list[dict], expected_issues: list[dict]) -> dict[str, Any]:
    """Compute TP, FP, FN for one fixture."""
    tp, fp, fn = 0, 0, 0
    matched_expected = set()

    for pred in predicted:
        found = False
        for i, exp in enumerate(expected_issues):
            if i not in matched_expected and _issue_matches(pred, exp):
                tp += 1
                matched_expected.add(i)
                found = True
                break
        if not found:
            fp += 1

    fn = len(expected_issues) - len(matched_expected)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


# ── Main ───────────────────────────────────────────────────────────────────

def run_eval(prompt_version: str, min_precision: float, output_path: str | None) -> bool:
    fixtures = load_fixtures()
    if not fixtures:
        print(f"No fixtures found in {FIXTURES_DIR}. Add .jsonl files to evals/fixtures/.")
        return False

    print(f"\n{'='*60}")
    print(f"  LLM Code Reviewer Eval — Prompt {prompt_version.upper()}")
    print(f"  {len(fixtures)} fixtures | model: {os.environ.get('MODEL_NAME', 'default')}")
    print(f"{'='*60}\n")

    # Patch config to use the requested prompt version
    os.environ["PROMPT_VERSION"] = prompt_version
    cfg = load_config()

    aggregate = {"tp": 0, "fp": 0, "fn": 0}
    per_fixture_results = []

    for i, fixture in enumerate(fixtures, 1):
        name           = fixture.get("name", f"fixture_{i}")
        diff_content   = fixture["diff"]
        expected       = fixture.get("expected_issues", [])
        start          = time.time()

        print(f"[{i:2}/{len(fixtures)}] {name} ({len(expected)} expected issues)...", end=" ", flush=True)

        predicted = review_chunk(diff_content, cfg)
        elapsed   = time.time() - start
        scores    = score_fixture(predicted, expected)

        print(f"precision={scores['precision']:.0%}  recall={scores['recall']:.0%}  ({elapsed:.1f}s)")

        aggregate["tp"] += scores["tp"]
        aggregate["fp"] += scores["fp"]
        aggregate["fn"] += scores["fn"]

        per_fixture_results.append({
            "fixture":    name,
            "expected":   len(expected),
            "predicted":  len(predicted),
            **scores,
            "duration_s": round(elapsed, 2),
        })

    # Overall metrics
    tp, fp, fn = aggregate["tp"], aggregate["fp"], aggregate["fn"]
    overall_precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    overall_recall    = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    overall_f1        = (
        2 * overall_precision * overall_recall / (overall_precision + overall_recall)
        if (overall_precision + overall_recall) > 0 else 0.0
    )

    print(f"\n{'─'*60}")
    print(f"  Overall  precision={overall_precision:.1%}  recall={overall_recall:.1%}  f1={overall_f1:.1%}")
    print(f"  TP={tp}  FP={fp}  FN={fn}")
    print(f"{'─'*60}\n")

    result = {
        "prompt_version":   prompt_version,
        "model":            os.environ.get("MODEL_NAME", "default"),
        "fixture_count":    len(fixtures),
        "overall_precision": round(overall_precision, 4),
        "overall_recall":   round(overall_recall, 4),
        "overall_f1":       round(overall_f1, 4),
        "tp": tp, "fp": fp, "fn": fn,
        "per_fixture":      per_fixture_results,
    }

    if output_path:
        RESULTS_DIR.mkdir(exist_ok=True)
        Path(output_path).write_text(json.dumps(result, indent=2))
        print(f"Results written to {output_path}")

    passed = overall_precision >= min_precision
    if not passed:
        print(f"EVAL FAILED: precision {overall_precision:.1%} < threshold {min_precision:.1%}")
    else:
        print(f"EVAL PASSED: precision {overall_precision:.1%} >= threshold {min_precision:.1%}")

    return passed


def main():
    ap = argparse.ArgumentParser(description="Run LLM code reviewer eval harness")
    ap.add_argument("--prompt-version", default="v2", choices=["v1", "v2"],
                    help="Prompt version to evaluate (default: v2)")
    ap.add_argument("--min-precision", type=float, default=0.70,
                    help="Minimum precision threshold (default: 0.70)")
    ap.add_argument("--output", default=None,
                    help="Path to write JSON results (default: print only)")
    args = ap.parse_args()

    passed = run_eval(
        prompt_version=args.prompt_version,
        min_precision=args.min_precision,
        output_path=args.output,
    )
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
