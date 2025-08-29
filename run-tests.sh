#!/usr/bin/env bash
# Test runner script that uses the virtual environment

set -e

# Change to the project directory
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "Warning: No virtual environment found, using system Python"
fi

# Run pytest with any arguments passed to this script
exec pytest "$@"