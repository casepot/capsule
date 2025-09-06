"""Test-only helpers for observing session messages via interceptors.

These utilities support the single-loop invariant by avoiding direct reads
from the transport in tests. Use them to await specific messages like Ready,
Heartbeat, or custom predicates.
"""

import asyncio
from typing import Callable, Optional

from src.session.manager import Session
from src.protocol.messages import Message


async def await_message(
    session: Session,
    predicate: Callable[[Message], bool],
    timeout: float = 2.0,
) -> Optional[Message]:
    """Await a message that satisfies predicate using a passive interceptor.

    Returns the message if observed within timeout, else None. The interceptor
    is removed automatically when the event fires or timeout elapses.
    """
    event = asyncio.Event()
    seen: dict[str, Message] = {}

    def _observer(msg: Message) -> None:
        try:
            if predicate(msg) and not event.is_set():
                seen["msg"] = msg
                event.set()
        except Exception:
            # Never fail tests due to observer exceptions
            pass

    session.add_message_interceptor(_observer)
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        return seen.get("msg")
    except Exception:
        return None
    finally:
        try:
            session.remove_message_interceptor(_observer)
        except Exception:
            pass

