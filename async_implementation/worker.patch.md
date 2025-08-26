
# src/subprocess/worker.py (delta)
# Replace ThreadedExecutor usage with AsyncExecutor.

from .async_executor import AsyncExecutor

class SubprocessWorker:
    async def execute(self, message: ExecuteMessage) -> None:
        execution_id = message.id
        start_time = time.time()

        # Mark this executor as active so INPUT_RESPONSE can be routed.
        executor = AsyncExecutor(
            transport=self._transport,
            execution_id=execution_id,
            namespace=self._namespace,
        )
        self._active_executor = executor

        try:
            result = await executor.execute(message.code)
            execution_time = time.time() - start_time

            # Send result (preserve current protocol)
            result_msg = ResultMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                value=result if self._is_json_serializable(result) else None,
                repr=repr(result),
                execution_id=execution_id,
                execution_time=execution_time,
            )
            await self._transport.send_message(result_msg)
        except Exception as e:
            error_msg = ErrorMessage(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                traceback="".join(traceback.format_exception(type(e), e, e.__traceback__)),
                exception_type=type(e).__name__,
                exception_message=str(e),
                execution_id=execution_id,
            )
            await self._transport.send_message(error_msg)
        finally:
            self._active_executor = None

    async def run(self) -> None:
        # ...
        if message.type in (MessageType.INPUT_RESPONSE, "input_response"):
            if self._active_executor:
                self._active_executor.handle_input_response(message.input_id, message.data)  # type: ignore
            else:
                logger.warning("Received input response with no active executor")
