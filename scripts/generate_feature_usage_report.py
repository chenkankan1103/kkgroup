#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生功能使用量報表並輸出到知識庫 Inbox。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.db.feature_usage import build_usage_markdown, summarize_feature_usage


def main() -> int:
    inbox_dir = PROJECT_ROOT / "knowledge" / "_wiki" / "Inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    output_path = inbox_dir / "feature-usage-report.md"

    days = int(os.getenv("FEATURE_USAGE_REPORT_DAYS", "30"))
    recent_days = int(os.getenv("FEATURE_USAGE_RECENT_DAYS", "7"))
    cold_threshold = int(os.getenv("FEATURE_USAGE_COLD_THRESHOLD", "2"))

    output_path.write_text(
        build_usage_markdown(
            days=days, recent_days=recent_days, cold_threshold=cold_threshold
        ),
        encoding="utf-8",
    )

    summary = summarize_feature_usage(
        days=days, recent_days=recent_days, cold_threshold=cold_threshold
    )
    print(
        json.dumps(
            {
                "report": str(output_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "total_features": summary["total_features"],
                "cold_features": len(summary["cold_features"]),
                "total_interactions": summary["total_interactions"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
