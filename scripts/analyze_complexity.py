#!/usr/bin/env python3
"""
Static code complexity analysis
Uses ruff to find overly long functions, high cyclomatic complexity, large classes

Usage:
    python scripts/analyze_complexity.py
"""

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Ruff check rules
# C901: Function too long/complex (cyclomatic complexity)
# PLR0912: Too many branches
# PLR0913: Too many arguments
# PLR0914: Too many local variables
# PLR0915: Too many statements
# PLR0911: Too many return statements
# PLR0904: Too many public methods
# PLR0902: Too many instance attributes

RULES = [
    "C901",  # Cyclomatic complexity
    "PLR0912",  # Too many branches
    "PLR0913",  # Too many arguments
    "PLR0914",  # Too many local variables
    "PLR0915",  # Too many statements
    "PLR0911",  # Too many return statements
    "PLR0904",  # Too many public methods
    "PLR0902",  # Too many instance attributes
]

EXCLUDE_DIRS = [
    "backup",
    "__pycache__",
    ".venv",
    "venv",
    ".local",
    "site-packages",
    ".git",
    "dist",
    "build",
    "*.egg-info",
    ".claude/worktrees",
]


def build_exclude_args():
    args = []
    for d in EXCLUDE_DIRS:
        args.extend(["--exclude", d])
    return args


def run_ruff_check(rules: list, max_results: int = 50):
    """Run ruff check and return results"""

    cmd = [
        "ruff",
        "check",
        "--select",
        ",".join(rules),
        "--output-format",
        "concise",
        *build_exclude_args(),
        str(PROJECT_ROOT),
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        print("OK: No issues found")
        return []

    # Parse output
    lines = result.stdout.strip().split("\n")
    issues = []

    for line in lines:
        if not line.strip():
            continue
        # Format: path:line:col: CODE message
        parts = line.split(":", 3)
        if len(parts) >= 4:
            file_path = parts[0]
            line_no = parts[1]
            col_no = parts[2]
            rest = parts[3].strip()
            code = rest.split(" ")[0]
            message = " ".join(rest.split(" ")[1:]) if " " in rest else ""
            issues.append(
                {
                    "file": file_path,
                    "line": int(line_no),
                    "col": int(col_no),
                    "code": code,
                    "message": message,
                }
            )

    return issues[:max_results]


def run_ruff_check_with_stats():
    """Run ruff and count issues per category"""

    cmd = [
        "ruff",
        "check",
        "--select",
        ",".join(RULES),
        "--output-format",
        "json",
        *build_exclude_args(),
        str(PROJECT_ROOT),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        return {}

    import json

    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}

    # Count
    stats = {}
    for issue in issues:
        code = issue.get("code", "UNKNOWN")
        stats[code] = stats.get(code, 0) + 1

    return stats


def find_large_files(min_lines: int = 500):
    """Find Python files exceeding specified line count"""

    import os

    large_files = []

    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if not any(ex in root for ex in EXCLUDE_DIRS)]

        for f in files:
            if f.endswith(".py"):
                path = Path(root) / f
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                        lines = len(fp.readlines())
                    if lines >= min_lines:
                        rel_path = path.relative_to(PROJECT_ROOT)
                        large_files.append((str(rel_path), lines))
                except Exception:
                    pass

    large_files.sort(key=lambda x: x[1], reverse=True)
    return large_files


def main():
    print("=" * 60)
    print("Static Code Complexity Analysis Report")
    print("=" * 60)

    # 1. Large file check
    print("\nLarge File Check (>= 500 lines):")
    large_files = find_large_files(500)
    if large_files:
        for f, lines in large_files[:20]:
            print(f"  {lines:>4} lines  {f}")
        if len(large_files) > 20:
            print(f"  ... and {len(large_files) - 20} more files")
    else:
        print("  OK: No files over 500 lines")

    # 2. Statistics per category
    print("\nIssue Statistics:")
    stats = run_ruff_check_with_stats()
    if stats:
        for code, count in sorted(stats.items(), key=lambda x: -x[1]):
            print(f"  {code}: {count}")
    else:
        print("  OK: No complexity issues found")

    # 3. Show top 30 specific issues
    print("\nSpecific Issues (Top 30):")
    issues = run_ruff_check(RULES, max_results=30)
    if issues:
        current_file = None
        for issue in issues:
            if issue["file"] != current_file:
                current_file = issue["file"]
                print(f"\n  File: {current_file}")
            print(f"    Line {issue['line']:>4}: {issue['code']} {issue['message']}")
    else:
        print("  OK: No specific issues")

    # 4. Suggested priority order
    print("\n" + "=" * 60)
    print("Suggested Priority Order:")
    print("=" * 60)

    priority_rules = [
        ("C901", "High cyclomatic complexity -> Split function, reduce nesting"),
        ("PLR0915", "Too many statements in function -> Split into smaller functions"),
        (
            "PLR0912",
            "Too many branches -> Guard clauses, strategy pattern, lookup table",
        ),
        ("PLR0914", "Too many local variables -> Split function, use dataclass"),
        ("PLR0913", "Too many parameters -> Use dataclass/config object"),
        ("PLR0904", "Too many public methods in class -> Split into multiple classes"),
        ("PLR0902", "Too many instance attributes -> Group into sub-objects"),
        ("PLR0911", "Too many return statements -> Single return point, guard clauses"),
    ]

    for code, desc in priority_rules:
        count = stats.get(code, 0)
        if count > 0:
            print(f"  {code} ({count}): {desc}")


if __name__ == "__main__":
    main()
