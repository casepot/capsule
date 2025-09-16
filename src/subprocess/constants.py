"""Constants shared across subprocess components.

This module provides centralized constants used by multiple components
in the subprocess module to ensure consistency and prevent drift.
"""

# Engine internals that must be preserved during namespace operations
# These keys are critical for IPython/Python execution state and must
# never be deleted or overwritten without explicit intent
# Reference: docs/execution-engine.md (namespace preservation contracts)
ENGINE_INTERNALS = {
    "_",  # Last result
    "__",  # Second to last result
    "___",  # Third to last result
    "_i",  # Last input
    "_ii",  # Second to last input
    "_iii",  # Third to last input
    "Out",  # Output history
    "In",  # Input history
    "_oh",  # Output history dict (IPython)
    "_ih",  # Input history list (IPython)
    "_exit_code",  # Last exit code
    "_exception",  # Last exception
}
