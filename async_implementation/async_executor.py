
# src/subprocess/async_executor.py
"""
Async-first executor with top-level await support and intelligent routing.

Contract
--------
- Primary execution runs inside the worker's asyncio event loop.
- Top-level await is supported via `ast.PyCF_ALLOW_TOP_LEVEL_AWAIT`.
- Truly blocking sync operations (e.g., input(), time.sleep) are executed in a
  dedicated single-worker ThreadPool to avoid blocking the loop.
- Stdout/stderr are streamed to the transport in all modes.
- Namespace persistence is maintained via the provided NamespaceManager.
- Last-expression value is captured (including with top-level await) using an
  AST rewrite that assigns it to a sentinel variable to avoid double-evaluation.

Invariants
----------
- Exactly one event loop per subprocess worker.
- At most one active execution per worker (the worker is responsible for
  orchestrating concurrency; this class is not re-entrant).
- Output ordering is preserved (line-buffered) per stream.
- input()/ainput() requests are correlated by tokens and resolved exactly once.

Error Semantics
---------------
- Syntax/Runtime exceptions are captured, printed to stderr (so they stream),
  and re-raised for the caller (worker) to send a structured ErrorMessage.
- Cancellation propagates: if the outer task is cancelled, we attempt to cancel
  any running coroutine and unwind cleanly.

Configuration Knobs
-------------------
- thread_max_workers: size of the fallback thread pool (default 1).
- output_flush_interval: max delay to coalesce partial lines (default 0.0).
"""

from __future__ import annotations

import ast
import asyncio
import builtins
import inspect
import io
import sys
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from types import CodeType
from typing import Any, Dict, Optional, Callable

try:
    from ..protocol.messages import (
        InputMessage,
        InputResponseMessage,
        OutputMessage,
        ResultMessage,
        ErrorMessage,
        StreamType,
    )
except Exception:  # pragma: no cover
    # Fallback for sandbox layout
    from messages import (  # type: ignore
        InputMessage,
        InputResponseMessage,
        OutputMessage,
        ResultMessage,
        ErrorMessage,
        StreamType,
    )

try:
    from .code_analyzer import CodeAnalyzer, CodeAnalysis
except Exception:  # pragma: no cover
    from .code_analyzer import CodeAnalyzer, CodeAnalysis  # type: ignore


@dataclass
class MessageTransport:
    """Structural protocol for transport used by the worker.

    Requires an async method: send_message(Message) -> None
    """
    send_message: Callable[..., Any]  # async
    receive_message: Optional[Callable[..., Any]] = None  # async (not used here)


class AsyncLineWriter:
    """Line-buffering stream that schedules async sends without blocking.

    - write(str): buffers until newline, then schedules a send
    - flush(): sends any remaining buffer as a line
    Preserves ordering per stream via an internal asyncio.Queue and a pump task.
    """

    def __init__(self, transport: MessageTransport, execution_id: str, stream: StreamType):
        self._transport = transport
        self._execution_id = execution_id
        self._stream = stream
        self._buf: str = ""
        self._queue: "asyncio.Queue[str]" = asyncio.Queue()
        self._pump_task: Optional[asyncio.Task] = None
        self._closed = False

    def _ensure_pump(self) -> None:
        if self._pump_task is None:
            self._pump_task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        try:
            while True:
                data = await self._queue.get()
                if data is None:  # type: ignore
                    break
                msg = OutputMessage(
                    id=str(uuid.uuid4()),
                    timestamp=time.time(),
                    data=data,
                    stream=self._stream,
                    execution_id=self._execution_id,
                )
                await self._transport.send_message(msg)  # type: ignore[attr-defined]
        except asyncio.CancelledError:
            pass

    def write(self, data: str) -> int:
        if self._closed:
            return 0
        if not isinstance(data, str):
            data = str(data)
        self._buf += data
        self._ensure_pump()
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            # Preserve newline
            self._queue.put_nowait(line + "\n")
        return len(data)

    def flush(self) -> None:
        if self._closed:
            return
        if self._buf:
            self._ensure_pump()
            self._queue.put_nowait(self._buf)
            self._buf = ""

    def close(self) -> None:
        if self._closed:
            return
        self.flush()
        self._closed = True
        if self._pump_task and not self._pump_task.done():
            self._queue.put_nowait(None)  # type: ignore

    def isatty(self) -> bool:  # compatibility
        return False

    def fileno(self) -> int:  # not supported
        raise io.UnsupportedOperation("fileno")


class AsyncExecutor:
    """Async-first executor with intelligent execution routing.

    Public API:
        - execute(code: str) -> Any
        - handle_input_response(token: str, data: str) -> None
    """

    def __init__(
        self,
        transport: MessageTransport,
        execution_id: str,
        namespace: Dict[str, Any],
        thread_max_workers: int = 1,
    ) -> None:
        self._transport = transport
        self._execution_id = execution_id
        self._namespace = namespace
        self._loop = asyncio.get_running_loop()
        self._thread_pool = ThreadPoolExecutor(max_workers=thread_max_workers)
        # Input waiters token -> Future[str]
        self._input_waiters: dict[str, asyncio.Future[str]] = {}
        # Output streams (set during execution)
        self._stdout: Optional[AsyncLineWriter] = None
        self._stderr: Optional[AsyncLineWriter] = None

    # ---------- Input bridging (shared async+thread modes) ----------

    async def _send_input_request(self, token: str, prompt: str) -> None:
        msg = InputMessage(
            id=token,
            timestamp=time.time(),
            prompt=prompt,
            execution_id=self._execution_id,
            timeout=None,
        )
        await self._transport.send_message(msg)  # type: ignore[attr-defined]

    def handle_input_response(self, token: str, data: str) -> None:
        fut = self._input_waiters.get(token)
        if fut and not fut.done():
            fut.set_result(data)

    async def ainput(self, prompt: str = "") -> str:
        """Async-friendly input primitive integrated with the protocol."""
        token = str(uuid.uuid4())
        fut: asyncio.Future[str] = self._loop.create_future()
        self._input_waiters[token] = fut
        await self._send_input_request(token, prompt)
        try:
            return await fut
        finally:
            self._input_waiters.pop(token, None)

    # ---------- Public API ----------

    async def execute(self, code: str) -> Any:
        """Main entrypoint that selects an execution strategy and returns the value.

        Strategy selection:
          1) If code contains top-level await (detected by compile flags) -> async path.
          2) Else if CodeAnalyzer heuristics say it needs blocking IO -> thread path.
          3) Else -> sync-in-async path (exec in loop).
        """
        analysis = CodeAnalyzer.analyze(code)

        # Route and run
        if analysis.has_top_level_await:
            return await self._execute_async(code, analysis)
        elif analysis.needs_blocking_io:
            return await self._execute_in_thread(code, analysis)
        else:
            return await self._execute_sync_in_async(code, analysis)

    # ---------- Implementations ----------

    def _install_streams(self) -> tuple[Any, Any]:
        """Replace sys.stdout/stderr with async line writers, return originals."""
        stdout = AsyncLineWriter(self._transport, self._execution_id, StreamType.STDOUT)
        stderr = AsyncLineWriter(self._transport, self._execution_id, StreamType.STDERR)
        orig_out, orig_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout, stderr  # type: ignore
        self._stdout, self._stderr = stdout, stderr
        return orig_out, orig_err

    def _restore_streams(self, orig_out: Any, orig_err: Any) -> None:
        for s in (self._stdout, self._stderr):
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        sys.stdout, sys.stderr = orig_out, orig_err  # type: ignore

    async def _execute_async(self, code: str, analysis: CodeAnalysis) -> Any:
        """Execute code with top-level await allowed inside the loop."""
        # Prepare namespace and I/O
        orig_out, orig_err = self._install_streams()
        # Provide async ainput helper
        self._namespace["ainput"] = self.ainput

        try:
            # Build AST with last-expr capture
            module_ast: ast.Module = compile(
                code, "<async>", "exec", ast.PyCF_ONLY_AST | ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
            )
            last_expr_name = "__pyrepl3_result__"
            self._maybe_rewrite_last_expr(module_ast, last_expr_name)

            # Compile with TLA allowed
            code_obj: CodeType = compile(module_ast, "<async>", "exec", ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)

            # Evaluate; this returns a coroutine when TLA is present
            maybe_coro = eval(code_obj, self._namespace)
            if inspect.isawaitable(maybe_coro):
                await maybe_coro

            result = self._namespace.get(last_expr_name, None)
            # mirror IPython convention: "_" holds last result
            self._namespace["_"] = result
            return result

        except Exception:
            # Print traceback to stderr so it streams
            traceback.print_exc(file=sys.stderr)
            raise
        finally:
            self._restore_streams(orig_out, orig_err)

    async def _execute_sync_in_async(self, code: str, analysis: CodeAnalysis) -> Any:
        """Execute synchronous code directly in the loop (fast path)."""
        orig_out, orig_err = self._install_streams()
        # Provide ainput for user convenience (works but requires awaiting)
        self._namespace["ainput"] = self.ainput

        try:
            module_ast: ast.Module = compile(code, "<sync>", "exec", ast.PyCF_ONLY_AST)
            last_expr_name = "__pyrepl3_result__"
            self._maybe_rewrite_last_expr(module_ast, last_expr_name)

            code_obj: CodeType = compile(module_ast, "<sync>", "exec")
            exec(code_obj, self._namespace)

            result = self._namespace.get(last_expr_name, None)
            self._namespace["_"] = result
            return result

        except Exception:
            traceback.print_exc(file=sys.stderr)
            raise
        finally:
            self._restore_streams(orig_out, orig_err)

    async def _execute_in_thread(self, code: str, analysis: CodeAnalysis) -> Any:
        """Execute blocking code in a dedicated worker thread."""
        loop = asyncio.get_running_loop()

        # Bridge class to reuse protocol I/O from a thread
        executor = _ThreadBridge(self._transport, self._execution_id, self._namespace, loop, self.ainput)

        # Run the blocking code
        return await loop.run_in_executor(self._thread_pool, executor.run, code)

    # ---------- Helpers ----------

    @staticmethod
    def _maybe_rewrite_last_expr(module_ast: ast.Module, result_name: str) -> None:
        """If the last statement is an expression, replace it with an assignment
        to `result_name`. Supports both sync and TLA by using the AST we already
        compiled with the appropriate flags.
        """
        if not module_ast.body:
            return
        last = module_ast.body[-1]
        if isinstance(last, ast.Expr):
            assign = ast.Assign(targets=[ast.Name(id=result_name, ctx=ast.Store())], value=last.value)
            ast.copy_location(assign, last)
            module_ast.body[-1] = assign
            ast.fix_missing_locations(module_ast)


class _ThreadBridge:
    """Run user code in a thread with protocol-based I/O.

    This is a minimal, self-contained version of the previous ThreadedExecutor
    sufficient for use as a fallback for blocking code paths. It shares the
    same namespace dict with the AsyncExecutor so state persists across modes.
    """

    def __init__(
        self,
        transport: MessageTransport,
        execution_id: str,
        namespace: Dict[str, Any],
        loop: asyncio.AbstractEventLoop,
        ainput: Callable[[str], "asyncio.Future[str]"] | Callable[[str], "asyncio.Future[str]"],
    ) -> None:
        self._transport = transport
        self._execution_id = execution_id
        self._namespace = namespace
        self._loop = loop
        self._ainput = ainput

    
        def _create_input(self) -> Callable[[str], str]:
            def protocol_input(prompt: str = "") -> str:
                # Delegate to the AsyncExecutor's ainput via the main loop.
                fut = asyncio.run_coroutine_threadsafe(self._ainput(prompt), self._loop)
                return fut.result()
            return protocol_input

