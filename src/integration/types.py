from __future__ import annotations

from typing import Any, TypedDict


class DurableResult(TypedDict):
    """Final payload returned by durable_execute.

    - result: the value produced by AsyncExecutor (may be any Python object)
    - execution_id: identifier associated with this execution
    """

    result: Any
    execution_id: str
