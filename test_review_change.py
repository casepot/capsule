#!/usr/bin/env python3
"""
Test file for review pipeline demonstration.
This file intentionally contains issues for the reviewers to find.
"""

import subprocess  # Security risk: subprocess usage
import os

def process_user_input(user_data):
    """Process user input - potential security issue."""
    # Bug: No input validation
    cmd = f"echo {user_data}"  # Security: Command injection vulnerability
    result = subprocess.run(cmd, shell=True, capture_output=True)
    return result.stdout.decode()

def calculate_average(numbers):
    """Calculate average of numbers."""
    # Bug: No check for empty list
    total = sum(numbers)
    return total / len(numbers)  # Will raise ZeroDivisionError if empty

class DataProcessor:
    def __init__(self):
        self.data = []
        
    def add_data(self, item):
        # Performance: Inefficient for large datasets
        if item not in self.data:
            for i in range(len(self.data)):  # Could use set for O(1) lookup
                if self.data[i] == item:
                    return
            self.data.append(item)
    
    def process(self):
        # Missing error handling
        result = []
        for item in self.data:
            processed = item.upper()  # Assumes all items are strings
            result.append(processed)
        return result

# Missing tests
# No docstrings for class methods
# No type hints