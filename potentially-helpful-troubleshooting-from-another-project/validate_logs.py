#!/usr/bin/env python3
"""
Validation script for investigation logs.
Ensures logs follow the required format and conventions.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class LogValidator:
    """Validates investigation log structure and content."""

    REQUIRED_FIELDS = {"timestamp", "tags", "summary", "details", "outcome"}
    OPTIONAL_FIELDS = {"hypothesis", "falsification_steps", "notes"}
    VALID_TAGS = {
        # Investigation phases
        "initial_symptom",
        "observation",
        "hypothesis",
        "investigation",
        "breakthrough",
        "root_cause",
        # Actions
        "fix_decision",
        "implementation",
        "validation",
        "testing",
        # Meta
        "reflection",
        "process_improvement",
        "lessons_learned",
        "summary",
    }

    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate(self) -> bool:
        """Run all validations on the log file."""
        try:
            with open(self.log_file) as f:
                logs = json.load(f)
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON: {e}")
            return False
        except FileNotFoundError:
            self.errors.append(f"File not found: {self.log_file}")
            return False

        if not isinstance(logs, list):
            self.errors.append("Log must be a JSON array")
            return False

        # Validate each entry
        for i, entry in enumerate(logs):
            self._validate_entry(entry, i)

        # Check chronological order
        self._check_chronological_order(logs)

        # Check hypothesis tracking
        self._check_hypothesis_tracking(logs)

        return len(self.errors) == 0

    def _validate_entry(self, entry: dict[str, Any], index: int) -> None:
        """Validate a single log entry."""
        prefix = f"Entry {index}"

        # Check required fields
        missing = self.REQUIRED_FIELDS - set(entry.keys())
        if missing:
            self.errors.append(f"{prefix}: Missing required fields: {missing}")

        # Check no extra fields
        all_fields = self.REQUIRED_FIELDS | self.OPTIONAL_FIELDS
        extra = set(entry.keys()) - all_fields
        if extra:
            self.warnings.append(f"{prefix}: Unknown fields: {extra}")

        # Validate timestamp format
        if "timestamp" in entry:
            try:
                datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                self.errors.append(f"{prefix}: Invalid timestamp format: {entry.get('timestamp')}")

        # Validate tags
        if "tags" in entry:
            if not isinstance(entry["tags"], list):
                self.errors.append(f"{prefix}: Tags must be an array")
            else:
                invalid_tags = set(entry["tags"]) - self.VALID_TAGS
                if invalid_tags:
                    self.warnings.append(f"{prefix}: Unknown tags: {invalid_tags}")
                if not entry["tags"]:
                    self.errors.append(f"{prefix}: Tags array cannot be empty")

        # Check hypothesis consistency
        if entry.get("hypothesis") and not entry.get("falsification_steps"):
            self.warnings.append(f"{prefix}: Hypothesis without falsification_steps")

        # Check summary length
        if "summary" in entry and len(entry["summary"]) > 100:
            self.warnings.append(f"{prefix}: Summary exceeds 100 characters")

    def _check_chronological_order(self, logs: list[dict[str, Any]]) -> None:
        """Verify logs are in chronological order."""
        timestamps = []
        for entry in logs:
            if "timestamp" in entry:
                try:
                    ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                    timestamps.append(ts)
                except (ValueError, AttributeError):
                    pass  # Already reported in entry validation

        if timestamps != sorted(timestamps):
            self.errors.append("Entries are not in chronological order")

    def _check_hypothesis_tracking(self, logs: list[dict[str, Any]]) -> None:
        """Check that hypotheses are properly tracked."""
        open_hypotheses: dict[str, int] = {}

        for i, entry in enumerate(logs):
            if entry.get("hypothesis"):
                hypothesis = entry["hypothesis"]
                if hypothesis not in open_hypotheses:
                    open_hypotheses[hypothesis] = i

            # Check if this entry resolves any hypothesis
            if "hypothesis" in ["falsified", "confirmed", "validated"] in entry.get("outcome", "").lower():
                # Could match hypothesis from details
                pass

        # Warn about unresolved hypotheses
        if open_hypotheses:
            for hypothesis, index in open_hypotheses.items():
                # Only warn if it's not in the last few entries
                if index < len(logs) - 3:
                    self.warnings.append(f"Hypothesis at entry {index} may not have resolution: {hypothesis[:50]}...")

    def print_report(self) -> None:
        """Print validation report."""
        print(f"\n📋 Validating: {self.log_file}")
        print("=" * 60)

        if not self.errors and not self.warnings:
            print("✅ All validations passed!")
            return

        if self.errors:
            print("\n❌ ERRORS (must fix):")
            for error in self.errors:
                print(f"  • {error}")

        if self.warnings:
            print("\n⚠️  WARNINGS (should review):")
            for warning in self.warnings:
                print(f"  • {warning}")

        print("\n" + "=" * 60)
        print(f"Summary: {len(self.errors)} errors, {len(self.warnings)} warnings")


def main():
    """Main entry point."""
    # Default to all JSON files in troubleshooting directory
    if len(sys.argv) > 1:
        files = [Path(arg) for arg in sys.argv[1:]]
    else:
        files = list(Path(__file__).parent.glob("*_log.json"))

    if not files:
        print("No log files found to validate")
        sys.exit(1)

    all_valid = True
    for file in files:
        validator = LogValidator(file)
        valid = validator.validate()
        validator.print_report()
        all_valid = all_valid and valid

    sys.exit(0 if all_valid else 1)


if __name__ == "__main__":
    main()
