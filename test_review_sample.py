#!/usr/bin/env python3
"""Test file for review pipeline verification."""

import os
import sys
from typing import List, Optional

# Global variable (potential issue)
GLOBAL_CONFIG = {"debug": True}

class DataProcessor:
    """Sample class with some potential issues for review."""
    
    def __init__(self):
        self.data = []
        self.config = GLOBAL_CONFIG  # Using global state
        
    def process_items(self, items: List[str]) -> List[str]:
        """Process a list of items.
        
        Args:
            items: List of strings to process
            
        Returns:
            Processed items
        """
        results = []
        for i in range(len(items)):  # Could use enumerate
            item = items[i]
            try:
                # Potential security issue: eval usage
                if item.startswith("eval:"):
                    result = eval(item[5:])  
                    results.append(str(result))
                else:
                    results.append(item.upper())
            except Exception as e:  # Too broad exception
                print(f"Error: {e}")  # Should use logging
                results.append("")
        
        return results
    
    def load_file(self, filepath: str) -> Optional[str]:
        """Load file without proper validation."""
        # Missing path validation
        with open(filepath, 'r') as f:  # No error handling
            return f.read()
    
    def save_data(self, data: dict) -> None:
        """Save data with potential issues."""
        # Hardcoded path
        with open("/tmp/data.json", "w") as f:
            import json
            json.dump(data, f)  # No error handling
    
    # Missing docstring
    def calculate_sum(self, numbers):
        total = 0
        for n in numbers:
            total = total + n  # Could use +=
        return total

def main():
    """Main function with test code."""
    processor = DataProcessor()
    
    # Test data
    test_items = ["hello", "world", "eval:2+2"]
    results = processor.process_items(test_items)
    print(results)
    
    # Unused variable
    unused_var = "This is never used"
    
    # Magic number
    if len(results) > 3:
        print("Too many results")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())