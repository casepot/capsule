from __future__ import annotations

from typing import Any, Callable

class Promise:
    def result(self) -> Any: ...

class PromiseRegistry:
    def create(self, *, id: str, timeout: int, data: str) -> Promise: ...
    def resolve(self, *, id: str, data: str) -> None: ...

class Resonate:
    promises: PromiseRegistry

    @staticmethod
    def local() -> Resonate: ...

    def register(
        self,
        name: str | None = ...,
        version: int | str = ...,
        timeout: int | None = ...,
        retries: int | None = ...,
        idempotent: bool | None = ...,
        tags: list[str] | None = ...,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...

    def set_dependency(self, name: str, value: Any) -> None: ...

