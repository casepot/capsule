#!/usr/bin/env python3
"""
Extract insights and patterns from investigation logs.
Useful for quickly finding similar issues or understanding patterns.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def load_logs(file_path: Path) -> list[dict[str, Any]]:
    """Load investigation logs from JSON file."""
    with open(file_path) as f:
        return json.load(f)


def extract_hypotheses(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract all hypotheses with their outcomes."""
    hypotheses = []
    for entry in logs:
        if entry.get("hypothesis"):
            hypotheses.append(
                {
                    "timestamp": entry["timestamp"],
                    "hypothesis": entry["hypothesis"],
                    "falsification": entry.get("falsification_steps", "Not documented"),
                    "outcome": entry["outcome"],
                    "tags": entry["tags"],
                }
            )
    return hypotheses


def extract_root_causes(logs: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract confirmed root causes."""
    root_causes = []
    for entry in logs:
        if "root_cause" in entry.get("tags", []):
            root_causes.append(
                {
                    "timestamp": entry["timestamp"],
                    "cause": entry["summary"],
                    "details": entry["details"][:200] + "..." if len(entry["details"]) > 200 else entry["details"],
                }
            )
    return root_causes


def extract_fixes(logs: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract implemented fixes."""
    fixes = []
    for entry in logs:
        if "fix_decision" in entry.get("tags", []) or "implementation" in entry.get("tags", []):
            fixes.append(
                {
                    "timestamp": entry["timestamp"],
                    "fix": entry["summary"],
                    "details": entry["details"][:200] + "..." if len(entry["details"]) > 200 else entry["details"],
                    "outcome": entry["outcome"],
                }
            )
    return fixes


def extract_lessons(logs: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract lessons learned and process improvements."""
    lessons = []
    for entry in logs:
        tags = entry.get("tags", [])
        if any(tag in tags for tag in ["lessons_learned", "process_improvement", "reflection"]):
            lessons.append(
                {
                    "type": [t for t in tags if t in ["lessons_learned", "process_improvement", "reflection"]][0],
                    "lesson": entry["summary"],
                    "details": entry.get("notes") or entry["details"][:200],
                }
            )
    return lessons


def calculate_investigation_stats(logs: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate investigation statistics."""
    if not logs:
        return {}

    timestamps = []
    for entry in logs:
        try:
            ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            timestamps.append(ts)
        except:
            pass

    if len(timestamps) >= 2:
        duration = timestamps[-1] - timestamps[0]
        duration_hours = duration.total_seconds() / 3600
    else:
        duration_hours = 0

    hypothesis_count = sum(1 for e in logs if e.get("hypothesis"))

    tag_counts: defaultdict[str, int] = defaultdict(int)
    for entry in logs:
        for tag in entry.get("tags", []):
            tag_counts[tag] += 1

    return {
        "total_entries": len(logs),
        "duration_hours": round(duration_hours, 2),
        "hypotheses_tested": hypothesis_count,
        "tag_distribution": dict(tag_counts),
    }


def print_section(title: str, items: list[Any], formatter=None):
    """Print a formatted section."""
    print(f"\n{'=' * 60}")
    print(f"📌 {title}")
    print("=" * 60)

    if not items:
        print("  (None found)")
        return

    for i, item in enumerate(items, 1):
        if formatter:
            print(formatter(i, item))
        else:
            print(f"\n{i}. ", end="")
            for key, value in item.items():
                if key == "timestamp":
                    continue
                print(f"   {key.title()}: {value}")


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1])
    else:
        # Default to v0_1 investigation log
        file_path = Path(__file__).parent / "v0_1_investigation_log.json"

    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    print(f"\n🔍 Analyzing: {file_path.name}")

    logs = load_logs(file_path)

    # Extract different types of insights
    stats = calculate_investigation_stats(logs)
    hypotheses = extract_hypotheses(logs)
    root_causes = extract_root_causes(logs)
    fixes = extract_fixes(logs)
    lessons = extract_lessons(logs)

    # Print statistics
    print("\n📊 Investigation Statistics")
    print("=" * 60)
    print(f"  Total Entries: {stats.get('total_entries', 0)}")
    print(f"  Duration: {stats.get('duration_hours', 0)} hours")
    print(f"  Hypotheses Tested: {stats.get('hypotheses_tested', 0)}")

    if stats.get("tag_distribution"):
        print("\n  Tag Distribution:")
        for tag, count in sorted(stats["tag_distribution"].items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"    • {tag}: {count}")

    # Print hypotheses
    print_section(
        "Hypotheses Tested",
        hypotheses[:5],
        lambda i, h: f"\n{i}. {h['hypothesis'][:100]}...\n   Outcome: {h['outcome'][:100]}...",
    )

    # Print root causes
    print_section("Root Causes Identified", root_causes)

    # Print fixes
    print_section("Fixes Implemented", fixes[:5], lambda i, f: f"\n{i}. {f['fix']}\n   Outcome: {f['outcome']}")

    # Print lessons
    print_section("Lessons Learned", lessons)

    # Print summary
    print(f"\n{'=' * 60}")
    print("💡 Quick Insights")
    print("=" * 60)

    if root_causes:
        print(f"\n✓ Identified {len(root_causes)} root cause(s)")

    if fixes:
        successful_fixes = [f for f in fixes if "success" in f["outcome"].lower() or "pass" in f["outcome"].lower()]
        print(f"✓ Implemented {len(fixes)} fix(es), {len(successful_fixes)} successful")

    if hypotheses:
        falsified = [h for h in hypotheses if "falsified" in h["outcome"].lower()]
        confirmed = [h for h in hypotheses if "confirmed" in h["outcome"].lower() or "correct" in h["outcome"].lower()]
        print(f"✓ Tested {len(hypotheses)} hypotheses: {len(confirmed)} confirmed, {len(falsified)} falsified")

    if lessons:
        print(f"✓ Captured {len(lessons)} lessons for future reference")


if __name__ == "__main__":
    main()
