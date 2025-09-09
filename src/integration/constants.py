"""Integration-layer constants for durable promise/correlation identifiers.

Centralizes ID format to avoid drift across bridge/capability helpers.

Conventions (local mode, Phase 2):
- Execute promises: f"{EXEC_PREFIX}{execution_id}"
- Input promises:   f"{EXEC_PREFIX}{execution_id}:{INPUT_SEGMENT}{request_id}"
  where request_id is the InputMessage.id used for correlation

Future capabilities should follow the same pattern using CAP segments.
"""

EXEC_PREFIX = "exec:"
INPUT_SEGMENT = "input:"
CHECKPOINT_SEGMENT = "checkpoint:"
RESTORE_SEGMENT = "restore:"


def execution_promise_id(execution_id: str) -> str:
    return f"{EXEC_PREFIX}{execution_id}"


def input_promise_id(execution_id: str, input_id: str) -> str:
    return f"{EXEC_PREFIX}{execution_id}:{INPUT_SEGMENT}{input_id}"
